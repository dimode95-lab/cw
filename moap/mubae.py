"""무한매수법 v4.0 엔진 (라오어 방법론) — 순수 계산 로직.

API 호출 없이 주문 계획(plan)과 상태 갱신(apply)만 담당한다.
tests/test_mubae.py 에서 방법론 문서의 예시 숫자로 검증한다.

용어:
  T        : 진행회차 (1회매수 +1, 절반매수 +0.5, 쿼터매도 ×0.75, 지정가매도 ×0.25)
  별%      : target_pct × (1 - 2T/분할수)   ← 문서의 4가지 공식을 일반화
             (20분할 TQQQ 15-1.5T / 40분할 TQQQ 15-0.75T /
              20분할 SOXL 20-2T / 40분할 SOXL 20-T 와 동일)
  별지점   : 평단 × (1+별%) — 매도는 별지점, 매수는 별지점-0.01
  1회매수금: 잔금 / (분할수 - T)
  리버스모드: T > 분할수-1 (소진) 시 진입, 별지점=직전 5거래일 종가평균
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class StockCfg:
    symbol: str
    exchange: str = "NASD"
    principal: float = 10000.0
    divisions: int = 40          # 20 | 40
    target_pct: float = 15.0     # 지정가매도 % (TQQQ 15, SOXL 20) = 별% 기본값
    big_pct: float = 10.0        # 큰수매수: 전일종가 대비 % (첫매수/급락시)
    ladder_levels: int = 8       # 아래로 추가하는 1주 LOC 매수 단계 수
    compound: bool = True        # 사이클 종료 시 수익 재투자(복리)
    enabled: bool = True


@dataclass
class State:
    symbol: str
    principal: float = 0.0       # 이번 사이클 원금
    mode: str = "NORMAL"         # NORMAL | REVERSE
    T: float = 0.0
    cash: float = 0.0            # 잔금
    shares: int = 0
    avg_price: float = 0.0       # 평단가
    cycle_realized: float = 0.0  # 사이클 내 실현손익
    total_realized: float = 0.0  # 전체 누적 실현손익
    cycle_no: int = 1
    cycle_start: str = ""        # YYYY-MM-DD
    reverse_day: int = 0         # 리버스모드 경과 거래일 (0=첫날 MOC 매도)
    last_close_date: str = ""    # 마지막으로 반영한 종가 날짜
    # 직전 사이클 종료 기록 (수익 일지용)
    last_cycle_profit: float = 0.0
    last_cycle_principal: float = 0.0
    last_cycle_final_t: float = 0.0


@dataclass
class PlannedOrder:
    intent: str       # big_buy|star_half|avg_half|star_full|ladder|quarter_sell|limit_sell|reverse_moc|reverse_sell|quarter_buy|quarter_buy_ladder
    side: str         # buy | sell
    order_type: str   # LOC | MOC | LIMIT
    price: float      # MOC 는 0
    qty: int
    t_inc: float = 0.0   # 이 주문이 체결되면 T에 더해질 값 (매수만, 최대값 하나 적용)


def load_stock_cfgs(yaml_path: Path | None = None) -> list[StockCfg]:
    import yaml as _yaml
    from .config import BASE_DIR
    path = yaml_path or BASE_DIR / "config" / "mubae.yaml"
    data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [StockCfg(**item) for item in data.get("stocks", [])]


# ── 기본 수식 ─────────────────────────────────────────────

def star_pct(cfg: StockCfg, t: float) -> float:
    """별% (예: 40분할 TQQQ T=8 → 15-0.75×8 = 9.0)"""
    return cfg.target_pct * (1 - 2 * t / cfg.divisions)


def star_point(cfg: StockCfg, st: State) -> float:
    """별지점 = 평단 × (1+별%)"""
    return round(st.avg_price * (1 + star_pct(cfg, st.T) / 100), 2)


def one_buy_amount(cfg: StockCfg, st: State) -> float:
    """1회매수금 = 잔금 / (분할수 - T). 잔금을 넘지 않게 캡."""
    denom = max(cfg.divisions - st.T, 0.25)
    return min(st.cash / denom, st.cash)


def _ladder(budget: float, base_qty: int, below: float, levels: int,
            floor_price: float) -> list[float]:
    """추가 1주 LOC 매수 가격들: p_k = 매수금 / (기본수량 + k).

    문서 예시 검증: 예산 617.89, 12주 → 617.89/13=47.53, /14=44.13
    """
    out, k = [], 1
    while len(out) < levels:
        p = round(budget / (base_qty + k), 2)
        k += 1
        if p >= below:
            continue
        if p <= 0 or p < floor_price:
            break
        out.append(p)
    return out


# ── 주문 계획 ─────────────────────────────────────────────

def plan_orders(cfg: StockCfg, st: State, prev_close: float,
                avg5: float) -> list[PlannedOrder]:
    if st.mode == "REVERSE":
        return _plan_reverse(cfg, st, avg5)
    return _plan_normal_buys(cfg, st, prev_close) + _plan_normal_sells(cfg, st)


def _plan_normal_buys(cfg: StockCfg, st: State, prev_close: float) -> list[PlannedOrder]:
    b = one_buy_amount(cfg, st)
    orders: list[PlannedOrder] = []

    if st.shares <= 0:
        # 처음 매수: 전일종가 +big% 큰수 LOC로 무조건 매수 의도
        big = round(prev_close * (1 + cfg.big_pct / 100), 2)
        q = int(b // big)
        if q >= 1:
            orders.append(PlannedOrder("big_buy", "buy", "LOC", big, q, t_inc=1.0))
        base_qty = q
    else:
        sp = star_point(cfg, st)
        star_buy = round(sp - 0.01, 2)
        levels: list[tuple[str, float, int, float]] = []  # (intent, price, qty, t_inc)
        if st.T < cfg.divisions / 2:
            # 전반전: 절반은 별지점-0.01, 나머지 절반은 평단 LOC
            q1 = int((b / 2) // star_buy) if star_buy > 0 else 0
            remain = b - q1 * star_buy
            q2 = int(remain // st.avg_price) if st.avg_price > 0 else 0
            levels = [("star_half", star_buy, q1, 0.5),
                      ("avg_half", round(st.avg_price, 2), q2, 1.0)]
        else:
            # 후반전: 1회매수액 전체를 별지점-0.01 LOC
            q1 = int(b // star_buy) if star_buy > 0 else 0
            levels = [("star_full", star_buy, q1, 1.0)]

        # 큰수매수: 전일종가 대비 너무 높은 가격(≈+20% 거부)은 큰수 가격 하나로 합침
        if any(p > prev_close * 1.15 for _, p, q, _ in levels if q > 0):
            big = round(prev_close * (1 + cfg.big_pct / 100), 2)
            merged_q = sum(q for _, p, q, _ in levels if p >= big)
            merged_t = max((t for _, p, q, t in levels if p >= big and q > 0), default=1.0)
            levels = ([("big_buy", big, merged_q, merged_t)]
                      + [lv for lv in levels if lv[1] < big])

        for intent, price, qty, t_inc in levels:
            if qty >= 1 and price > 0:
                orders.append(PlannedOrder(intent, "buy", "LOC", price, qty, t_inc=t_inc))
        base_qty = sum(o.qty for o in orders)

    # 큰 하락 대비 아래로 1주씩 LOC 추가
    min_main = min((o.price for o in orders), default=prev_close)
    for p in _ladder(b, base_qty, min_main, cfg.ladder_levels, prev_close * 0.5):
        orders.append(PlannedOrder("ladder", "buy", "LOC", p, 1, t_inc=0.0))
    return orders


def _plan_normal_sells(cfg: StockCfg, st: State) -> list[PlannedOrder]:
    if st.shares <= 0:
        return []
    orders = []
    sp = star_point(cfg, st)
    q_quarter = st.shares // 4
    if q_quarter >= 1 and sp > 0:
        orders.append(PlannedOrder("quarter_sell", "sell", "LOC", sp, q_quarter))
    q_limit = st.shares - q_quarter
    limit = round(st.avg_price * (1 + cfg.target_pct / 100), 2)
    if q_limit >= 1:
        orders.append(PlannedOrder("limit_sell", "sell", "LIMIT", limit, q_limit))
    return orders


def _plan_reverse(cfg: StockCfg, st: State, avg5: float) -> list[PlannedOrder]:
    orders: list[PlannedOrder] = []
    n_split = cfg.divisions // 2  # 20분할→10등분, 40분할→20등분
    a = round(avg5, 2)

    if st.shares > 0:
        qty = max(st.shares // n_split, 1)
        if st.reverse_day == 0:
            # 소진 후 첫날: 무조건 매도 (MOC), 매수 없음
            return [PlannedOrder("reverse_moc", "sell", "MOC", 0.0, qty)]
        orders.append(PlannedOrder("reverse_sell", "sell", "LOC", a, qty))

    if st.reverse_day > 0 and st.cash > 0:
        # 쿼터매수: 잔금/4 을 별지점(5일평균) 아래에서 LOC 매수
        c = st.cash / 4
        star_buy = round(a - 0.01, 2)
        q1 = int(c // star_buy) if star_buy > 0 else 0
        if q1 >= 1:
            orders.append(PlannedOrder("quarter_buy", "buy", "LOC", star_buy, q1, t_inc=1.0))
        for p in _ladder(c, q1, star_buy, cfg.ladder_levels, avg5 * 0.5):
            orders.append(PlannedOrder("quarter_buy_ladder", "buy", "LOC", p, 1,
                                       t_inc=1.0 if q1 == 0 else 0.0))
    return orders


# ── 체결 반영 ─────────────────────────────────────────────

def apply_fills(cfg: StockCfg, st: State, fills: list[dict], close: float,
                close_date: str) -> list[str]:
    """전일 체결을 상태에 반영하고 이벤트(한글 설명) 목록을 반환.

    fills 항목: {intent, side, qty, price, amount, t_inc}
    """
    events: list[str] = []
    n = cfg.divisions
    was_reverse = st.mode == "REVERSE"

    sells = [f for f in fills if f["side"] == "sell" and f["qty"] > 0]
    buys = [f for f in fills if f["side"] == "buy" and f["qty"] > 0]

    # 매도 반영 (평단은 매도로 변하지 않음)
    for f in sells:
        pnl = f["amount"] - f["qty"] * st.avg_price
        st.cycle_realized += pnl
        st.total_realized += pnl
        st.shares -= f["qty"]
        st.cash += f["amount"]

    # 매수 반영 (평단 재계산)
    buy_qty = sum(f["qty"] for f in buys)
    buy_amt = sum(f["amount"] for f in buys)
    if buy_qty > 0:
        st.avg_price = round((st.shares * st.avg_price + buy_amt) / (st.shares + buy_qty), 4)
        st.shares += buy_qty
        st.cash -= buy_amt

    # T값 갱신
    intents = {f["intent"] for f in sells}
    if was_reverse:
        if intents & {"reverse_moc", "reverse_sell"}:
            st.T *= (1 - 2 / n)  # 20분할 ×0.9, 40분할 ×0.95
        if buy_qty > 0:
            st.T += (n - st.T) * 0.25
        st.reverse_day += 1
    else:
        if "limit_sell" in intents:
            st.T *= 0.25
            events.append("지정가 매도 체결 (T×0.25)")
        elif "quarter_sell" in intents:
            st.T *= 0.75
            events.append("쿼터매도 체결 (T×0.75)")
        inc = max((f.get("t_inc", 0.0) for f in buys), default=0.0)
        if inc > 0:
            st.T += inc

    st.last_close_date = close_date

    # 전환/종료 판정
    if st.shares <= 0 and sells:
        profit = round(st.cash - st.principal, 2)
        rate = profit / st.principal * 100 if st.principal else 0
        events.append(f"🎊 사이클 {st.cycle_no} 종료! 수익 ${profit:,.2f} ({rate:+.2f}%)")
        st.last_cycle_profit = profit
        st.last_cycle_principal = st.principal
        st.last_cycle_final_t = round(st.T, 6)
        st.principal = round(st.cash, 2) if cfg.compound else st.principal
        st.cash = st.principal
        st.T = 0.0
        st.mode = "NORMAL"
        st.avg_price = 0.0
        st.shares = 0
        st.cycle_realized = 0.0
        st.cycle_no += 1
        st.reverse_day = 0
        st.cycle_start = close_date
    elif st.mode == "NORMAL" and st.T > n - 1:
        st.mode = "REVERSE"
        st.reverse_day = 0
        events.append(f"⚠️ 원금 소진 (T={st.T:.2f}) → 리버스모드 진입 (내일 MOC 매도)")
    elif was_reverse and st.shares > 0 and st.avg_price > 0 \
            and close > st.avg_price * (1 - cfg.target_pct / 100):
        st.mode = "NORMAL"
        events.append(f"↩️ 종가 ${close} > 평단 -{cfg.target_pct:.0f}% → 일반모드 복귀 (T={st.T:.2f})")

    return events


# ── 체결 시뮬레이션 (DRY_RUN / 모의 검증용) ────────────────

def simulate_fills(pendings: list[dict], close: float, high: float) -> list[dict]:
    """LOC/MOC/지정가 규칙으로 종가 기준 체결을 시뮬레이션.

    pendings 항목: {intent, side, order_type, price, qty, t_inc}
    LOC 매수: 종가 ≤ 지정가 → 종가 체결 / LOC 매도: 종가 ≥ 지정가 → 종가 체결
    MOC: 무조건 종가 체결 / 지정가 매도: 고가 ≥ 지정가 → 지정가 체결
    """
    fills = []
    for p in pendings:
        qty, price = 0, close
        if p["order_type"] == "MOC":
            qty = p["qty"]
        elif p["order_type"] == "LOC" and p["side"] == "buy":
            qty = p["qty"] if close <= p["price"] else 0
        elif p["order_type"] == "LOC":
            qty = p["qty"] if close >= p["price"] else 0
        else:  # LIMIT sell
            qty, price = (p["qty"], p["price"]) if high >= p["price"] else (0, close)
        fills.append({
            "intent": p["intent"], "side": p["side"], "qty": qty,
            "price": price if qty else 0.0,
            "amount": round(qty * price, 2),
            "t_inc": p.get("t_inc", 0.0),
        })
    return fills
