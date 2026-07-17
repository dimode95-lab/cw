"""DCA / SMA200(TQQQ 200일선) / HFEA 단위테스트 — 소형 손계산 시나리오.

각 전략의 on_bar/on_fill을 직접 호출해 핵심 계산(수량 산정, 교차·밴드 판정, 리밸런싱
수량)을 수기 계산값과 대조한다. 엔진(engine.py)을 거치지 않고 core.py의 Portfolio를
빌려 PortfolioView만 만들어 쓴다(전략 인터페이스만 검증하는 것이 목적이라 broker_sim의
체결 판정/거부 로직은 이 테스트의 관심사가 아니다 — on_bar가 만드는 Order 자체의
side/type/qty/role이 맞는지만 확인한다).

실행: `cd backtester && python3 -m unittest tests.test_trio` 또는
      `python3 -m unittest discover -s tests`
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal

_BACKTESTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from core import OHLC, OrderType, Portfolio, Side  # noqa: E402

from strategies.dca import DCAState, DCAStrategy  # noqa: E402
from strategies.hfea import HFEAState, HFEAStrategy, quarter_key  # noqa: E402
from strategies.sma200 import SMA200State, SMA200Strategy  # noqa: E402


def bar(d, close, o=None, h=None, l=None):
    c = Decimal(str(close))
    return OHLC(
        date=d,
        open=Decimal(str(o)) if o is not None else c,
        high=Decimal(str(h)) if h is not None else c,
        low=Decimal(str(l)) if l is not None else c,
        close=c,
    )


def view(cash, positions=None):
    """positions: {ticker: (qty, avg_price)}.

    apply_buy()는 현금도 함께 차감하므로(실제 매수를 재현), 포지션만 세팅하고
    cash는 테스트가 원하는 값으로 마지막에 덮어쓴다.
    """
    p = Portfolio(cash=Decimal("0"))
    for ticker, (qty, avg_price) in (positions or {}).items():
        if qty > 0:
            p.apply_buy(ticker, qty, Decimal(str(avg_price)), Decimal("0"))
    p.cash = Decimal(str(cash))
    return p.snapshot()


def business_dates(start: date, n: int):
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# DCA
# ---------------------------------------------------------------------------


class DCAQtyCalculationTests(unittest.TestCase):
    def test_periodic_buy_qty_is_floor_budget_over_price_with_fee_headroom(self):
        strat = DCAStrategy(ticker="TQQQ", contribution_amount=Decimal("1000"))
        d0 = date(2024, 1, 2)
        state = strat.initial_state(start_date=d0)
        bars = {"TQQQ": bar(d0, "97.30")}
        orders = strat.on_bar(state, bars, view(cash="100000"))

        self.assertEqual(len(orders), 1)
        o = orders[0]
        self.assertEqual(o.side, Side.BUY)
        self.assertEqual(o.type, OrderType.MOC)
        self.assertEqual(o.role, "PERIODIC_BUY")
        # floor(1000/97.30) = 10; 10주*97.30=973.00 + 수수료 0.68 = 973.68 <= 1000
        self.assertEqual(o.qty, 10)

    def test_before_scheduled_date_no_order(self):
        strat = DCAStrategy(ticker="TQQQ", contribution_amount=Decimal("1000"))
        state = strat.initial_state(start_date=date(2024, 1, 10))
        bars = {"TQQQ": bar(date(2024, 1, 5), "50")}
        orders = strat.on_bar(state, bars, view(cash="100000"))
        self.assertEqual(orders, [])

    def test_on_fill_advances_next_buy_date_from_anchor_not_execution_date(self):
        # next_buy_date가 토요일(비거래일)이면 다음 거래일(월요일)에 체결되지만,
        # 다음 스케줄은 "체결일+14일"이 아니라 "원래 앵커(토요일)+14일"이어야 한다.
        strat = DCAStrategy(ticker="TQQQ", contribution_amount=Decimal("1000"), interval_trading_days=10)
        self.assertEqual(strat.interval_calendar_days, 14)  # ceil(10*7/5)

        anchor = date(2024, 1, 6)  # 토요일
        state = DCAState(next_buy_date=anchor)
        execution_day = date(2024, 1, 8)  # 월요일 (그 주 첫 거래일)
        bars = {"TQQQ": bar(execution_day, "10.00")}
        orders = strat.on_bar(state, bars, view(cash="100000"))
        self.assertEqual(len(orders), 1)

        fills = _fake_fills(orders[0], price=Decimal("10.00"), d=execution_day, fee=Decimal("0.07"))
        new_state = strat.on_fill(state, fills)

        self.assertEqual(new_state.next_buy_date, anchor + timedelta(days=14))
        self.assertNotEqual(new_state.next_buy_date, execution_day + timedelta(days=14))

    def test_leftover_cash_policy_a_idle_discards_leftover(self):
        strat = DCAStrategy(
            ticker="TQQQ",
            contribution_amount=Decimal("1000"),
            leftover_cash_policy="A_IDLE",
        )
        state = DCAState(next_buy_date=date(2024, 1, 2))
        bars = {"TQQQ": bar(date(2024, 1, 2), "97.30")}
        orders = strat.on_bar(state, bars, view(cash="100000"))
        fills = _fake_fills(orders[0], price=Decimal("97.30"), d=date(2024, 1, 2), fee=Decimal("0.68"))
        new_state = strat.on_fill(state, fills)
        self.assertEqual(new_state.carry_cash, Decimal("0"))

    def test_leftover_cash_policy_b_carries_forward_to_next_budget(self):
        strat = DCAStrategy(
            ticker="TQQQ",
            contribution_amount=Decimal("1000"),
            leftover_cash_policy="B_CARRY",
        )
        state = DCAState(next_buy_date=date(2024, 1, 2), carry_cash=Decimal("50.00"), buy_count=3)
        bars = {"TQQQ": bar(date(2024, 1, 2), "97.30")}
        orders = strat.on_bar(state, bars, view(cash="100000"))
        # 예산 = 1000 + 이월 50 = 1050 -> floor(1050/97.30)=10 (1050 상한 때문에 11주는 불가)
        self.assertEqual(orders[0].qty, 10)

        spent = Decimal("97.30") * 10 + Decimal("0.68")
        fills = _fake_fills(orders[0], price=Decimal("97.30"), d=date(2024, 1, 2), fee=Decimal("0.68"))
        new_state = strat.on_fill(state, fills)
        expected_leftover = (Decimal("1000") + Decimal("50.00")) - spent
        self.assertEqual(new_state.carry_cash, expected_leftover)
        self.assertEqual(new_state.buy_count, 4)

    def test_lump_sum_buys_once_with_all_cash_then_stops(self):
        strat = DCAStrategy(
            ticker="TQQQ", contribution_amount=Decimal("0"), lump_sum=True
        )
        d0 = date(2024, 1, 2)
        state = strat.initial_state(start_date=d0)
        bars = {"TQQQ": bar(d0, "100.00")}
        orders = strat.on_bar(state, bars, view(cash="20000"))
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].role, "LUMP_SUM_BUY")
        # floor(20000/(100*1.0007)) = floor(199.86) = 199
        self.assertEqual(orders[0].qty, 199)

        fills = _fake_fills(orders[0], price=Decimal("100.00"), d=d0, fee=Decimal("13.93"))
        new_state = strat.on_fill(state, fills)
        self.assertTrue(new_state.done)

        # 다음 거래일에는 done=True라 더 이상 주문하지 않는다
        bars2 = {"TQQQ": bar(date(2024, 1, 3), "101.00")}
        orders2 = strat.on_bar(new_state, bars2, view(cash="6.07"))
        self.assertEqual(orders2, [])


def _fake_fills(order, price, d, fee):
    from core import Fill

    return [Fill(order=order, price=price, date=d, fee=fee)]


# ---------------------------------------------------------------------------
# SMA200
# ---------------------------------------------------------------------------


class SMA200Tests(unittest.TestCase):
    def setUp(self):
        self.dates = business_dates(date(2020, 1, 1), 220)
        # 처음 200개는 종가 100 고정(워밍업 채우기), 이후 20개는 100에서 119까지 상승
        closes = [Decimal("100")] * 200 + [Decimal(100 + i) for i in range(20)]
        self.closes = closes
        self.price_history = [bar(d, c) for d, c in zip(self.dates, closes)]

    def test_warmup_period_produces_no_orders_regardless_of_price(self):
        # 200개 미만(150개)만 넣으면 어떤 날짜도 SMA를 계산할 수 없어야 한다
        short_history = self.price_history[:150]
        strat = SMA200Strategy(ticker="TQQQ", price_history=short_history)
        state = SMA200State()
        last_date = short_history[-1].date
        bars = {"TQQQ": bar(last_date, "10000")}  # 극단적으로 높은 종가를 줘도
        orders = strat.on_bar(state, bars, view(cash="100000"))
        self.assertEqual(orders, [])

    def test_sma_matches_naive_trailing_200_average_including_today(self):
        strat = SMA200Strategy(ticker="TQQQ", price_history=self.price_history)
        idx = 219  # 마지막 날
        naive_sma = sum(self.closes[idx - 199 : idx + 1]) / Decimal(200)
        self.assertEqual(strat._sma[idx], naive_sma)
        # 첫 신호 가능일(index 199, 200번째 종가)의 SMA는 앞 200개(전부 100)의 평균 = 100
        self.assertEqual(strat._sma[199], Decimal("100"))

    def test_band_zero_enters_on_simple_cross_above_sma(self):
        strat = SMA200Strategy(ticker="TQQQ", price_history=self.price_history, whipsaw_band_pct=Decimal("0"))
        idx = 219
        sma = strat._sma[idx]
        d = self.dates[idx]

        # sma 바로 위 -> 진입
        above = bar(d, sma * Decimal("1.01"))
        orders = strat.on_bar(SMA200State(position="CASH"), {"TQQQ": above}, view(cash="100000"))
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].role, "TREND_ENTER")
        self.assertEqual(orders[0].side, Side.BUY)

        # sma 바로 아래 -> 진입 안 함(여전히 CASH)
        below = bar(d, sma * Decimal("0.99"))
        orders2 = strat.on_bar(SMA200State(position="CASH"), {"TQQQ": below}, view(cash="100000"))
        self.assertEqual(orders2, [])

    def test_band_hysteresis_prevents_premature_reentry_and_exit(self):
        band = Decimal("0.02")
        strat = SMA200Strategy(ticker="TQQQ", price_history=self.price_history, whipsaw_band_pct=band)
        idx = 219
        sma = strat._sma[idx]
        d = self.dates[idx]

        # CASH 상태, 1% 위(밴드 2% 미만) -> 아직 진입 안 함
        small_up = bar(d, sma * Decimal("1.01"))
        self.assertEqual(
            strat.on_bar(SMA200State(position="CASH"), {"TQQQ": small_up}, view(cash="100000")), []
        )
        # CASH 상태, 3% 위(밴드 2% 초과) -> 진입
        big_up = bar(d, sma * Decimal("1.03"))
        orders = strat.on_bar(SMA200State(position="CASH"), {"TQQQ": big_up}, view(cash="100000"))
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].role, "TREND_ENTER")

        # HOLD 상태, 1% 아래(밴드 2% 미만) -> 아직 청산 안 함
        held_view = view(cash="0", positions={"TQQQ": (50, "10")})
        small_down = bar(d, sma * Decimal("0.99"))
        self.assertEqual(
            strat.on_bar(SMA200State(position="HOLD", qty=50), {"TQQQ": small_down}, held_view), []
        )
        # HOLD 상태, 3% 아래(밴드 2% 초과) -> 전량 매도
        big_down = bar(d, sma * Decimal("0.97"))
        orders2 = strat.on_bar(SMA200State(position="HOLD", qty=50), {"TQQQ": big_down}, held_view)
        self.assertEqual(len(orders2), 1)
        self.assertEqual(orders2[0].role, "TREND_EXIT")
        self.assertEqual(orders2[0].side, Side.SELL)
        self.assertEqual(orders2[0].qty, 50)

    def test_on_fill_updates_position_and_entry_price(self):
        strat = SMA200Strategy(ticker="TQQQ", price_history=self.price_history)
        state = SMA200State(position="CASH")
        entry_order_bars = {"TQQQ": bar(self.dates[219], "500")}
        orders = strat.on_bar(state, entry_order_bars, view(cash="100000"))
        fills = _fake_fills(orders[0], price=Decimal("500"), d=self.dates[219], fee=Decimal("1"))
        new_state = strat.on_fill(state, fills)
        self.assertEqual(new_state.position, "HOLD")
        self.assertEqual(new_state.qty, orders[0].qty)
        self.assertEqual(new_state.entry_price, Decimal("500"))

        exit_bars = {"TQQQ": bar(self.dates[219], "1")}
        exit_orders = strat.on_bar(new_state, exit_bars, view(cash="0", positions={"TQQQ": (new_state.qty, "500")}))
        # sma가 500보다 훨씬 낮으므로(약 100~119대) close=1은 하회 -> 매도 시도
        self.assertEqual(len(exit_orders), 1)
        self.assertEqual(exit_orders[0].role, "TREND_EXIT")
        exit_fills = _fake_fills(exit_orders[0], price=Decimal("1"), d=self.dates[219], fee=Decimal("0"))
        final_state = strat.on_fill(new_state, exit_fills)
        self.assertEqual(final_state.position, "CASH")
        self.assertEqual(final_state.qty, 0)
        self.assertIsNone(final_state.entry_price)


# ---------------------------------------------------------------------------
# HFEA
# ---------------------------------------------------------------------------


class HFEATests(unittest.TestCase):
    def test_quarter_key_maps_months_to_calendar_quarters(self):
        self.assertEqual(quarter_key(date(2020, 1, 15)), (2020, 1))
        self.assertEqual(quarter_key(date(2020, 3, 31)), (2020, 1))
        self.assertEqual(quarter_key(date(2020, 4, 1)), (2020, 2))
        self.assertEqual(quarter_key(date(2020, 12, 31)), (2020, 4))

    def test_initial_entry_targets_55_45_floor_qty(self):
        strat = HFEAStrategy()
        state = strat.initial_state()
        bars = {
            "UPRO": bar(date(2020, 3, 16), "97.30"),
            "TMF": bar(date(2020, 3, 16), "52.70"),
        }
        orders = strat.on_bar(state, bars, view(cash="20000"))
        by_ticker = {o.ticker: o for o in orders}

        self.assertEqual(len(orders), 2)
        # target_value_UPRO = 20000*0.55 = 11000.00 -> floor(11000/97.30) = 113
        self.assertEqual(by_ticker["UPRO"].side, Side.BUY)
        self.assertEqual(by_ticker["UPRO"].role, "REBAL_BUY")
        self.assertEqual(by_ticker["UPRO"].qty, 113)
        # target_value_TMF = 20000*0.45 = 9000.00 -> floor(9000/52.70) = 170
        self.assertEqual(by_ticker["TMF"].side, Side.BUY)
        self.assertEqual(by_ticker["TMF"].role, "REBAL_BUY")
        self.assertEqual(by_ticker["TMF"].qty, 170)

    def test_same_quarter_does_not_retrigger(self):
        strat = HFEAStrategy()
        state = HFEAState(last_rebalance_quarter=(2020, 1), last_rebalance_date=date(2020, 1, 2))
        bars = {
            "UPRO": bar(date(2020, 2, 15), "80"),
            "TMF": bar(date(2020, 2, 15), "40"),
        }
        orders = strat.on_bar(state, bars, view(cash="1000", positions={"UPRO": (10, "80"), "TMF": (5, "40")}))
        self.assertEqual(orders, [])

    def test_rebalance_computes_buy_and_sell_deltas_after_price_move(self):
        strat = HFEAStrategy()
        # 1분기에 UPRO 113주 / TMF 170주 보유 중이라고 가정, 새 분기 도래
        state = HFEAState(last_rebalance_quarter=(2020, 1), last_rebalance_date=date(2020, 1, 2))
        bars = {
            "UPRO": bar(date(2020, 4, 1), "130.00"),
            "TMF": bar(date(2020, 4, 1), "45.00"),
        }
        pv = view(cash="100", positions={"UPRO": (113, "97.30"), "TMF": (170, "52.70")})
        orders = strat.on_bar(state, bars, pv)
        by_ticker = {o.ticker: o for o in orders}

        # total_value = 100 + 113*130 + 170*45 = 22440
        # target_UPRO = 22440*0.55=12342.00 -> floor(12342/130)=94 -> delta=94-113=-19 (매도)
        self.assertEqual(by_ticker["UPRO"].side, Side.SELL)
        self.assertEqual(by_ticker["UPRO"].role, "REBAL_SELL")
        self.assertEqual(by_ticker["UPRO"].qty, 19)
        # target_TMF = 22440*0.45=10098.00 -> floor(10098/45)=224 -> delta=224-170=54 (매수)
        self.assertEqual(by_ticker["TMF"].side, Side.BUY)
        self.assertEqual(by_ticker["TMF"].role, "REBAL_BUY")
        self.assertEqual(by_ticker["TMF"].qty, 54)

    def test_on_fill_marks_quarter_done(self):
        strat = HFEAStrategy()
        state = strat.initial_state()
        fills = _fake_fills(
            order=type("O", (), {"ticker": "UPRO", "side": Side.BUY, "role": "REBAL_BUY", "qty": 1})(),
            price=Decimal("100"),
            d=date(2020, 4, 2),
            fee=Decimal("0"),
        )
        new_state = strat.on_fill(state, fills)
        self.assertEqual(new_state.last_rebalance_quarter, (2020, 2))
        self.assertEqual(new_state.last_rebalance_date, date(2020, 4, 2))


if __name__ == "__main__":
    unittest.main()
