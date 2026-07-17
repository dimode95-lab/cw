"""D1. DCA — 정액 적립식 분할매수 (catalog/D1-DCA.md 채택 가정 구현).

기준선(baseline) 전략. 회당 정해진 금액을 정해진 주기마다 MOC로 매수한다. 럼프섬
(lump_sum=True) 변형은 시작일에 가용 현금 전액을 1회 투입한다.

## 채택 가정 (catalog 명세 + 이 구현이 추가로 확정한 것)

1. **주기 = "거래일수" 파라미터를 달력일로 근사 환산해 스케줄링**: PLAN 오케스트레이션
   지시는 `interval_trading_days`(기본 10)를 파라미터로 요구하지만, 엔진 계약
   (core.py: "state는 on_fill 안에서만 갱신")상 전략은 체결이 없는 날엔 state를 바꿀 수
   없다 — 즉 "지난 N 거래일을 셌다"를 매일 증분하는 카운터로 정확히 구현할 방법이 없다
   (체결이 발생해야만 state가 갱신되므로, 체결 없는 날들을 세는 부수효과는 금지된
   on_bar 변형에 해당한다). 따라서 거래일수를 `ceil(N×7/5)` 달력일로 근사 환산해
   `next_buy_date`(달력일)로 스케줄을 관리한다. 기본값 10거래일→14달력일(2주)이 되어
   catalog D1-DCA.md의 채택 기본값("2주마다 $X")과 정확히 일치한다. 이 근사는 N이
   클수록(주/격주/월 단위) 정확하고 N=1처럼 아주 작은 값에는 부적합함을 명시(가정).
2. **비거래일 이월**: 스케줄일이 비거래일이면 그 이후 첫 거래일에 체결되고,
   `next_buy_date`는 **원래 스케줄 앵커 + 간격**으로 전진한다(체결 실행일 기준이 아님) —
   catalog가 명시한 "밀린 날짜가 누적되지 않도록 원래 스케줄 기준 유지" 그대로.
3. **잔여 현금 방침 A(기본, idle)/B(carry)**: catalog cash_profile 그대로. 기본은 A —
   잔돈은 그냥 유휴 현금으로 남고 다음 회차 예산에 합산하지 않는다.
4. **매수 수량 계산에 수수료 버퍼 적용**: catalog rounding 표는 `qty=floor(budget/price)`만
   명시하지만, 그대로 하면 수수료만큼 총비용이 budget(또는 가용 현금)을 초과해
   broker_sim이 주문 전체를 거부할 수 있다(부분체결 미모델링) — `_util.max_affordable_qty`로
   수수료까지 포함해 감당 가능한 최대 수량을 계산한다(문서 rounding 규칙의 정신은 유지,
   구현상 안전장치 추가).
5. **lump_sum 변형**: catalog에 없는 이번 태스크 지시사항. 시작일(next_buy_date=start_date)에
   가용 현금 전액으로 1회만 매수하고 이후 `done=True`로 더 이상 주문하지 않는다.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

_BACKTESTER_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from broker_sim import DEFAULT_FEE_RATE  # noqa: E402
from core import Fill, OHLC, Order, OrderType, PortfolioView, Side, Strategy  # noqa: E402

from strategies._util import max_affordable_qty  # noqa: E402

LEFTOVER_A_IDLE = "A_IDLE"
LEFTOVER_B_CARRY = "B_CARRY"


def trading_days_to_calendar_days(trading_days: int) -> int:
    """거래일수를 달력일로 근사 환산 (5거래일≈7달력일, 올림). 위 모듈 docstring 가정 1 참고."""
    return math.ceil(trading_days * 7 / 5)


@dataclass
class DCAState:
    next_buy_date: Date
    carry_cash: Decimal = Decimal("0")
    buy_count: int = 0
    done: bool = False  # lump_sum 모드에서 1회 매수 완료 여부


class DCAStrategy(Strategy):
    def __init__(
        self,
        ticker: str,
        contribution_amount: Decimal,
        interval_trading_days: int = 10,
        leftover_cash_policy: str = LEFTOVER_A_IDLE,
        lump_sum: bool = False,
        fee_rate_hint: Decimal = DEFAULT_FEE_RATE,
    ) -> None:
        self.ticker = ticker
        self.contribution_amount = (
            contribution_amount
            if isinstance(contribution_amount, Decimal)
            else Decimal(str(contribution_amount))
        )
        self.interval_trading_days = interval_trading_days
        self.interval_calendar_days = trading_days_to_calendar_days(interval_trading_days)
        if leftover_cash_policy not in (LEFTOVER_A_IDLE, LEFTOVER_B_CARRY):
            raise ValueError(f"알 수 없는 leftover_cash_policy: {leftover_cash_policy}")
        self.leftover_cash_policy = leftover_cash_policy
        self.lump_sum = lump_sum
        self.fee_rate_hint = fee_rate_hint

    def initial_state(self, start_date: Date) -> DCAState:
        return DCAState(next_buy_date=start_date)

    def on_bar(
        self, state: DCAState, bars: Dict[str, OHLC], portfolio: PortfolioView
    ) -> List[Order]:
        bar = bars.get(self.ticker)
        if bar is None:
            return []
        today = bar.date

        if self.lump_sum:
            if state.done or today < state.next_buy_date:
                return []
            qty = max_affordable_qty(portfolio.cash, bar.close, self.fee_rate_hint)
            if qty <= 0:
                return []
            return [Order(self.ticker, Side.BUY, OrderType.MOC, None, qty, "LUMP_SUM_BUY")]

        if today < state.next_buy_date:
            return []

        budget = self.contribution_amount
        if self.leftover_cash_policy == LEFTOVER_B_CARRY:
            budget += state.carry_cash
        available = min(budget, portfolio.cash)
        qty = max_affordable_qty(available, bar.close, self.fee_rate_hint)
        if qty <= 0:
            return []
        return [Order(self.ticker, Side.BUY, OrderType.MOC, None, qty, "PERIODIC_BUY")]

    def on_fill(self, state: DCAState, fills: List[Fill]) -> DCAState:
        carry_cash = state.carry_cash
        buy_count = state.buy_count
        next_buy_date = state.next_buy_date
        done = state.done

        for f in fills:
            if f.order.role == "PERIODIC_BUY":
                budget = self.contribution_amount + (
                    state.carry_cash if self.leftover_cash_policy == LEFTOVER_B_CARRY else Decimal("0")
                )
                spent = f.price * f.order.qty + f.fee
                leftover = budget - spent
                carry_cash = leftover if self.leftover_cash_policy == LEFTOVER_B_CARRY else Decimal("0")
                buy_count += 1
                next_buy_date = state.next_buy_date + timedelta(days=self.interval_calendar_days)
            elif f.order.role == "LUMP_SUM_BUY":
                buy_count += 1
                done = True

        return DCAState(
            next_buy_date=next_buy_date, carry_cash=carry_cash, buy_count=buy_count, done=done
        )
