"""E2. HFEA — UPRO 55% / TMF 45% 분기 리밸런싱 (catalog/E2-HFEA.md 구현 스펙 §"구현 스펙
요약" 그대로).

## 채택 가정 (catalog 그대로 + 이 구현이 확정한 것)

1. **목표비중 = UPRO 55% / TMF 45%** (2019-08 개정 이후 확정 규칙, catalog 표 그대로).
2. **분기 첫 거래일 = "이번 분기를 아직 리밸런싱하지 않았는데 오늘이 그 분기에 속하는
   첫 on_bar 호출인 날"**로 판정한다. 엔진이 거래일 순서대로 정확히 한 번씩 `on_bar`를
   호출하므로(engine.py), 특정 (year, quarter) 키를 처음 만나는 날이 정의상 그 분기의
   첫 거래일이다 — 별도의 거래소 휴장일 캘린더 조회 없이 catalog의 "1·4·7·10월 첫
   거래일" 규칙을 정확히 재현한다(달력월 1~3→Q1, 4~6→Q2, 7~9→Q3, 10~12→Q4이므로 분기
   경계가 그대로 1/4/7/10월 경계와 일치).
3. **초기 진입 = 시작일을 최초 리밸런싱으로 취급**: `state.last_rebalance_quarter`의
   초기값은 `None`이라 시작일이 어느 달이든(1/4/7/10월이 아니어도) 첫 `on_bar` 호출에서
   무조건 리밸런싱(=최초 목표비중 진입)이 트리거된다 — catalog "초기 진입은 시작일에
   목표 비중으로" 그대로.
4. **정수 주 내림 + 잔여현금 자연 이월**: `target_qty = floor(target_value/price)`,
   두 종목 모두 절사 후 남는 금액은 `portfolio.cash`에 그대로 남아 다음 분기
   `total_value` 계산에 자동 포함된다(catalog 구현 스펙 요약 그대로 — 별도 carry_cash
   상태 불필요).
5. **한쪽 다리만 체결돼도 그 분기는 완료 처리**: 두 종목 중 한쪽이 현금 부족 등으로
   거부되더라도(드묾 — 매도가 먼저 반영되어 매수 재원이 되므로), 다른 쪽이 체결되면
   `on_fill`이 호출되어 그 분기는 리밸런싱 완료로 표시한다(다음 분기까지 재시도하지
   않음). 두 종목 모두 delta=0이라 이번 분기에 주문 자체가 하나도 없는 극단적인 경우는
   `on_fill`이 호출되지 않아 다음 거래일에도 재시도되는데, 하루만 지나도 가격이
   움직여 delta가 0이 아니게 될 가능성이 높아 실질적 영향은 미미함(가정, catalog에
   없는 구현상 알려진 한계).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date as Date
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_BACKTESTER_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from core import Fill, OHLC, Order, OrderType, PortfolioView, Side, Strategy, round_cents  # noqa: E402

DEFAULT_TARGET_WEIGHTS: Dict[str, Decimal] = {"UPRO": Decimal("0.55"), "TMF": Decimal("0.45")}

QuarterKey = Tuple[int, int]


def quarter_key(d: Date) -> QuarterKey:
    return (d.year, (d.month - 1) // 3 + 1)


@dataclass
class HFEAState:
    last_rebalance_quarter: Optional[QuarterKey] = None
    last_rebalance_date: Optional[Date] = None


class HFEAStrategy(Strategy):
    def __init__(self, target_weights: Optional[Dict[str, Decimal]] = None) -> None:
        self.target_weights = target_weights or dict(DEFAULT_TARGET_WEIGHTS)
        total = sum(self.target_weights.values())
        if total != Decimal("1"):
            raise ValueError(f"target_weights 합은 1이어야 합니다: {total}")

    @staticmethod
    def initial_state() -> HFEAState:
        return HFEAState()

    def on_bar(
        self, state: HFEAState, bars: Dict[str, OHLC], portfolio: PortfolioView
    ) -> List[Order]:
        tickers = list(self.target_weights.keys())
        if not all(t in bars for t in tickers):
            return []  # 두 종목 모두 그날 시세가 있어야 리밸런싱 가능

        today = bars[tickers[0]].date
        q_key = quarter_key(today)
        if state.last_rebalance_quarter == q_key:
            return []  # 이번 분기는 이미 리밸런싱 완료

        total_value = portfolio.cash + sum(
            portfolio.position(t).qty * bars[t].close for t in tickers
        )
        if total_value <= 0:
            return []

        orders: List[Order] = []
        for ticker, weight in self.target_weights.items():
            price = bars[ticker].close
            if price <= 0:
                continue
            target_value = round_cents(total_value * weight)
            target_qty = int((target_value / price).to_integral_value(rounding=ROUND_DOWN))
            current_qty = portfolio.position(ticker).qty
            delta = target_qty - current_qty
            if delta > 0:
                orders.append(Order(ticker, Side.BUY, OrderType.MOC, None, delta, "REBAL_BUY"))
            elif delta < 0:
                orders.append(Order(ticker, Side.SELL, OrderType.MOC, None, -delta, "REBAL_SELL"))
        return orders

    def on_fill(self, state: HFEAState, fills: List[Fill]) -> HFEAState:
        rebalance_date = fills[0].date
        return HFEAState(
            last_rebalance_quarter=quarter_key(rebalance_date),
            last_rebalance_date=rebalance_date,
        )
