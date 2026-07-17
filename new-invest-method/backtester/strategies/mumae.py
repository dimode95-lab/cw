"""A1. 무한매수법 V4.0 — MumaeEngine.kt(01.MumaeApp-dev) Python 포트.

기준 자료:
  - `/home/user/01.MumaeApp-dev/app/src/main/java/com/dimo/mumae/engine/MumaeEngine.kt`
  - 같은 폴더의 `Models.kt` (StrategyState/OrderSpec/Fill/OrderRole/Mode 등 타입)
  - `catalog/A1-무한매수법-V4.0.md` (규칙 명세 — 특히 `rounding`/`fill_interaction_rules` 표)
  - `tests/fixtures/mumae_fixtures.json` (교차검증 픽스처 25건, `_meta` 블록에 반올림 규칙 요약)

이 모듈은 두 계층으로 나뉜다.

1. **순수 계산 계층** (`MumaeState`, `star_percent`, `star_sell_price`, `one_time_budget`,
   `build_orders`, `apply_fills`, `should_enter_reverse`, `should_exit_reverse` 등) —
   Kotlin `MumaeEngine` object의 각 함수를 1:1로 이식한 것. `MumaeOrderSpec`은 Kotlin의
   `OrderSpec`(side/type/role/price/quantity/**label**)과 동일한 필드를 가진다 — label까지
   유지하는 이유는 픽스처가 "큰수 조정" 라벨 부기 여부를 직접 검증하기 때문이다
   (`tests/test_mumae_fixtures.py`가 이 계층을 fixtures와 직접 대조한다. core.py/engine.py는
   이 계층의 존재를 모른다).
2. **엔진 어댑터 계층** (`MumaeStrategy`) — 1번을 `core.Strategy` (on_bar/on_fill) 계약으로
   감싼다. `core.Order`에는 label 필드가 없으므로 어댑터에서 벗겨낸다.

## 반올림/정밀도 이식 원칙 (PLAN.md §4.2, catalog `rounding` 표)

Kotlin은 Double로 사전계산한 값을 `BigDecimal(double, MathContext.DECIMAL64)`로 변환하는
지점이 여러 곳 있다. `MathContext.DECIMAL64`는 **16유효자리, HALF_EVEN**이다(Java 표준 —
HALF_UP이 아니다). 그 뒤 최종 소비 지점에서 `.setScale(2, HALF_UP 또는 DOWN)`으로 센트
반올림한다. 이 파일의 `_bd()`가 `BigDecimal(double, MathContext.DECIMAL64)`를,
`_mc_divide()`가 `BigDecimal.divide(divisor, MathContext.DECIMAL64)`를, `_to_cents()`가
`BigDecimal.setScale(2, mode)`를 재현한다. 사다리(`ladder`)만 예외적으로
`divide(divisor, 2, HALF_UP)`(스케일 직접 지정 나눗셈, MathContext 경유 안 함)를 쓰므로
`_divide_cents()`로 별도 구현했다.

Python `float`은 Kotlin `Double`과 동일하게 IEEE754 binary64이므로, T값·별%처럼 Double로만
계산되는 값은 연산 순서만 Kotlin 소스와 동일하게 맞추면 비트 단위로 일치한다(반올림 없음).

## 상태 소유권에 대한 설계 결정 (core.py 계약과의 접점)

`core.py`의 `Strategy` 계약은 "전략 고유 상태는 `on_fill`에서만 갱신"을 요구한다. T값·평단·
보유수량·잔금은 이 규칙을 그대로 따른다(전부 체결 사건에서만 변하므로 자연스럽게 부합).

문제는 **모드 전환(NORMAL⇄REVERSE)**이다. `shouldEnterReverse`/`shouldExitReverse`는
"주문표를 만들기 직전에" 평가되는 판정이며, 체결 사건이 아니다(catalog `mode_transition`:
"실제 모드 전환은 그날 주문 생성 전에 반영해야 한다"). 리버스 진입 첫날은 MOC 무조건매도라
그날 반드시 체결되어 `on_fill`로 자연스럽게 영구 반영되지만, 리버스 **이탈**은 그날 정상모드
주문(LOC/지정가)이 꼭 체결된다는 보장이 없다 — 체결이 없으면 `state.mode`를 formal하게
갱신할 방법이 `on_fill`에는 없다.
이 구현은 `MumaeStrategy` 인스턴스 자신의 속성(`self._mode_cache`, `self._prev_close`,
`self._recent_closes`)에 "매일 다시 계산해도 같은 결론이 나오는" 모드/가격이력 캐시를 두어
해결한다 — 이는 engine이 스레딩하는 `state` 객체가 아니라 전략 구현체 내부의 캐시이므로
"on_bar가 state를 변형하면 안 된다"는 규칙과 충돌하지 않는다(그 규칙은 `state` 파라미터
자체에 대한 것). `on_fill`이 호출될 때는 그날 사용한 유효 모드를 `state.mode`에도 반영해
최종 리포트용 `state`가 최대한 사실과 일치하게 유지한다. 자세한 내용은 최종 보고 참고.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

_BACKTESTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from core import (  # noqa: E402
    Fill as CoreFill,
    OHLC,
    Order as CoreOrder,
    OrderType,
    PortfolioView,
    Side,
    Strategy,
    round_cents,
)

CENT = Decimal("0.01")

# MathContext.DECIMAL64 (Java 표준: 16유효자리, HALF_EVEN) — Kotlin이 Double → BigDecimal
# 변환/나눗셈에 쓰는 컨텍스트. HALF_UP이 아님에 주의(회귀 포인트).
_DECIMAL64 = Context(prec=16, rounding=ROUND_HALF_EVEN)
# BigDecimal.multiply()/.add()/.subtract()는 MathContext 없이 쓰면 절사 없는 완전정밀 연산.
# Python Decimal의 앰비언트(전역) 컨텍스트에 기대지 않고 항상 이 로컬 컨텍스트로 명시 수행.
_EXACT = Context(prec=50)


def _bd(x: float) -> Decimal:
    """`BigDecimal(double val, MathContext.DECIMAL64)` 포트: 이진 double의 정확한 값을
    16유효자리 HALF_EVEN으로 반올림한다."""
    return _DECIMAL64.create_decimal(Decimal(x))


def _mc_divide(a: Decimal, b: Decimal) -> Decimal:
    """`a.divide(b, MathContext.DECIMAL64)` 포트."""
    return _DECIMAL64.divide(a, b)


def _exact_multiply(a: Decimal, b: Decimal) -> Decimal:
    """`a.multiply(b)`(MathContext 없음 = 완전정밀) 포트."""
    return _EXACT.multiply(a, b)


def _to_cents(x: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    """`BigDecimal.setScale(2, mode)` 포트. HALF_UP이 기본(Kotlin의 `toCents()` 기본과 동일),
    최종매도가만 DOWN을 명시적으로 넘긴다."""
    return round_cents(x, rounding=rounding)


def _divide_cents(a: Decimal, b: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    """`a.divide(b, 2, roundingMode)` 포트 (사다리 전용) — MathContext를 거치지 않고
    정확한 몫을 구한 뒤 바로 센트로 반올림."""
    q = _EXACT.divide(a, b)
    return q.quantize(CENT, rounding=rounding)


def _floor_div(amount: Decimal, price: Decimal) -> int:
    """`amount.divide(price, 0, RoundingMode.DOWN).toInt()` 포트."""
    if price is None or price <= 0:
        return 0
    q = _EXACT.divide(amount, price)
    return int(q.to_integral_value(rounding=ROUND_DOWN))


def _trim(x: float) -> str:
    """Kotlin `Double.trim()` 포트: 정수값이면 정수로, 아니면 그대로 문자열화.
    (라벨 텍스트 전용 — 계산에는 관여하지 않음)"""
    if x == int(x):
        return str(int(x))
    return str(x)


class Mode(Enum):
    NORMAL = "NORMAL"
    REVERSE = "REVERSE"


class OrderRole:
    """Kotlin `OrderRole` enum과 이름을 동일하게 맞춘 문자열 상수 모음.
    `core.Order.role: str` 필드에 그대로 쓰인다."""

    FIRST_BUY = "FIRST_BUY"
    STAR_HALF_BUY = "STAR_HALF_BUY"
    AVG_HALF_BUY = "AVG_HALF_BUY"
    FULL_STAR_BUY = "FULL_STAR_BUY"
    LADDER_BUY = "LADDER_BUY"
    QUARTER_SELL = "QUARTER_SELL"
    FINAL_SELL = "FINAL_SELL"
    REVERSE_FIRST_SELL = "REVERSE_FIRST_SELL"
    REVERSE_SELL = "REVERSE_SELL"
    REVERSE_BUY = "REVERSE_BUY"


@dataclass
class MumaeState:
    """Kotlin `StrategyState` 포트. 필드명은 snake_case로 바꿨을 뿐 1:1 대응
    (`tests/fixtures/mumae_fixtures.json`의 `_meta.state_fields` 매핑 참고)."""

    ticker: str
    divisions: int
    principal: Decimal
    cash_balance: Decimal
    avg_price: Decimal
    quantity: int
    t_value: float
    target_rate: float
    mode: Mode
    big_number_rate: float = 0.10

    @property
    def is_exhausted(self) -> bool:
        return self.t_value > self.divisions - 1.0


@dataclass
class MumaeOrderSpec:
    """Kotlin `OrderSpec` 포트 (side/type/role/price/quantity/label)."""

    side: Side
    type: OrderType
    role: str
    price: Decimal
    quantity: int
    label: str


@dataclass
class MumaeFill:
    """Kotlin `Fill` 데이터클래스 포트 (role/side/price/quantity/fee) — `apply_fills`가
    순수 함수로 소비하는 입력 타입. 엔진 연동 시 `core.Fill`에서 이 타입으로 변환한다."""

    role: str
    side: Side
    price: Decimal
    quantity: int
    fee: Decimal = Decimal("0")


def initial_mumae_state(
    ticker: str,
    principal: Decimal,
    divisions: int,
    target_rate: float,
    big_number_rate: float = 0.10,
) -> MumaeState:
    """새 사이클 시작 상태 (quantity=0, avgPrice=0, T=0, 잔금=원금)."""
    return MumaeState(
        ticker=ticker,
        divisions=divisions,
        principal=principal,
        cash_balance=principal,
        avg_price=Decimal("0"),
        quantity=0,
        t_value=0.0,
        target_rate=target_rate,
        mode=Mode.NORMAL,
        big_number_rate=big_number_rate,
    )


# ---------- 기본 공식 (MumaeEngine.kt 15~49행 포트) ----------


def star_percent(state: MumaeState) -> float:
    """별% = R × (1 − 2T/n). 반올림 없음(Double 그대로)."""
    return state.target_rate * (1.0 - 2.0 * state.t_value / state.divisions)


def star_sell_price(state: MumaeState) -> Decimal:
    """별지점(매도점) = 평단 × (1+별%), 센트 HALF_UP."""
    factor = _bd(1.0 + star_percent(state))
    return _to_cents(_exact_multiply(state.avg_price, factor), ROUND_HALF_UP)


def star_buy_price(state: MumaeState) -> Decimal:
    """매수점 = 별지점(매도) − 0.01 (추가 반올림 없음)."""
    return star_sell_price(state) - CENT


def one_time_budget(state: MumaeState) -> Decimal:
    """1회 매수금 = 잔금 / (n − T). DECIMAL64로 나눗셈, 절사하지 않고 그대로 반환
    (소비처에서 센트화)."""
    denom = state.divisions - state.t_value
    if denom <= 0.0:
        return Decimal("0")
    return _mc_divide(state.cash_balance, _bd(denom))


def final_sell_price(state: MumaeState) -> Decimal:
    """최종 지정가 매도가 = 평단 × (1+R), 센트 DOWN(내림) — HALF_UP이면 회귀."""
    factor = _bd(1.0 + state.target_rate)
    return _to_cents(_exact_multiply(state.avg_price, factor), ROUND_DOWN)


def reverse_star_price(last5_closes: List[Decimal]) -> Decimal:
    """리버스모드 별지점 = 직전 5거래일 종가 평균, 센트 HALF_UP."""
    if not last5_closes:
        raise ValueError("종가 데이터가 필요합니다")
    total = sum(last5_closes, Decimal("0"))
    avg = _mc_divide(total, Decimal(len(last5_closes)))
    return _to_cents(avg, ROUND_HALF_UP)


def big_number_cap(prev_close: Decimal, big_number_rate: float) -> Decimal:
    """큰수 상한 = 전일종가 × (1+bigNumberRate), 센트 HALF_UP."""
    factor = _bd(1.0 + big_number_rate)
    return _to_cents(_exact_multiply(prev_close, factor), ROUND_HALF_UP)


# ---------- 주문표 생성 (MumaeEngine.kt 60~207행 포트) ----------


def ladder(
    budget: Decimal,
    already_qty: int,
    role: str,
    max_rungs: int = 12,
    min_price: Decimal = Decimal("1.00"),
) -> List[MumaeOrderSpec]:
    """폭락 대비 사다리: budget/(alreadyQty+k), k=1..max_rungs, 각 1주, HALF_UP 2자리."""
    if already_qty <= 0:
        return []
    rungs: List[MumaeOrderSpec] = []
    q = already_qty
    for _ in range(max_rungs):
        q += 1
        price = _divide_cents(budget, Decimal(q), ROUND_HALF_UP)
        if price < min_price:
            break
        rungs.append(MumaeOrderSpec(Side.BUY, OrderType.LOC, role, price, 1, "폭락 대비 +@"))
    return rungs


def build_normal_orders(state: MumaeState, prev_close: Decimal) -> List[MumaeOrderSpec]:
    orders: List[MumaeOrderSpec] = []
    budget = one_time_budget(state)

    if state.quantity == 0:
        # T가 0이 아니어도(상태 보정 등) quantity==0이면 새 사이클 첫 매수로 취급한다
        # (Kotlin과 동일 — quantity 기준 분기, tValue 기준 아님).
        big_num = big_number_cap(prev_close, state.big_number_rate)
        qty = _floor_div(budget, big_num)
        if qty > 0:
            orders.append(
                MumaeOrderSpec(
                    Side.BUY,
                    OrderType.LOC,
                    OrderRole.FIRST_BUY,
                    big_num,
                    qty,
                    f"첫 매수 (큰수 +{_trim(state.big_number_rate * 100)}%)",
                )
            )
            orders.extend(ladder(budget, qty, OrderRole.LADDER_BUY))
        return orders

    half_point = state.divisions / 2.0
    star_buy = star_buy_price(state)

    if state.t_value < half_point:
        half = _mc_divide(budget, Decimal(2))
        star_qty = _floor_div(half, star_buy)
        if star_qty > 0:
            orders.append(
                MumaeOrderSpec(Side.BUY, OrderType.LOC, OrderRole.STAR_HALF_BUY, star_buy, star_qty, "별지점 매수")
            )
        remaining = budget - _exact_multiply(star_buy, Decimal(star_qty))
        avg_qty = _floor_div(remaining, state.avg_price)
        if avg_qty > 0:
            orders.append(
                MumaeOrderSpec(
                    Side.BUY,
                    OrderType.LOC,
                    OrderRole.AVG_HALF_BUY,
                    _to_cents(state.avg_price, ROUND_HALF_UP),
                    avg_qty,
                    "평단 매수",
                )
            )
        orders.extend(ladder(budget, star_qty + avg_qty, OrderRole.LADDER_BUY))
    else:
        qty = _floor_div(budget, star_buy)
        if qty > 0:
            orders.append(
                MumaeOrderSpec(Side.BUY, OrderType.LOC, OrderRole.FULL_STAR_BUY, star_buy, qty, "별지점 전량 매수")
            )
        orders.extend(ladder(budget, qty, OrderRole.LADDER_BUY))

    quarter_qty = state.quantity // 4
    if quarter_qty > 0:
        orders.append(
            MumaeOrderSpec(
                Side.SELL, OrderType.LOC, OrderRole.QUARTER_SELL, star_sell_price(state), quarter_qty, "쿼터매도 (별지점)"
            )
        )
    rest_qty = state.quantity - quarter_qty
    if rest_qty > 0:
        orders.append(
            MumaeOrderSpec(
                Side.SELL,
                OrderType.LIMIT,
                OrderRole.FINAL_SELL,
                final_sell_price(state),
                rest_qty,
                f"지정가 매도 (+{_trim(state.target_rate * 100)}%)",
            )
        )
    return orders


def build_reverse_orders(
    state: MumaeState,
    prev_close: Decimal,
    last5_closes: List[Decimal],
    first_day: bool,
) -> List[MumaeOrderSpec]:
    orders: List[MumaeOrderSpec] = []
    if state.quantity > 0:
        sell_qty = max(1, int(state.quantity / (state.divisions / 2.0)))
    else:
        sell_qty = 0

    if first_day:
        if sell_qty > 0:
            orders.append(
                MumaeOrderSpec(
                    Side.SELL,
                    OrderType.MOC,
                    OrderRole.REVERSE_FIRST_SELL,
                    Decimal("0"),
                    sell_qty,
                    "리버스 첫날 MOC 무조건 매도",
                )
            )
        return orders  # 첫날은 매수 없음

    star = reverse_star_price(last5_closes)
    if sell_qty > 0:
        orders.append(
            MumaeOrderSpec(Side.SELL, OrderType.LOC, OrderRole.REVERSE_SELL, star, sell_qty, "리버스 매도 (5일평균)")
        )

    quarter_budget = _mc_divide(state.cash_balance, Decimal(4))
    buy_price = star - CENT
    qty = _floor_div(quarter_budget, buy_price)
    if qty > 0:
        orders.append(
            MumaeOrderSpec(Side.BUY, OrderType.LOC, OrderRole.REVERSE_BUY, buy_price, qty, "리버스 쿼터매수")
        )
        orders.extend(ladder(quarter_budget, qty, OrderRole.LADDER_BUY))
    return orders


def cap_buys_at_big_number(
    orders: List[MumaeOrderSpec], state: MumaeState, prev_close: Decimal
) -> List[MumaeOrderSpec]:
    """생성된 LOC 매수 주문 중 가격이 큰수 상한을 넘으면 상한가로 낮춘다(수량 유지).
    매도는 조정하지 않는다."""
    if prev_close is None or prev_close <= 0:
        return orders
    cap = big_number_cap(prev_close, state.big_number_rate)
    capped: List[MumaeOrderSpec] = []
    for o in orders:
        if o.side == Side.BUY and o.type == OrderType.LOC and o.price > cap:
            capped.append(replace(o, price=cap, label=o.label + " (큰수 조정)"))
        else:
            capped.append(o)
    return capped


def build_orders(
    state: MumaeState,
    prev_close: Decimal,
    last5_closes: Optional[List[Decimal]] = None,
    reverse_first_day: bool = False,
) -> List[MumaeOrderSpec]:
    last5_closes = last5_closes or []
    if state.mode == Mode.NORMAL:
        orders = build_normal_orders(state, prev_close)
    else:
        orders = build_reverse_orders(state, prev_close, last5_closes, reverse_first_day)
    return cap_buys_at_big_number(orders, state, prev_close)


# ---------- 체결 반영 (MumaeEngine.kt 215~287행 포트) ----------


def apply_fills(state: MumaeState, fills: List[MumaeFill]) -> Tuple[MumaeState, Decimal, bool]:
    """하루치 체결(fills)을 상태에 반영한다. 매도 먼저 → 매수 순서로 처리
    (fill_interaction_rules 표와 동일)."""
    if not fills:
        return state, Decimal("0"), False

    cash = state.cash_balance
    qty = state.quantity
    total_cost = state.avg_price * Decimal(state.quantity)
    realized = Decimal("0")

    sells = [f for f in fills if f.side == Side.SELL]
    buys = [f for f in fills if f.side == Side.BUY]

    for f in sells:
        proceeds = f.price * Decimal(f.quantity)
        realized += proceeds - state.avg_price * Decimal(f.quantity) - f.fee
        cash += proceeds - f.fee
        qty -= f.quantity
        total_cost -= state.avg_price * Decimal(f.quantity)

    for f in buys:
        cost = f.price * Decimal(f.quantity)
        cash -= cost + f.fee
        qty += f.quantity
        total_cost += cost

    new_avg = _to_cents(_mc_divide(total_cost, Decimal(qty)), ROUND_HALF_UP) if qty > 0 else Decimal("0")

    t = state.t_value
    n = state.divisions

    if any(f.role == OrderRole.QUARTER_SELL for f in sells):
        t *= 0.75
    if any(f.role in (OrderRole.REVERSE_FIRST_SELL, OrderRole.REVERSE_SELL) for f in sells):
        t *= 1.0 - 2.0 / n
    final_sold = any(f.role == OrderRole.FINAL_SELL for f in sells)
    if final_sold:
        t *= 0.25

    star_half = any(f.role == OrderRole.STAR_HALF_BUY for f in buys)
    avg_half = any(f.role == OrderRole.AVG_HALF_BUY for f in buys)
    full_buy = any(f.role in (OrderRole.FIRST_BUY, OrderRole.FULL_STAR_BUY) for f in buys)
    if full_buy:
        t += 1.0
    elif star_half and avg_half:
        t += 1.0
    elif star_half or avg_half:
        t += 0.5
    if any(f.role == OrderRole.REVERSE_BUY for f in buys):
        t += (n - t) * 0.25

    cycle_closed = qty == 0
    new_state = replace(
        state,
        cash_balance=_to_cents(cash, ROUND_HALF_UP),
        avg_price=new_avg,
        quantity=qty,
        t_value=0.0 if cycle_closed else t,
        mode=Mode.NORMAL if cycle_closed else state.mode,
    )
    return new_state, _to_cents(realized, ROUND_HALF_UP), cycle_closed


# ---------- 모드 전환 판정 (MumaeEngine.kt 292~300행 포트) ----------


def should_enter_reverse(state: MumaeState) -> bool:
    """일반→리버스: T가 n-1을 초과(1회분 미만 잔여)하면 소진."""
    return state.mode == Mode.NORMAL and state.quantity > 0 and state.t_value > state.divisions - 1.0


def should_exit_reverse(state: MumaeState, close: Decimal) -> bool:
    """리버스→일반: 종가가 평단 대비 -R보다 더 하락하면 복귀."""
    if state.mode != Mode.REVERSE or state.avg_price == 0:
        return False
    threshold = _exact_multiply(state.avg_price, _bd(1.0 - state.target_rate))
    return close < threshold


# ---------- 엔진 어댑터: core.Strategy(on_bar/on_fill) 래핑 ----------


class MumaeStrategy(Strategy):
    """단일 티커(TQQQ 또는 SOXL) 무한매수법 V4.0 전략의 `core.Strategy` 어댑터.

    `state`(엔진이 스레딩하는 `MumaeState`)는 T값·평단·보유수량·잔금·(best-effort) 모드만
    담당한다. 가격 이력(전일종가·직전5일종가)과 "오늘의 유효 모드" 캐시는 이 인스턴스 자신의
    속성에 둔다 — 모듈 docstring의 "상태 소유권" 절 참고.
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self._prev_close: Optional[Decimal] = None
        self._recent_closes: List[Decimal] = []
        self._mode_cache: Optional[Mode] = None

    def on_bar(self, state: MumaeState, bars: Dict[str, OHLC], portfolio: PortfolioView) -> List[CoreOrder]:
        bar = bars.get(self.ticker)
        if bar is None:
            return []

        prev_close = self._prev_close
        baseline_mode = self._mode_cache if self._mode_cache is not None else state.mode
        probe_state = replace(state, mode=baseline_mode)

        effective_mode = baseline_mode
        reverse_first_day = False
        if baseline_mode == Mode.NORMAL:
            if should_enter_reverse(probe_state):
                effective_mode = Mode.REVERSE
                reverse_first_day = True
        else:
            if prev_close is not None and should_exit_reverse(probe_state, prev_close):
                effective_mode = Mode.NORMAL

        self._mode_cache = effective_mode

        orders: List[CoreOrder] = []
        if prev_close is not None:
            eff_state = replace(state, mode=effective_mode)
            last5 = self._recent_closes[-5:]
            specs = build_orders(eff_state, prev_close, last5, reverse_first_day)
            orders = [self._to_core_order(s) for s in specs]

        # 다음 호출을 위한 이력 갱신 (오늘 종가는 "내일의 전일종가").
        self._prev_close = bar.close
        self._recent_closes.append(bar.close)
        if len(self._recent_closes) > 5:
            self._recent_closes = self._recent_closes[-5:]

        return orders

    def _to_core_order(self, spec: MumaeOrderSpec) -> CoreOrder:
        price = None if spec.type == OrderType.MOC else spec.price
        return CoreOrder(
            ticker=self.ticker,
            side=spec.side,
            type=spec.type,
            price=price,
            qty=spec.quantity,
            role=spec.role,
        )

    def on_fill(self, state: MumaeState, fills: List[CoreFill]) -> MumaeState:
        mode_for_today = self._mode_cache if self._mode_cache is not None else state.mode
        state_in = replace(state, mode=mode_for_today)
        mfills = [
            MumaeFill(role=f.order.role, side=f.order.side, price=f.price, quantity=f.order.qty, fee=f.fee)
            for f in fills
            if f.order.ticker == self.ticker
        ]
        if not mfills:
            self._mode_cache = state_in.mode
            return state_in
        new_state, _realized, _cycle_closed = apply_fills(state_in, mfills)
        self._mode_cache = new_state.mode
        return new_state
