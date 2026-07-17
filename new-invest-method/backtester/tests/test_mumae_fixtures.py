"""무한매수법 V4.0 Python 포트(`strategies/mumae.py`) vs MumaeEngine.kt 교차검증.

`tests/fixtures/mumae_fixtures.json`의 25개 항목을 전부 로드해 Python 구현과 대조한다.
픽스처 값 자체는 Kotlin 원본이 기준이므로 수정하지 않는다 — 불일치가 있으면 Python 쪽
구현을 고친다.

실행: `cd backtester && python3 -m unittest tests.test_mumae_fixtures` 또는
`python3 -m unittest discover -s tests`.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_BACKTESTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from core import OrderType, Side  # noqa: E402

from strategies.mumae import (  # noqa: E402
    Mode,
    MumaeFill,
    MumaeState,
    OrderRole,
    apply_fills,
    big_number_cap,
    build_orders,
    final_sell_price,
    one_time_budget,
    reverse_star_price,
    should_enter_reverse,
    should_exit_reverse,
    star_buy_price,
    star_percent,
    star_sell_price,
)

_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "mumae_fixtures.json"


def _state_from_dict(d: dict) -> MumaeState:
    return MumaeState(
        ticker=d["ticker"],
        divisions=int(d["divisions"]),
        principal=Decimal(d["principal"]),
        cash_balance=Decimal(d["cashBalance"]),
        avg_price=Decimal(d["avgPrice"]),
        quantity=int(d["quantity"]),
        t_value=float(d["tValue"]),
        target_rate=float(d["targetRate"]),
        mode=Mode[d["mode"]],
        big_number_rate=float(d["bigNumberRate"]),
    )


def _fill_from_dict(d: dict) -> MumaeFill:
    return MumaeFill(
        role=d["role"],
        side=Side[d["side"]],
        price=Decimal(d["price"]),
        quantity=int(d["quantity"]),
        fee=Decimal(d["fee"]),
    )


class MumaeFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(_FIXTURES_PATH, encoding="utf-8") as f:
            cls.fixtures = json.load(f)

    def test_fixture_count_is_25(self) -> None:
        self.assertEqual(len(self.fixtures["tests"]), 25)

    def test_all_fixtures(self) -> None:
        for entry in self.fixtures["tests"]:
            with self.subTest(entry["test_name"]):
                self._run_entry(entry)

    # ---- 항목별 디스패치 ----

    def _run_entry(self, entry: dict) -> None:
        func = entry["function"]
        inputs = entry["inputs"]
        expected = entry["expected"]
        tol = entry.get("tolerance", {})

        if func == "starPercent":
            state = _state_from_dict(inputs["state"])
            self._assert_float_close(star_percent(state), expected["starPercent"], tol.get("starPercent"))

        elif func == "starSellPrice_starBuyPrice":
            state = _state_from_dict(inputs["state"])
            self.assertEqual(star_sell_price(state), Decimal(expected["starSellPrice"]))
            self.assertEqual(star_buy_price(state), Decimal(expected["starBuyPrice"]))

        elif func == "finalSellPrice":
            state = _state_from_dict(inputs["state"])
            self.assertEqual(final_sell_price(state), Decimal(expected["finalSellPrice"]))

        elif func == "starPercent_starSellPrice":
            state = _state_from_dict(inputs["state"])
            if "starPercent" in expected:
                self._assert_float_close(star_percent(state), expected["starPercent"], tol.get("starPercent"))
            if "starSellPrice" in expected:
                self.assertEqual(star_sell_price(state), Decimal(expected["starSellPrice"]))

        elif func == "oneTimeBudget":
            state = _state_from_dict(inputs["state"])
            actual = one_time_budget(state)
            self._assert_decimal_close(actual, Decimal(expected["oneTimeBudget"]), tol.get("oneTimeBudget", "0.01"))

        elif func == "buildOrders":
            state = _state_from_dict(inputs["state"])
            prev_close = Decimal(inputs["prevClose"])
            last5 = [Decimal(x) for x in inputs.get("last5Closes", [])]
            reverse_first_day = bool(inputs.get("reverseFirstDay", False))
            orders = build_orders(state, prev_close, last5, reverse_first_day)
            self._check_build_orders(state, prev_close, last5, orders, expected, tol)

        elif func == "applyFills":
            state = _state_from_dict(inputs["state"])
            fills = [_fill_from_dict(f) for f in inputs["fills"]]
            new_state, realized, cycle_closed = apply_fills(state, fills)
            if "newState.tValue" in expected:
                self._assert_float_close(
                    new_state.t_value, expected["newState.tValue"], tol.get("newState.tValue")
                )
            if "newState.quantity" in expected:
                self.assertEqual(new_state.quantity, expected["newState.quantity"])
            if "realizedPnl" in expected:
                self.assertEqual(realized, Decimal(expected["realizedPnl"]))
            if "cycleClosed" in expected:
                self.assertEqual(cycle_closed, expected["cycleClosed"])

        elif func == "shouldEnterReverse":
            state = _state_from_dict(inputs["state"])
            self.assertEqual(should_enter_reverse(state), expected["shouldEnterReverse"])

        elif func == "shouldExitReverse":
            state = _state_from_dict(inputs["state"])
            close = Decimal(inputs["close"])
            self.assertEqual(should_exit_reverse(state, close), expected["shouldExitReverse"])

        else:
            self.fail(f"알 수 없는 function: {func}")

    def _check_build_orders(self, state, prev_close, last5, orders, expected, tol) -> None:
        by_role: dict = {}
        for o in orders:
            by_role.setdefault(o.role, []).append(o)

        if "oneTimeBudget" in expected:
            self._assert_decimal_close(
                one_time_budget(state), Decimal(expected["oneTimeBudget"]), tol.get("oneTimeBudget", "0.01")
            )

        if "reverseStarPrice" in expected:
            self.assertEqual(reverse_star_price(last5), Decimal(expected["reverseStarPrice"]))

        if "orders" in expected:
            for role, spec in expected["orders"].items():
                role_orders = by_role.get(role, [])
                if "price" in spec:
                    self.assertTrue(role_orders, f"{role} 주문이 생성되지 않았습니다")
                    self.assertEqual(role_orders[0].price, Decimal(spec["price"]), role)
                if "quantity" in spec:
                    self.assertTrue(role_orders, f"{role} 주문이 생성되지 않았습니다")
                    self.assertEqual(role_orders[0].quantity, spec["quantity"], role)
                if "type" in spec:
                    self.assertTrue(role_orders, f"{role} 주문이 생성되지 않았습니다")
                    self.assertEqual(role_orders[0].type.value, spec["type"], role)
                if "label_contains" in spec:
                    self.assertTrue(role_orders, f"{role} 주문이 생성되지 않았습니다")
                    self.assertIn(spec["label_contains"], role_orders[0].label, role)

        if "LADDER_BUY_first6_prices" in expected:
            ladder_orders = by_role.get(OrderRole.LADDER_BUY, [])
            actual_prices = [o.price for o in ladder_orders[:6]]
            expected_prices = [Decimal(x) for x in expected["LADDER_BUY_first6_prices"]]
            self.assertEqual(actual_prices, expected_prices)

        if "LADDER_BUY_first1_price" in expected:
            ladder_orders = by_role.get(OrderRole.LADDER_BUY, [])
            self.assertTrue(ladder_orders, "LADDER_BUY 주문이 없습니다")
            self.assertEqual(ladder_orders[0].price, Decimal(expected["LADDER_BUY_first1_price"]))

        if "has_order_with_role" in expected:
            for role, should_exist in expected["has_order_with_role"].items():
                exists = bool(by_role.get(role))
                self.assertEqual(exists, should_exist, f"role={role}")

        if expected.get("no_buy_orders"):
            for o in orders:
                self.assertNotEqual(o.side, Side.BUY, "매수 주문이 있으면 안 됩니다")

        if "big_number_cap" in expected:
            cap = big_number_cap(prev_close, state.big_number_rate)
            self.assertEqual(cap, Decimal(expected["big_number_cap"]))

        if expected.get("all_buy_orders_price_lte_cap"):
            cap = big_number_cap(prev_close, state.big_number_rate)
            for o in orders:
                if o.side == Side.BUY and o.type == OrderType.LOC:
                    self.assertLessEqual(o.price, cap)

        if "no_order_label_contains" in expected:
            needle = expected["no_order_label_contains"]
            for o in orders:
                self.assertNotIn(needle, o.label)

    # ---- 비교 헬퍼 ----

    def _assert_float_close(self, actual: float, expected_str: str, tol_str: str | None) -> None:
        expected = float(expected_str)
        tol = float(tol_str) if tol_str is not None else 1e-9
        self.assertLessEqual(abs(actual - expected), tol, f"{actual} != {expected} (tol={tol})")

    def _assert_decimal_close(self, actual: Decimal, expected: Decimal, tol_str: str) -> None:
        tol = Decimal(tol_str)
        self.assertLessEqual(abs(actual - expected), tol, f"{actual} != {expected} (tol={tol})")


if __name__ == "__main__":
    unittest.main()
