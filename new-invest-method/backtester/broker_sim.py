"""체결 판정 (PLAN.md §4.1/§4.4).

판정 규칙 (전량 체결만 — 부분체결 미모델링):
  - LOC 매수: 종가 <= 지정가  → 종가에 체결
  - LOC 매도: 종가 >= 지정가  → 종가에 체결
  - MOC     : 조건 없이 종가에 체결
  - LIMIT 매수: 저가 <= 지정가 → 지정가에 체결 (보수적 가정 — 실제로는 더 낮게
    체결될 수도 있지만, 정규장 고저 범위 판정만으로는 정확한 체결가를 알 수 없으므로
    지정가 그대로를 체결가로 잡는다)
  - LIMIT 매도: 고가 >= 지정가 → 지정가에 체결 (동일한 보수적 가정)
  - MKT     : 조건 없이 시가에 체결

수수료: fee_rate(기본 0.0007) × 체결금액, Decimal ROUND_HALF_UP 센트 반올림.

현금 부족: 매도를 먼저 처리해 그날 들어오는 현금을 먼저 반영한 뒤, 매수는 원래 주문
순서대로 처리하면서 그 시점까지 가용한 현금을 초과하면 그 주문은 거부(체결 없음)한다.
이는 MumaeEngine.applyFills의 "매도 먼저 반영" 관례와 동일하다.
보유 수량보다 많은 매도 주문도 거부한다(공매도 미지원).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal
from typing import Dict, List, Optional

from core import Fill, OHLC, Order, OrderType, Portfolio, Side, round_cents

DEFAULT_FEE_RATE = Decimal("0.0007")


@dataclass
class RejectedOrder:
    order: Order
    reason: str  # "no_fill_price_condition" | "insufficient_cash" | "insufficient_shares" | "no_bar_today"


@dataclass
class FillResult:
    fills: List[Fill]
    rejected: List[RejectedOrder]


def _fill_price(order: Order, bar: OHLC) -> Optional[Decimal]:
    """가격 조건만으로 체결 여부/체결가를 판정. 현금·보유수량 제약은 별도로 검사한다.
    체결 조건을 만족하지 못하면 None.
    """
    if order.type == OrderType.MOC:
        return bar.close
    if order.type == OrderType.MKT:
        return bar.open
    if order.type == OrderType.LOC:
        if order.price is None:
            raise ValueError(f"LOC 주문은 price가 필요합니다: {order}")
        if order.side == Side.BUY:
            return bar.close if bar.close <= order.price else None
        else:
            return bar.close if bar.close >= order.price else None
    if order.type == OrderType.LIMIT:
        if order.price is None:
            raise ValueError(f"LIMIT 주문은 price가 필요합니다: {order}")
        if order.side == Side.BUY:
            return order.price if bar.low <= order.price else None
        else:
            return order.price if bar.high >= order.price else None
    raise ValueError(f"알 수 없는 주문 유형: {order.type}")


def _fee_for(price: Decimal, qty, fee_rate: Decimal) -> Decimal:
    return round_cents(price * qty * fee_rate)


def simulate_day(
    orders: List[Order],
    bars: Dict[str, OHLC],
    portfolio: Portfolio,
    trade_date: Date,
    fee_rate: Decimal = DEFAULT_FEE_RATE,
) -> FillResult:
    """그날의 주문 목록을 체결 판정한다. Portfolio는 읽기만 한다 — 실제 반영(현금/수량
    갱신)은 engine.py가 반환된 FillResult.fills를 바탕으로 수행한다.

    단, "그날 쓸 수 있는 현금"을 매도 선반영으로 시뮬레이션하기 위해 로컬 변수로
    available_cash를 추적할 뿐, portfolio 객체 자체는 변경하지 않는다.
    """
    fills: List[Fill] = []
    rejected: List[RejectedOrder] = []

    sells = [o for o in orders if o.side == Side.SELL]
    buys = [o for o in orders if o.side == Side.BUY]

    available_cash = portfolio.cash

    # 1) 매도 먼저: 보유수량 확인 후 체결 판정. 체결되면 현금이 늘어난다(그날 매수 여력에 반영).
    for order in sells:
        bar = bars.get(order.ticker)
        if bar is None:
            rejected.append(RejectedOrder(order, "no_bar_today"))
            continue
        held_qty = portfolio.position(order.ticker).qty
        if order.qty > held_qty:
            rejected.append(RejectedOrder(order, "insufficient_shares"))
            continue
        price = _fill_price(order, bar)
        if price is None:
            rejected.append(RejectedOrder(order, "no_fill_price_condition"))
            continue
        fee = _fee_for(price, order.qty, fee_rate)
        fills.append(Fill(order=order, price=price, date=trade_date, fee=fee))
        available_cash = available_cash + price * order.qty - fee

    # 2) 매수: 원래 순서대로, 그 시점까지 가용 현금을 넘으면 거부.
    for order in buys:
        bar = bars.get(order.ticker)
        if bar is None:
            rejected.append(RejectedOrder(order, "no_bar_today"))
            continue
        price = _fill_price(order, bar)
        if price is None:
            rejected.append(RejectedOrder(order, "no_fill_price_condition"))
            continue
        fee = _fee_for(price, order.qty, fee_rate)
        total_cost = price * order.qty + fee
        if total_cost > available_cash:
            rejected.append(RejectedOrder(order, "insufficient_cash"))
            continue
        fills.append(Fill(order=order, price=price, date=trade_date, fee=fee))
        available_cash = available_cash - total_cost

    return FillResult(fills=fills, rejected=rejected)
