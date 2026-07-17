"""C2. TQQQ 200일선 추세추종 (catalog/C2-200일선-추세추종.md §2 "1차 구현 스펙" 구현).

종가가 200일 SMA 상단 밴드 위로 복귀하면 전액 매수(HOLD), 하단 밴드 아래로 이탈하면
전량 매도(CASH). 밴드=0이면 단순 상/하회 교차, 밴드>0이면 히스테리시스(whipsaw 완화).

## 채택 가정 (catalog "미확정/가정 항목" §3 그대로 + 이 구현이 추가로 확정한 것)

1. **판정=당일 MOC 체결**: catalog 가정 2 그대로 — 종가로 판정한 그날 MOC로 접수해
   같은 날 종가에 체결(선행편향 없음, engine.py가 이미 그날 bar.close를 on_bar에
   넘겨준 뒤 broker_sim이 같은 close로 체결하므로 자연히 일치).
2. **SMA200 = 당일 종가를 포함한 직전 200개 종가의 단순평균** (window은
   `[t-199, t]` 닫힌 구간, 당일 포함). catalog는 "당일 종가 기준"이라고만 쓰고 당일
   포함 여부를 명시하지 않아 이 구현이 확정한 값 — "종가 확정 후 판정"이라는 catalog의
   같은 날 체결 가정과 정합적이도록 당일 종가를 SMA에 포함시켰다.
3. **밴드 방식 = 히스테리시스**: catalog 가정 3 그대로. CASH→HOLD는
   `close > sma*(1+band)`, HOLD→CASH는 `close < sma*(1-band)` (엄격 부등호, catalog
   mode_transition 표 그대로).
4. **워밍업(200거래일 미만)**: catalog backtest_notes 그대로 — SMA를 계산할 200개
   과거 종가가 없는 기간은 NO_ACTION(주문 없음, CASH 상태 유지). 그래서 이 전략은
   `price_history`(SMA 계산용 전체 과거 시세)를 생성자에서 미리 받아 자체 보관한다 —
   `Strategy.on_bar`는 그날 하루치 bar만 받으므로, 200일 이동평균처럼 "여러 날짜의
   과거 값"이 필요한 지표는 engine이 순간순간 넘겨주는 하루짜리 bar만으로는 계산할 수
   없다. 이는 PLAN.md §4.2의 "state는 on_fill에서만 갱신" 규칙과는 무관한 별개 문제 —
   `price_history`는 전략의 매매 상태(state)가 아니라 이미 확정된 과거 시세를 읽기
   전용으로 참조하는 지표 계산용 데이터일 뿐이라 그 규칙의 적용 대상이 아니다(미래
   데이터를 보는 것이 아니라 각 날짜 시점에 그 이전 데이터만 사용하므로 선행편향도 없음).
5. **매수 수량에 수수료 버퍼 적용**: catalog rounding 표는 `floor(cash/price)`만
   명시하지만 DCA와 같은 이유로 `_util.max_affordable_qty`를 사용한다.
6. **대기 자산 = 순수 현금(이자 0)**: catalog 가정 4 그대로, SHY 옵션은 미구현.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

_BACKTESTER_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from broker_sim import DEFAULT_FEE_RATE  # noqa: E402
from core import Fill, OHLC, Order, OrderType, PortfolioView, Side, Strategy  # noqa: E402

from strategies._util import max_affordable_qty  # noqa: E402

POSITION_HOLD = "HOLD"
POSITION_CASH = "CASH"


@dataclass
class SMA200State:
    position: str = POSITION_CASH
    qty: int = 0
    entry_price: Optional[Decimal] = None


class SMA200Strategy(Strategy):
    """TQQQ 단일종목 200일선 추세추종.

    price_history: SMA 계산용 전체 과거(및 백테스트 구간) OHLC 리스트 — 백테스트
    시작일 이전 최소 `sma_window_days`개의 워밍업 데이터를 포함해야 워밍업 기간 없이
    시작일부터 바로 신호가 나온다(포함하지 않으면 그만큼 워밍업 기간이 자동으로
    NO_ACTION 처리된다 — catalog backtest_notes의 워밍업 요구사항).
    """

    def __init__(
        self,
        ticker: str,
        price_history: List[OHLC],
        sma_window_days: int = 200,
        whipsaw_band_pct: Decimal = Decimal("0"),
        fee_rate_hint: Decimal = DEFAULT_FEE_RATE,
    ) -> None:
        self.ticker = ticker
        self.sma_window_days = sma_window_days
        self.whipsaw_band_pct = (
            whipsaw_band_pct if isinstance(whipsaw_band_pct, Decimal) else Decimal(str(whipsaw_band_pct))
        )
        self.fee_rate_hint = fee_rate_hint

        sorted_bars = sorted(price_history, key=lambda b: b.date)
        self._dates: List[Date] = [b.date for b in sorted_bars]
        self._closes: List[Decimal] = [b.close for b in sorted_bars]
        self._date_index: Dict[Date, int] = {d: i for i, d in enumerate(self._dates)}
        self._sma: List[Optional[Decimal]] = self._precompute_sma()

    def _precompute_sma(self) -> List[Optional[Decimal]]:
        n = len(self._closes)
        w = self.sma_window_days
        out: List[Optional[Decimal]] = [None] * n
        if n == 0:
            return out
        running = Decimal("0")
        for i in range(n):
            running += self._closes[i]
            if i >= w:
                running -= self._closes[i - w]
            if i >= w - 1:
                out[i] = running / Decimal(w)
        return out

    @staticmethod
    def initial_state() -> SMA200State:
        return SMA200State()

    def on_bar(
        self, state: SMA200State, bars: Dict[str, OHLC], portfolio: PortfolioView
    ) -> List[Order]:
        bar = bars.get(self.ticker)
        if bar is None:
            return []
        today = bar.date
        idx = self._date_index.get(today)
        if idx is None:
            return []
        sma = self._sma[idx]
        if sma is None:
            return []  # 워밍업 기간(200거래일 미만) — NO_ACTION

        close = bar.close
        upper = sma * (Decimal("1") + self.whipsaw_band_pct)
        lower = sma * (Decimal("1") - self.whipsaw_band_pct)

        if state.position == POSITION_CASH and close > upper:
            qty = max_affordable_qty(portfolio.cash, close, self.fee_rate_hint)
            if qty > 0:
                return [Order(self.ticker, Side.BUY, OrderType.MOC, None, qty, "TREND_ENTER")]
        elif state.position == POSITION_HOLD and close < lower:
            held = portfolio.position(self.ticker).qty
            if held > 0:
                return [Order(self.ticker, Side.SELL, OrderType.MOC, None, held, "TREND_EXIT")]
        return []

    def on_fill(self, state: SMA200State, fills: List[Fill]) -> SMA200State:
        position = state.position
        qty = state.qty
        entry_price = state.entry_price
        for f in fills:
            if f.order.role == "TREND_ENTER":
                position = POSITION_HOLD
                qty = int(f.order.qty)
                entry_price = f.price
            elif f.order.role == "TREND_EXIT":
                position = POSITION_CASH
                qty = 0
                entry_price = None
        return SMA200State(position=position, qty=qty, entry_price=entry_price)
