"""종목 선정 전략.

★ 모압매수 로직 통합 지점 ★
현재는 config/orders.yaml 에 적힌 종목/수량을 그대로 사용한다.
데스크탑 C:\\dev 의 모압매수 앱 로직을 이 저장소에 올리면,
select_orders() 내부를 그 계산 로직으로 교체하면 된다.
(반환 형식만 list[OrderSpec] 으로 유지하면 나머지 파이프라인은 그대로 동작)
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import BASE_DIR
from .kis_client import KisClient

ORDERS_YAML = BASE_DIR / "config" / "orders.yaml"


@dataclass
class OrderSpec:
    side: str        # "buy" | "sell"
    symbol: str
    exchange: str    # NASD | NYSE | AMEX
    qty: int
    price: float     # 지정가 (USD)


def _resolve_price(client: KisClient, item: dict) -> float:
    """price 가 지정돼 있으면 그대로, 없으면 현재가에 limit_offset_pct 를 적용."""
    if item.get("price"):
        return float(item["price"])
    current = client.get_price(item.get("exchange", "NASD"), item["symbol"])
    offset = float(item.get("limit_offset_pct", 0)) / 100.0
    return round(current * (1 + offset), 2)


def select_orders(client: KisClient, yaml_path: Path = ORDERS_YAML) -> list[OrderSpec]:
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    specs: list[OrderSpec] = []
    for side in ("buy", "sell"):
        for item in cfg.get(side) or []:
            specs.append(OrderSpec(
                side=side,
                symbol=item["symbol"],
                exchange=item.get("exchange", "NASD"),
                qty=int(item["qty"]),
                price=_resolve_price(client, item),
            ))
    return specs
