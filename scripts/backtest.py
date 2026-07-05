"""무한매수법 v4.0 백테스트 + 규칙 검증 하네스.

매 거래일마다: 주문표 계산 → LOC/MOC/지정가 체결 시뮬레이션 → 상태 갱신을
실전과 동일한 코드(mubae.py)로 수행하면서, 방법론 규칙과 회계 불변식을
독립적으로 검사한다.

사용법:
  python scripts/backtest.py --csv data.csv --symbol TQQQ            # 실데이터
  python scripts/backtest.py --scenario crash --symbol SOXL          # 시나리오
  python scripts/backtest.py --all                                   # 전체 시나리오 검증

CSV 형식: date,open,high,low,close (헤더 필수, 날짜 오름차순/내림차순 무관)
"""
import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moap.mubae import (State, StockCfg, apply_fills, one_buy_amount,
                        plan_orders, simulate_fills, star_pct)

DEFAULTS = {"TQQQ": dict(target_pct=15.0, vol=0.033), "SOXL": dict(target_pct=20.0, vol=0.045)}


# ── 시나리오 생성 (실제 3배 레버리지 ETF 일변동성 수준으로 보정) ──
def gen_scenario(kind: str, days: int = 125, start: float = 70.0,
                 vol: float = 0.035, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows, p = [], start
    for i in range(days):
        if kind == "sideways":
            drift = 0.0
        elif kind == "bull":
            drift = 0.004
        elif kind == "bear":
            drift = -0.012
        elif kind == "crash":     # 급락(30일) → 횡보(30일) → 회복
            drift = -0.035 if i < 30 else (0.0 if i < 60 else 0.012)
        else:
            raise ValueError(kind)
        r = drift + rng.gauss(0, vol)
        prev = p
        p = max(p * (1 + r), 1.0)
        hi = max(prev, p) * (1 + abs(rng.gauss(0, vol * 0.35)))
        lo = min(prev, p) * (1 - abs(rng.gauss(0, vol * 0.35)))
        rows.append({"date": f"D{i+1:03d}", "open": round(prev, 2), "high": round(hi, 2),
                     "low": round(lo, 2), "close": round(p, 2)})
    return rows


def load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        raw = list(csv.DictReader(f))
    rows = []
    for r in raw:
        r = {k.strip().lower(): v for k, v in r.items()}
        rows.append({"date": r["date"], "close": float(r["close"]),
                     "high": float(r.get("high") or r["close"]),
                     "low": float(r.get("low") or r["close"]),
                     "open": float(r.get("open") or r["close"])})
    rows.sort(key=lambda x: x["date"])
    return rows


# ── 독립 규칙 검증기 ──────────────────────────────────────
def validate_plan(cfg, st, prev_close, orders, errors, day):
    def err(msg):
        errors.append(f"[{day}] {cfg.symbol} 규칙위반: {msg}")

    buys = [o for o in orders if o.side == "buy"]
    sells = [o for o in orders if o.side == "sell"]

    if st.mode == "NORMAL":
        b = one_buy_amount(cfg, st)
        # 매도 규칙: 쿼터 = 보유//4 LOC@별지점, 나머지 지정가@평단×(1+P%)
        if st.shares > 0:
            q4 = st.shares // 4
            qs = [o for o in sells if o.intent == "quarter_sell"]
            ls = [o for o in sells if o.intent == "limit_sell"]
            star = round(st.avg_price * (1 + star_pct(cfg, st.T) / 100), 2)
            if q4 >= 1 and (len(qs) != 1 or qs[0].qty != q4 or qs[0].price != star
                            or qs[0].order_type != "LOC"):
                err(f"쿼터매도 불일치: 기대 {q4}주@{star} LOC, 실제 {qs}")
            lim = round(st.avg_price * (1 + cfg.target_pct / 100), 2)
            if len(ls) != 1 or ls[0].qty != st.shares - q4 or ls[0].price != lim:
                err(f"지정가매도 불일치: 기대 {st.shares - q4}주@{lim}, 실제 {ls}")
        elif sells:
            err("보유 0인데 매도 주문 존재")
        # 매수 예산: 어떤 종가에서도 총지출이 1회매수금을 넘지 않아야 함 (LOC 특성)
        cum = 0
        for o in sorted(buys, key=lambda x: -x.price):
            cum += o.qty
            if cum * o.price > b * 1.001 + 0.05:
                err(f"매수 초과지출 가능: {cum}주 × ${o.price} > 1회매수금 ${b:.2f}")
        # t_inc 태그 검증
        for o in buys:
            expected = {"star_half": 0.5, "avg_half": 1.0, "star_full": 1.0,
                        "big_buy": None, "ladder": 0.0}.get(o.intent, 0.0)
            if expected is not None and o.t_inc != expected:
                err(f"{o.intent} t_inc={o.t_inc} (기대 {expected})")
    else:  # REVERSE
        n2 = cfg.divisions // 2
        if st.reverse_day == 0:
            if len(orders) != 1 or orders[0].order_type != "MOC" or orders[0].side != "sell":
                err(f"리버스 첫날은 MOC 매도 1건이어야 함: {orders}")
            elif st.shares > 0 and orders[0].qty != max(st.shares // n2, 1):
                err(f"리버스 첫 매도수량 {orders[0].qty} ≠ {max(st.shares // n2, 1)}")
        else:
            rs = [o for o in sells if o.intent == "reverse_sell"]
            if st.shares > 0 and (len(rs) != 1 or rs[0].qty != max(st.shares // n2, 1)):
                err(f"리버스 매도수량 불일치: {rs}")
            c = st.cash / 4
            cum = 0
            for o in sorted(buys, key=lambda x: -x.price):
                cum += o.qty
                if cum * o.price > c * 1.001 + 0.05:
                    err(f"쿼터매수 초과지출 가능: {cum}주 × ${o.price} > 잔금/4 ${c:.2f}")


def validate_t_update(cfg, t_before, mode_before, fills, t_after, errors, day, symbol):
    """체결 결과로부터 T 갱신을 독립 재계산해 엔진 결과와 대조."""
    t = t_before
    sold = {f["intent"] for f in fills if f["side"] == "sell" and f["qty"] > 0}
    bought = [f for f in fills if f["side"] == "buy" and f["qty"] > 0]
    if mode_before == "NORMAL":
        if "limit_sell" in sold:
            t *= 0.25
        elif "quarter_sell" in sold:
            t *= 0.75
        t += max((f["t_inc"] for f in bought), default=0.0)
    else:
        if sold & {"reverse_moc", "reverse_sell"}:
            t *= (1 - 2 / cfg.divisions)
        if bought:
            t += (cfg.divisions - t) * 0.25
    # 사이클 종료로 T=0 리셋된 경우는 제외
    if t_after != 0.0 and abs(t - t_after) > 1e-9:
        errors.append(f"[{day}] {symbol} T갱신 오류: 기대 {t} vs 실제 {t_after}")


# ── 백테스트 본체 ─────────────────────────────────────────
def run_backtest(cfg: StockCfg, rows: list[dict], log_path: str | None = None,
                 verbose: bool = False) -> dict:
    st = State(symbol=cfg.symbol, principal=cfg.principal, cash=cfg.principal)
    errors, log = [], []
    stats = dict(cycles=0, orders=0, fills=0, max_t=0.0, min_cash=cfg.principal,
                 reverse_entries=0, reverse_exits=0, events=[])

    for i in range(5, len(rows)):
        day = rows[i]["date"]
        prev_close = rows[i - 1]["close"]
        avg5 = sum(r["close"] for r in rows[i - 5:i]) / 5

        orders = plan_orders(cfg, st, prev_close, avg5)
        validate_plan(cfg, st, prev_close, orders, errors, day)
        stats["orders"] += len(orders)

        pend = [{"intent": o.intent, "side": o.side, "order_type": o.order_type,
                 "price": o.price, "qty": o.qty, "t_inc": o.t_inc} for o in orders]
        fills = simulate_fills(pend, rows[i]["close"], rows[i]["high"])
        stats["fills"] += sum(1 for f in fills if f["qty"] > 0)

        t0, mode0, cyc0 = st.T, st.mode, st.cycle_no
        events = apply_fills(cfg, st, fills, rows[i]["close"], day)
        validate_t_update(cfg, t0, mode0, fills, st.T, errors, day, cfg.symbol)

        # 회계 불변식: 원금 + 실현손익 = 잔금 + 보유원가 (평단 4자리 반올림 오차 허용)
        basis = st.shares * st.avg_price
        drift = abs((st.cash + basis) - (st.principal + st.cycle_realized))
        if st.cycle_no == cyc0 and drift > max(1.0, st.shares * 0.01):
            errors.append(f"[{day}] {cfg.symbol} 회계 불일치 ${drift:.2f}")
        if st.cash < -0.01:
            errors.append(f"[{day}] {cfg.symbol} 잔금 음수: {st.cash:.2f}")
        if st.shares < 0:
            errors.append(f"[{day}] {cfg.symbol} 보유수량 음수")
        if not (-1e-9 <= st.T <= cfg.divisions + 1):
            errors.append(f"[{day}] {cfg.symbol} T 범위 이탈: {st.T}")

        stats["max_t"] = max(stats["max_t"], st.T)
        stats["min_cash"] = min(stats["min_cash"], st.cash)
        if st.cycle_no > cyc0:
            stats["cycles"] += 1
        if mode0 == "NORMAL" and st.mode == "REVERSE":
            stats["reverse_entries"] += 1
        if mode0 == "REVERSE" and st.mode == "NORMAL" and st.cycle_no == cyc0:
            stats["reverse_exits"] += 1
        for ev in events:
            stats["events"].append(f"[{day}] {ev}")

        log.append([day, rows[i]["close"], st.mode, round(st.T, 4), st.shares,
                    round(st.avg_price, 4), round(st.cash, 2),
                    len(orders), sum(1 for f in fills if f["qty"] > 0),
                    " | ".join(events)])
        if verbose:
            print(f"{day} close={rows[i]['close']:>8.2f} {st.mode:<7} T={st.T:7.3f} "
                  f"보유={st.shares:>4} 평단={st.avg_price:>8.2f} 잔금={st.cash:>10.2f} "
                  + (" ".join(events)))

    if log_path:
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "close", "mode", "T", "shares", "avg", "cash",
                        "orders", "fills", "events"])
            w.writerows(log)

    final_value = st.cash + st.shares * rows[-1]["close"]
    stats.update(errors=errors, final_value=round(final_value, 2),
                 final_state=st, days=len(rows) - 5,
                 pnl_pct=round((final_value / cfg.principal - 1) * 100, 2))
    return stats


def report(name: str, cfg: StockCfg, s: dict) -> None:
    st = s["final_state"]
    print(f"\n{'='*62}\n[{name}] {cfg.symbol} {cfg.divisions}분할 · 원금 ${cfg.principal:,.0f} · {s['days']}거래일")
    print(f"  주문 {s['orders']}건 / 체결 {s['fills']}건 · 사이클 완료 {s['cycles']}회")
    print(f"  리버스 진입 {s['reverse_entries']}회 / 복귀 {s['reverse_exits']}회 · 최대 T={s['max_t']:.2f}")
    print(f"  최종: {st.mode} T={st.T:.3f} 보유 {st.shares}주 평단 ${st.avg_price:.2f} 잔금 ${st.cash:,.2f}")
    print(f"  평가금액 ${s['final_value']:,.2f} ({s['pnl_pct']:+.2f}%) · 최소잔금 ${s['min_cash']:,.2f}")
    if s["events"]:
        for ev in s["events"][:12]:
            print(f"   · {ev}")
        if len(s["events"]) > 12:
            print(f"   · … 외 {len(s['events'])-12}건")
    if s["errors"]:
        print(f"  ❌ 검증 실패 {len(s['errors'])}건:")
        for e in s["errors"][:20]:
            print(f"     {e}")
    else:
        print("  ✅ 규칙 위반/불변식 오류 0건")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--scenario", choices=["sideways", "bull", "bear", "crash"])
    ap.add_argument("--all", action="store_true", help="전 시나리오 × TQQQ/SOXL 검증")
    ap.add_argument("--symbol", default="TQQQ")
    ap.add_argument("--principal", type=float, default=10000)
    ap.add_argument("--divisions", type=int, default=40)
    ap.add_argument("--days", type=int, default=125)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--log", help="일별 로그 CSV 저장 경로")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    total_errors = 0
    if args.all:
        for sym in ("TQQQ", "SOXL"):
            d = DEFAULTS[sym]
            cfg = StockCfg(sym, principal=args.principal, divisions=args.divisions,
                           target_pct=d["target_pct"])
            for sc in ("sideways", "bull", "bear", "crash"):
                for seed in (args.seed, args.seed + 1, args.seed + 2):
                    rows = gen_scenario(sc, days=args.days, vol=d["vol"], seed=seed)
                    s = run_backtest(cfg, rows)
                    report(f"{sc} seed={seed}", cfg, s)
                    total_errors += len(s["errors"])
        print(f"\n{'='*62}\n총 검증 오류: {total_errors}건")
        sys.exit(1 if total_errors else 0)

    d = DEFAULTS.get(args.symbol, {"target_pct": 15.0, "vol": 0.035})
    cfg = StockCfg(args.symbol, principal=args.principal, divisions=args.divisions,
                   target_pct=d["target_pct"])
    if args.csv:
        rows = load_csv(args.csv)
        name = Path(args.csv).name
    else:
        rows = gen_scenario(args.scenario or "sideways", days=args.days,
                            vol=d["vol"], seed=args.seed)
        name = args.scenario or "sideways"
    s = run_backtest(cfg, rows, log_path=args.log, verbose=args.verbose)
    report(name, cfg, s)
    sys.exit(1 if s["errors"] else 0)


if __name__ == "__main__":
    main()
