"""전략 공용 유틸 — DCA/SMA200/HFEA가 공유하는 사이징 헬퍼.

PLAN.md §4.2의 `Strategy.on_bar(state, bars, portfolio)` 시그니처는 fee_rate를
넘기지 않는다. 그런데 "가용 현금(또는 예산) 전액으로 최대한 매수"하는 전략은 가격만으로
수량을 정하면 수수료만큼 총비용이 가용현금을 살짝 초과해 broker_sim.simulate_day가
주문 전체를 insufficient_cash로 통째 거부할 수 있다(부분체결 미모델링이라 전량 거부).
이 헬퍼는 broker_sim과 동일한 수수료 공식(가격×수량×fee_rate, ROUND_HALF_UP 센트)을
재현해 이 거부를 방지한다 — broker_sim.py/core.py는 수정하지 않고 그대로 재사용.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from broker_sim import DEFAULT_FEE_RATE
from core import round_cents


def max_affordable_qty(
    available_cash: Decimal, price: Decimal, fee_rate: Decimal = DEFAULT_FEE_RATE
) -> int:
    """available_cash로 (가격+수수료 포함) 살 수 있는 최대 정수 주 수량.

    1) price*(1+fee_rate)로 나눈 근사치를 내림해 후보를 구하고,
    2) broker_sim과 동일한 수수료 반올림 오차로 여전히 초과하면 1주씩 줄여
       "이 qty로 주문하면 절대 insufficient_cash로 거부되지 않음"을 보장한다.
    """
    if price is None or price <= 0 or available_cash is None or available_cash <= 0:
        return 0
    approx = (available_cash / (price * (Decimal("1") + fee_rate))).to_integral_value(
        rounding=ROUND_DOWN
    )
    qty = int(approx)
    while qty > 0:
        fee = round_cents(price * qty * fee_rate)
        if price * qty + fee <= available_cash:
            break
        qty -= 1
    return max(qty, 0)
