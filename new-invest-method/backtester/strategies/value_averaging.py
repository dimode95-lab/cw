"""B2. Value Averaging (Edleson) — catalog/B2-Value-Averaging.md 채택 가정 구현.

월간(이 프로젝트에서는 "거래일 N일 간격"으로 근사, 아래 가정 1 참고) 평가일마다 목표
경로 V_t = C×t×(1+R)^t 대비 부족분을 매수하고(TOPUP_BUY), 초과분을 매도한다
(TRIM_SELL, no_sell=False일 때만). 둘 다 MOC.

## 채택 가정 (catalog "미확정/가정 필요" 절 + 이 구현이 추가로 확정한 것)

1. **평가 주기 = "거래일 N일 간격"(기본 21≈1개월)으로 근사, 실제 거래일 인덱스로 정확히
   카운트**: catalog는 "월간(표준)"이라고 하나 정확한 달력월 경계(월초/월말) 정렬은
   "미확정"(catalog backtest_notes)이라고 명시했다. VR(B1)과 동일한 이유로 — 엔진 계약상
   state는 on_fill에서만 갱신되고, 평가 스케줄은 매매가 없는 날에도 어긋남 없이 매겨져야
   하므로 — `sma200.py`가 확립한 패턴을 그대로 따라 `price_history`로 date→거래일
   인덱스를 미리 만들고 `index % eval_interval_trading_days == 0`인 날을 평가일로 삼는다
   (달력일 근사가 아니라 데이터의 실제 거래일을 그대로 셈).
2. **t, V_t는 완전히 무상태(stateless)로 매번 재계산**: t = 거래일 인덱스 //
   eval_interval_trading_days. V_t = C*t*(1+R)^t는 t만의 순수함수라 매매 이력에 의존하지
   않는다(catalog: "사전에 확정된 지수형 목표선"이라는 VA 고유의 특성과 부합 — VR의 V처럼
   Pool에 의존해 매매 이력에 따라 달라지는 값이 아니다). 따라서 VR과 달리 "밴드 안이면
   V 동결" 같은 특별 처리가 필요 없다 — diff=0인 평가일은 그냥 SKIP(무주문)일 뿐, 다음
   평가일의 V_t 계산에 전혀 영향을 주지 않는다.
3. **V_0=0 자연 처리(catalog 미확정#1의 실무적 해소)**: t=0(백테스트 시작일)에는
   V_0=0이고 보유수량도 0이라 diff=0 → 자연히 무매매. 실질적인 첫 매수는 t=1(첫 평가
   주기)부터 시작한다.
4. **매도대금의 용처(catalog 미확정#3)**: core.Portfolio는 현금 풀이 하나뿐이라, 매도
   대금은 구조적으로 자동 재투자 재원(다음 매수용 가용 현금)이 된다 — 엔진 인터페이스에
   별도 인출 프리미티브가 없어 다른 선택지가 없다.
5. **lot_size = 정수 주(내림)**: catalog는 미확정(펀드 기준 소수 허용 언급)이라고 밝혔으나,
   프로젝트의 다른 전략들과 일관성을 위해 정수 주로 구현한다(과업 지시에도 fractional
   요구 없음).
6. **no_sell 변형**: diff<0이고 no_sell=True면 주문을 내지 않는다(catalog order_roles의
   SKIP 그대로) — side fund는 별도 시뮬레이션하지 않는다(실제 현금은 이미
   portfolio.cash에 남아 있으므로 인위적 가상 구좌를 또 만들 필요가 없다).
7. **현금 부족 시 완충장치 없음(의도적)**: VR의 pool_limit 같은 상한을 두지 않고
   broker_sim의 자연스러운 insufficient_cash 거부에 맡긴다 — catalog risk_notes가
   지적하는 "하락장에서 필요 매수액 급증" 리스크를 그대로 노출하기 위함(의도적으로
   완충장치를 추가하지 않았다).
8. **주문 유형 = MOC**, 반올림은 금액 센트 HALF_UP(V_t), 수량 DOWN(catalog 제안 그대로).
9. **매수 수량에 수수료 버퍼 적용**: `_util.max_affordable_qty` 재사용(DCA/SMA200/VR과
   동일한 이유 — 수수료로 인한 insufficient_cash 통째 거부 방지).
10. **배당**: 엔진이 보유수량×배당을 포트폴리오 현금에 자동 가산하므로(PLAN.md 방침),
    다음 평가일의 diff 계산이 그 늘어난 현금을 자연히 반영한다 — 전략 state가 별도로
    배당을 부기할 필요 없다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date as Date
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Dict, List, Optional

_BACKTESTER_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from broker_sim import DEFAULT_FEE_RATE  # noqa: E402
from core import Fill, OHLC, Order, OrderType, PortfolioView, Side, Strategy, round_cents  # noqa: E402

from strategies._util import max_affordable_qty  # noqa: E402

ROLE_BUY = "VA_BUY"
ROLE_SELL = "VA_SELL"


def target_value(C: Decimal, R: Decimal, t: int) -> Decimal:
    """V_t = C * t * (1+R)^t. t<=0이면 0(가정 3)."""
    if t <= 0:
        return Decimal("0")
    return round_cents(C * t * (Decimal("1") + R) ** t)


@dataclass
class VAState:
    """핵심 로직(t, V_t)은 무상태(날짜만의 함수, 가정 2)라 이 상태는 리포팅/테스트
    편의를 위한 부기 값만 담는다 — Strategy 계약상 필수 필드는 아니다."""

    cumulative_net_invested: Decimal = Decimal("0")  # 누적 순매수금(매수-매도), 참고용
    trade_count: int = 0


class ValueAveragingStrategy(Strategy):
    def __init__(
        self,
        ticker: str,
        price_history: List[OHLC],
        C: Decimal,
        R: Decimal,
        no_sell: bool = False,
        eval_interval_trading_days: int = 21,
        fee_rate_hint: Decimal = DEFAULT_FEE_RATE,
    ) -> None:
        self.ticker = ticker
        self.C = C if isinstance(C, Decimal) else Decimal(str(C))
        self.R = R if isinstance(R, Decimal) else Decimal(str(R))
        self.no_sell = no_sell
        self.eval_interval_trading_days = eval_interval_trading_days
        self.fee_rate_hint = fee_rate_hint

        sorted_bars = sorted(price_history, key=lambda b: b.date)
        self._date_index: Dict[Date, int] = {b.date: i for i, b in enumerate(sorted_bars)}

    @staticmethod
    def initial_state() -> VAState:
        return VAState()

    def _period(self, today: Date) -> Optional[int]:
        idx = self._date_index.get(today)
        if idx is None:
            return None
        return idx // self.eval_interval_trading_days

    def _is_eval_day(self, today: Date) -> bool:
        idx = self._date_index.get(today)
        if idx is None:
            return False
        return idx % self.eval_interval_trading_days == 0

    def on_bar(
        self, state: VAState, bars: Dict[str, OHLC], portfolio: PortfolioView
    ) -> List[Order]:
        bar = bars.get(self.ticker)
        if bar is None or not self._is_eval_day(bar.date):
            return []

        t = self._period(bar.date) or 0
        v_t = target_value(self.C, self.R, t)
        price = bar.close
        qty_held = portfolio.position(self.ticker).qty
        actual_value = price * qty_held
        diff = v_t - actual_value

        if diff > 0:
            budget = diff if diff <= portfolio.cash else portfolio.cash
            qty = max_affordable_qty(budget, price, self.fee_rate_hint)
            if qty > 0:
                return [Order(self.ticker, Side.BUY, OrderType.MOC, None, qty, ROLE_BUY)]
        elif diff < 0 and not self.no_sell:
            qty = int((-diff / price).to_integral_value(rounding=ROUND_DOWN))
            qty = min(qty, qty_held)
            if qty > 0:
                return [Order(self.ticker, Side.SELL, OrderType.MOC, None, qty, ROLE_SELL)]
        return []

    def on_fill(self, state: VAState, fills: List[Fill]) -> VAState:
        cumulative = state.cumulative_net_invested
        count = state.trade_count
        for f in fills:
            if f.order.ticker != self.ticker or f.order.role not in (ROLE_BUY, ROLE_SELL):
                continue
            count += 1
            if f.order.side == Side.BUY:
                cumulative += f.price * f.order.qty + f.fee
            else:
                cumulative -= f.price * f.order.qty - f.fee
        return VAState(cumulative_net_invested=cumulative, trade_count=count)
