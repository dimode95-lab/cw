"""백테스터 공용 타입 정의.

PLAN.md §4.2의 핵심 인터페이스 계약을 코드로 명문화한다.

엔진(engine.py)-전략(strategies/*) 사이의 책임 경계:

1. 엔진은 거래일마다 정확히 한 번 `Strategy.on_bar(state, bars, portfolio)`를 호출해
   그날 걸 주문 목록(list[Order])을 받는다. 2주/월간 단위로만 매매하는 전략(VR5.0 등)도
   `on_bar`는 매일 호출되며, 평가일 여부 판단은 전략 내부(state에 보관한 마지막 평가일 등)
   책임이다 — 엔진은 캘린더 스킵을 하지 않는다.
2. 엔진은 broker_sim으로 그 주문들의 체결 여부/가격을 판정하고, 체결된 것만 Portfolio에
   반영한다(현금 차감/증가, 보유수량·평단 갱신). **Portfolio는 엔진이 소유한다.**
   전략에 넘어가는 것은 `Portfolio.snapshot()`이 만드는 읽기 전용 `PortfolioView`뿐이며,
   전략은 이를 통해 현재 현금/보유현황을 "참고"만 할 수 있고 직접 변경할 수 없다
   (dataclass가 frozen이고 positions는 MappingProxyType이라 실수로도 변경 불가).
3. 그날 체결이 하나라도 있었다면, 엔진은 그날 발생한 Fill 전체를 모아
   `Strategy.on_fill(state, fills)`를 **하루에 정확히 1회** 호출한다. 체결마다 여러 번
   호출하지 않는다 — 무한매수법처럼 "같은 날 별지점 절반 매수 + 평단 절반 매수가
   동시에 체결되면 T값이 +1(개별이면 각각 +0.5가 아니라 합쳐서 +1)"처럼, 같은 날 체결들의
   *조합*에 의존해 상태를 비선형적으로 갱신하는 전략을 재현하려면 이 "일괄 1회 통지"
   계약이 필수적이다 (MumaeEngine.applyFills와 동일한 사상).
4. 전략 고유 상태(state — Strategy 구현체가 정의하는 임의의 객체, 예: T값·모드·마지막
   평가일)는 **on_fill 안에서만 갱신**한다. `on_bar`는 state를 읽어 주문을 만들 뿐,
   반환값 외의 부수효과로 state를 변형해서는 안 된다. 이렇게 소유권을 분리해야
   "체결 안 된 주문은 상태에 영향을 주지 않는다"는 규칙이 코드 구조로 보장된다.

금액은 전부 `decimal.Decimal`을 쓴다 (문자열 경유 생성 권장: `Decimal(str(x))`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as Date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Union


def round_cents(amount: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    """센트(소수점 2자리) 단위로 반올림. 기본은 ROUND_HALF_UP.

    broker_sim.py의 수수료 계산, Portfolio의 평단 계산 등 금액이 등장하는 모든
    곳에서 이 함수를 통일해서 쓴다.
    """
    return amount.quantize(Decimal("0.01"), rounding=rounding)


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LOC = "LOC"    # 종가지정가: 매수는 종가<=지정가, 매도는 종가>=지정가일 때 종가 체결
    MOC = "MOC"    # 종가시장가: 무조건 종가 체결
    LIMIT = "LIMIT"  # 지정가: 정규장 고저 범위로 판정, 체결가는 지정가(보수적 가정)
    MKT = "MKT"    # 시장가: 시가 체결


@dataclass
class Order:
    """전략이 하루에 내는 주문 1건.

    qty는 기본적으로 int(정수 주)지만, Grid Trading처럼 소수 단위 lot을 쓰는 전략을
    위해 Decimal도 허용한다 — 이 경우 fractional=True로 표시해 broker_sim/engine이
    수량 연산에서 int 캐스팅을 하지 않도록 한다.
    """

    ticker: str
    side: Side
    type: OrderType
    price: Optional[Decimal]  # MOC/MKT는 None (가격 조건 없음)
    qty: Union[int, Decimal]
    role: str  # 전략별 논리 역할 태그 (예: "STAR_HALF_BUY") — on_fill에서 상태갱신의 키
    fractional: bool = False  # True면 qty가 Decimal(소수 lot 허용)


@dataclass
class Fill:
    """체결 1건 = Order + 체결가/일자/수수료."""

    order: Order
    price: Decimal
    date: Date
    fee: Decimal


@dataclass
class OHLC:
    """일봉 1개. 체결가 판정은 원종가(raw close) 기준 — 수정종가 아님(PLAN §4.3)."""

    date: Date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    dividend: Decimal = Decimal("0")  # 그날의 주당 배당금(배당락일 등). 없으면 0.


@dataclass(frozen=True)
class PositionSnapshot:
    """특정 티커의 보유 현황 스냅샷 (읽기 전용)."""

    qty: int
    avg_price: Decimal


_ZERO_POSITION = PositionSnapshot(qty=0, avg_price=Decimal("0"))


@dataclass(frozen=True)
class PortfolioView:
    """전략에 전달되는 읽기 전용 포트폴리오 스냅샷.

    frozen dataclass + MappingProxyType이라 전략 코드가 실수로라도 필드를 바꾸거나
    positions 딕셔너리에 값을 넣을 수 없다. 실제 갱신은 엔진이 Portfolio(비-view)를
    통해서만 수행한다.
    """

    cash: Decimal
    positions: Mapping[str, PositionSnapshot]

    def position(self, ticker: str) -> PositionSnapshot:
        return self.positions.get(ticker, _ZERO_POSITION)


class Portfolio:
    """엔진이 소유하는 실제 포트폴리오 (가변). 전략에는 절대 이 객체 자체를 넘기지 않는다
    — 반드시 snapshot()으로 만든 PortfolioView만 넘긴다.
    """

    def __init__(self, cash: Decimal):
        self.cash: Decimal = cash
        self._positions: Dict[str, PositionSnapshot] = {}

    def position(self, ticker: str) -> PositionSnapshot:
        return self._positions.get(ticker, _ZERO_POSITION)

    def snapshot(self) -> PortfolioView:
        return PortfolioView(
            cash=self.cash,
            positions=MappingProxyType(dict(self._positions)),
        )

    # ---- 엔진 전용 갱신 메서드 (전략에서 직접 호출 금지) ----

    def apply_buy(self, ticker: str, qty: Union[int, Decimal], price: Decimal, fee: Decimal) -> None:
        cur = self.position(ticker)
        cost = price * qty
        new_qty = cur.qty + qty
        new_total_cost = cur.avg_price * cur.qty + cost
        new_avg = (new_total_cost / new_qty) if new_qty else Decimal("0")

        self._positions[ticker] = PositionSnapshot(qty=new_qty, avg_price=round_cents(new_avg))
        self.cash = self.cash - cost - fee

    def apply_sell(self, ticker: str, qty: Union[int, Decimal], price: Decimal, fee: Decimal) -> Decimal:
        """매도를 반영하고 이 체결의 실현손익을 반환한다."""
        cur = self.position(ticker)
        proceeds = price * qty
        realized = proceeds - cur.avg_price * qty - fee
        new_qty = cur.qty - qty
        new_avg = cur.avg_price if new_qty else Decimal("0")
        self._positions[ticker] = PositionSnapshot(qty=new_qty, avg_price=new_avg)
        self.cash = self.cash + proceeds - fee
        return realized

    def apply_dividend(self, ticker: str, dividend_per_share: Decimal) -> Decimal:
        """배당 발생: 그날 시가 기준이 아니라 보유수량 × 배당금을 현금으로 가산.
        가산된 현금액을 반환한다.
        """
        cur = self.position(ticker)
        if cur.qty <= 0 or dividend_per_share == 0:
            return Decimal("0")
        amount = dividend_per_share * cur.qty
        self.cash = self.cash + amount
        return amount


class Strategy(ABC):
    """전략 구현체가 상속하는 추상 클래스. state는 전략이 자유롭게 정의하는 객체
    (예: dataclass)이며 엔진은 내용을 들여다보지 않고 그대로 보관·전달만 한다.
    """

    @abstractmethod
    def on_bar(self, state: Any, bars: Dict[str, OHLC], portfolio: PortfolioView) -> List[Order]:
        """오늘 걸 주문 목록을 반환한다. state를 변형하지 않는다(읽기만)."""
        raise NotImplementedError

    @abstractmethod
    def on_fill(self, state: Any, fills: List[Fill]) -> Any:
        """오늘 발생한 체결 전체(1회 호출)를 받아 새 state를 반환한다.
        fills가 비어 있으면 엔진이 이 메서드를 호출하지 않는다(그날 체결 없음).
        """
        raise NotImplementedError
