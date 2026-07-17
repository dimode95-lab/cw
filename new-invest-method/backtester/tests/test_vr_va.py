"""VR5.0(B1) / Value Averaging(B2) 단위테스트 — 손계산 가능한 소형 시나리오.

실행: `cd backtester && python3 -m unittest tests.test_vr_va` 또는
`python3 -m unittest discover -s tests`.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import MappingProxyType

_BACKTESTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

from core import OHLC, Fill, Order, OrderType, PortfolioView, PositionSnapshot, Side  # noqa: E402
from engine import run_backtest  # noqa: E402
from strategies.value_averaging import (  # noqa: E402
    ROLE_BUY as VA_BUY,
    ROLE_SELL as VA_SELL,
    ValueAveragingStrategy,
    target_value,
)
from strategies.vr import ROLE_BUY as VR_BUY, ROLE_SELL as VR_SELL, VRState, VRStrategy  # noqa: E402


def bar(d: date, close: str, dividend: str = "0") -> OHLC:
    c = Decimal(close)
    return OHLC(date=d, open=c, high=c, low=c, close=c, dividend=Decimal(dividend))


def flat_history(start: date, n: int, close: str) -> list[OHLC]:
    return [bar(start + timedelta(days=i), close) for i in range(n)]


def portfolio_view(cash: str, ticker: str = "", qty: int = 0, avg_price: str = "0") -> PortfolioView:
    positions = {}
    if ticker:
        positions[ticker] = PositionSnapshot(qty=qty, avg_price=Decimal(avg_price))
    return PortfolioView(cash=Decimal(cash), positions=MappingProxyType(positions))


class VRUnitTests(unittest.TestCase):
    """VR5.0 — on_bar/on_fill을 직접 호출해 밴드 판정·수량·V/Pool 갱신을 손계산 검증."""

    def test_below_band_buy_qty_and_state_update(self):
        # state.V=5000, pool=1000, G=10, contribution=0 -> candidate_V = 5000+1000/10=5100
        # band_lower = 5100*0.85 = 4335, band_upper = 5100*1.15 = 5865
        # 보유 0주 -> current_value=0 < 4335 -> BELOW_BAND 매수
        # buy_value = min(5100-0=5100, pool*0.75=750, cash) = 750 (pool_limit이 한도로 작동)
        # price=50 -> buy_qty = floor(750/50) = 15
        d0 = date(2021, 1, 1)
        history = [bar(d0, "50")]
        strat = VRStrategy(
            ticker="TQQQ",
            price_history=history,
            band=Decimal("0.15"),
            G=10,
            pool_limit=Decimal("0.75"),
            contribution=Decimal("0"),
            eval_interval_trading_days=10,
            fee_rate_hint=Decimal("0"),
        )
        state = VRStrategy.initial_state(V0=Decimal("5000"), pool0=Decimal("1000"))
        pv = portfolio_view(cash="1000")

        orders = strat.on_bar(state, {"TQQQ": history[0]}, pv)
        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(order.side, Side.BUY)
        self.assertEqual(order.type, OrderType.MOC)
        self.assertEqual(order.role, VR_BUY)
        self.assertEqual(order.qty, 15)

        fill = Fill(order=order, price=Decimal("50"), date=d0, fee=Decimal("0"))
        new_state = strat.on_fill(state, [fill])
        self.assertEqual(new_state.V, Decimal("5100.00"))
        # pool = 1000 - (50*15 + 0) = 1000 - 750 = 250
        self.assertEqual(new_state.pool, Decimal("250"))
        self.assertEqual(new_state.cycles_traded, 1)

    def test_above_band_sell_qty_and_state_update(self):
        # state.V=5000, pool=1000, G=10 -> candidate_V = 5100, band_upper = 5865
        # 보유 200주 @ price 50 -> current_value = 10000 > 5865 -> ABOVE_BAND 매도
        # sell_value = 10000 - 5100 = 4900 -> sell_qty = floor(4900/50) = 98
        d0 = date(2021, 1, 1)
        history = [bar(d0, "50")]
        strat = VRStrategy(
            ticker="TQQQ",
            price_history=history,
            band=Decimal("0.15"),
            G=10,
            pool_limit=Decimal("0.75"),
            contribution=Decimal("0"),
            eval_interval_trading_days=10,
            fee_rate_hint=Decimal("0"),
        )
        state = VRStrategy.initial_state(V0=Decimal("5000"), pool0=Decimal("1000"))
        pv = portfolio_view(cash="1000", ticker="TQQQ", qty=200, avg_price="40")

        orders = strat.on_bar(state, {"TQQQ": history[0]}, pv)
        self.assertEqual(len(orders), 1)
        order = orders[0]
        self.assertEqual(order.side, Side.SELL)
        self.assertEqual(order.role, VR_SELL)
        self.assertEqual(order.qty, 98)

        fill = Fill(order=order, price=Decimal("50"), date=d0, fee=Decimal("0"))
        new_state = strat.on_fill(state, [fill])
        self.assertEqual(new_state.V, Decimal("5100.00"))
        # pool = 1000 + (50*98 - 0) = 1000 + 4900 = 5900
        self.assertEqual(new_state.pool, Decimal("5900"))

    def test_in_band_no_order(self):
        # candidate_V = 5100, band 4335~5865. 보유 100주 @ 50 = 5000 -> 밴드 안 -> 무매매
        d0 = date(2021, 1, 1)
        history = [bar(d0, "50")]
        strat = VRStrategy(
            ticker="TQQQ", price_history=history, eval_interval_trading_days=10,
            fee_rate_hint=Decimal("0"),
        )
        state = VRStrategy.initial_state(V0=Decimal("5000"), pool0=Decimal("1000"))
        pv = portfolio_view(cash="1000", ticker="TQQQ", qty=100, avg_price="40")
        orders = strat.on_bar(state, {"TQQQ": history[0]}, pv)
        self.assertEqual(orders, [])
        # 무거래 사이클이어도 V는 동결되지 않고 갱신되어야 한다(코디네이터 지시,
        # vr.py 모듈 docstring 가정 3). 여기서 self._pool은 아직 초기값(1000)이므로
        # candidate_V = 5000 + 1000/10 = 5100.00.
        self.assertEqual(strat.current_V, Decimal("5100.00"))
        self.assertEqual(strat.current_pool, Decimal("1000"))

    def test_v_keeps_compounding_through_a_no_trade_cycle(self):
        """무거래(밴드 안) 사이클에도 다음 사이클의 V가 pool/G만큼 계속 증가하는지 검증
        (코디네이터 지시 — 이전 구현은 체결 없는 사이클엔 V를 동결해 방법론을 왜곡했다).

        사이클1(idx0): V0=1000, pool0=2000, G=10 -> V=1000+2000/10=1200.00
          보유0 -> 매수. buy_value=min(1200, pool*0.75=1500, cash=2000)=1200
          qty=floor(1200/100)=12 -> 체결 후 pool = 2000-1200=800
        사이클2(idx1, eval_interval=1이라 매일 평가): V = 1200 + 800/10 = 1280.00
          (pool은 사이클1 체결 이후 그대로 800 — 사이클2엔 거래가 없으므로 불변)
          band = 1280*0.85~1280*1.15 = 1088.00~1472.00. 보유12주@100=1200 -> 밴드 안 -> 무매매.
          이전 구현(체결에서만 V 갱신)이었다면 이 사이클에서 V가 1200.00에 동결됐을 것 —
          이 테스트는 1280.00으로 증가함을 확인해 그 반례를 명시적으로 검증한다.
        """
        d0 = date(2021, 1, 1)
        d1 = date(2021, 1, 2)
        bar0 = bar(d0, "100")
        bar1 = bar(d1, "100")
        strat = VRStrategy(
            ticker="TQQQ",
            price_history=[bar0, bar1],
            band=Decimal("0.15"),
            G=10,
            pool_limit=Decimal("0.75"),
            contribution=Decimal("0"),
            eval_interval_trading_days=1,  # 이 테스트에선 매 bar가 평가일
            fee_rate_hint=Decimal("0"),
        )
        state0 = VRStrategy.initial_state(V0=Decimal("1000"), pool0=Decimal("2000"))
        pv0 = portfolio_view(cash="2000")

        orders1 = strat.on_bar(state0, {"TQQQ": bar0}, pv0)
        self.assertEqual(len(orders1), 1)
        self.assertEqual(orders1[0].role, VR_BUY)
        self.assertEqual(orders1[0].qty, 12)
        self.assertEqual(strat.current_V, Decimal("1200.00"))

        fill1 = Fill(order=orders1[0], price=Decimal("100"), date=d0, fee=Decimal("0"))
        state1 = strat.on_fill(state0, [fill1])
        self.assertEqual(state1.pool, Decimal("800"))
        self.assertEqual(strat.current_pool, Decimal("800"))

        pv1 = portfolio_view(cash="800", ticker="TQQQ", qty=12, avg_price="100")
        orders2 = strat.on_bar(state1, {"TQQQ": bar1}, pv1)

        self.assertEqual(orders2, [])  # 밴드 안 -> 무매매
        # 핵심 검증: 무거래였음에도 V는 pool/G만큼 계속 증가했다(동결되지 않았다).
        self.assertEqual(strat.current_V, Decimal("1280.00"))
        self.assertEqual(strat.current_pool, Decimal("800"))  # pool은 거래가 없어 불변
        # 리포팅 미러(state1.V)는 on_fill이 그날 호출되지 않아 지연됨 — 문서화된 특성.
        self.assertEqual(state1.V, Decimal("1200.00"))

    def test_non_eval_day_no_order_even_if_far_out_of_band(self):
        # idx=1 (eval_interval=10) -> 1%10 != 0 -> 평가일이 아니므로 밴드 이탈이어도 무주문
        d0 = date(2021, 1, 1)
        d1 = date(2021, 1, 2)
        history = [bar(d0, "50"), bar(d1, "50")]
        strat = VRStrategy(
            ticker="TQQQ", price_history=history, eval_interval_trading_days=10,
            fee_rate_hint=Decimal("0"),
        )
        state = VRStrategy.initial_state(V0=Decimal("5000"), pool0=Decimal("1000"))
        pv = portfolio_view(cash="0", ticker="TQQQ", qty=1000, avg_price="1")  # 극단적으로 밴드 상단 초과
        orders = strat.on_bar(state, {"TQQQ": history[1]}, pv)
        self.assertEqual(orders, [])


class VREngineIntegrationTest(unittest.TestCase):
    """엔진을 통째로 돌려 2회 평가 사이클(pool_limit이 두 번째 사이클에서 한도로
    작동하는 경우)을 손계산 대조한다. 수수료는 0으로 둬 계산을 단순화한다."""

    def test_two_cycles_via_run_backtest(self):
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 11, "100")  # idx 0..10, 종가 전부 100

        strat = VRStrategy(
            ticker="TQQQ",
            price_history=history,
            band=Decimal("0.15"),
            G=10,
            pool_limit=Decimal("0.75"),
            contribution=Decimal("0"),
            eval_interval_trading_days=10,
            fee_rate_hint=Decimal("0"),
        )
        initial_cash = Decimal("10000")
        initial_state = VRStrategy.initial_state(V0=Decimal("10000"), pool0=initial_cash)

        result = run_backtest(
            strategy=strat,
            price_data={"TQQQ": history},
            initial_cash=initial_cash,
            initial_state=initial_state,
            fee_rate=Decimal("0"),
        )

        # 사이클0(idx0): candidate_V = 10000 + 10000/10 = 11000
        #   band_lower=9350, 보유0 -> 매수. buy_value=min(11000, 10000*0.75=7500, 10000)=7500
        #   qty = floor(7500/100) = 75, cash -> 10000-7500=2500, pool -> 2500
        # 사이클1(idx10): candidate_V = 11000 + 2500/10 = 11250
        #   band_lower=9562.50, 보유75*100=7500 -> 매수.
        #   buy_value=min(11250-7500=3750, 2500*0.75=1875, 2500)=1875
        #   qty = floor(1875/100) = 18, cash -> 2500-1800=700, pool -> 700
        self.assertTrue(result.rejected_log.empty)
        self.assertEqual(len(result.trades), 2)
        self.assertEqual(result.trades.iloc[0]["role"], VR_BUY)
        self.assertEqual(result.trades.iloc[0]["qty"], 75)
        self.assertEqual(result.trades.iloc[1]["role"], VR_BUY)
        self.assertEqual(result.trades.iloc[1]["qty"], 18)

        final_state: VRState = result.final_state
        self.assertEqual(final_state.V, Decimal("11250.00"))
        self.assertEqual(final_state.pool, Decimal("700"))
        self.assertEqual(final_state.cycles_traded, 2)

        last_row = result.equity_curve.iloc[-1]
        self.assertEqual(last_row["cash"], Decimal("700"))
        self.assertEqual(last_row["market_value"], Decimal("100") * 93)
        self.assertEqual(last_row["equity"], Decimal("10000"))


class VAUnitTests(unittest.TestCase):
    def test_target_value_formula(self):
        self.assertEqual(target_value(Decimal("1000"), Decimal("0.01"), 0), Decimal("0"))
        self.assertEqual(target_value(Decimal("1000"), Decimal("0.01"), 1), Decimal("1010.00"))
        # 1000*3*(1.01)^3 = 3000*1.030301 = 3090.903 -> HALF_UP -> 3090.90
        self.assertEqual(target_value(Decimal("1000"), Decimal("0.01"), 3), Decimal("3090.90"))

    def test_below_target_buy(self):
        # eval_interval=5, idx=5 -> t=1 -> V_1 = 1000*1*(1+0)^1 = 1000.00
        # 보유 0 -> actual=0 -> diff=1000 -> budget=min(1000,2000)=1000 -> qty=floor(1000/50)=20
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 6, "50")
        strat = ValueAveragingStrategy(
            ticker="TQQQ", price_history=history, C=Decimal("1000"), R=Decimal("0"),
            no_sell=False, eval_interval_trading_days=5, fee_rate_hint=Decimal("0"),
        )
        state = ValueAveragingStrategy.initial_state()
        pv = portfolio_view(cash="2000")
        orders = strat.on_bar(state, {"TQQQ": history[5]}, pv)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.BUY)
        self.assertEqual(orders[0].role, VA_BUY)
        self.assertEqual(orders[0].qty, 20)

    def test_above_target_sell_standard(self):
        # V_1=1000.00, 보유 30주@50=1500 -> diff=1000-1500=-500 -> qty=floor(500/50)=10
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 6, "50")
        strat = ValueAveragingStrategy(
            ticker="TQQQ", price_history=history, C=Decimal("1000"), R=Decimal("0"),
            no_sell=False, eval_interval_trading_days=5, fee_rate_hint=Decimal("0"),
        )
        state = ValueAveragingStrategy.initial_state()
        pv = portfolio_view(cash="0", ticker="TQQQ", qty=30, avg_price="40")
        orders = strat.on_bar(state, {"TQQQ": history[5]}, pv)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, Side.SELL)
        self.assertEqual(orders[0].role, VA_SELL)
        self.assertEqual(orders[0].qty, 10)

    def test_above_target_no_sell_variant_skips(self):
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 6, "50")
        strat = ValueAveragingStrategy(
            ticker="TQQQ", price_history=history, C=Decimal("1000"), R=Decimal("0"),
            no_sell=True, eval_interval_trading_days=5, fee_rate_hint=Decimal("0"),
        )
        state = ValueAveragingStrategy.initial_state()
        pv = portfolio_view(cash="0", ticker="TQQQ", qty=30, avg_price="40")
        orders = strat.on_bar(state, {"TQQQ": history[5]}, pv)
        self.assertEqual(orders, [])

    def test_t0_is_always_skip(self):
        # idx=0 -> t=0 -> V_0=0, 보유 0 -> diff=0 -> 무주문
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 6, "50")
        strat = ValueAveragingStrategy(
            ticker="TQQQ", price_history=history, C=Decimal("1000"), R=Decimal("0"),
            eval_interval_trading_days=5, fee_rate_hint=Decimal("0"),
        )
        state = ValueAveragingStrategy.initial_state()
        pv = portfolio_view(cash="2000")
        orders = strat.on_bar(state, {"TQQQ": history[0]}, pv)
        self.assertEqual(orders, [])

    def test_non_eval_day_no_order(self):
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 6, "50")
        strat = ValueAveragingStrategy(
            ticker="TQQQ", price_history=history, C=Decimal("1000"), R=Decimal("0"),
            eval_interval_trading_days=5, fee_rate_hint=Decimal("0"),
        )
        state = ValueAveragingStrategy.initial_state()
        pv = portfolio_view(cash="2000")
        orders = strat.on_bar(state, {"TQQQ": history[2]}, pv)  # idx=2, 2%5 != 0
        self.assertEqual(orders, [])

    def test_on_fill_bookkeeping(self):
        d0 = date(2021, 1, 1)
        buy_order = Order("TQQQ", Side.BUY, OrderType.MOC, None, 20, VA_BUY)
        strat = ValueAveragingStrategy(
            ticker="TQQQ", price_history=[bar(d0, "50")], C=Decimal("1000"), R=Decimal("0"),
        )
        state = ValueAveragingStrategy.initial_state()
        fill = Fill(order=buy_order, price=Decimal("50"), date=d0, fee=Decimal("0"))
        new_state = strat.on_fill(state, [fill])
        self.assertEqual(new_state.cumulative_net_invested, Decimal("1000"))
        self.assertEqual(new_state.trade_count, 1)

        sell_order = Order("TQQQ", Side.SELL, OrderType.MOC, None, 5, VA_SELL)
        fill2 = Fill(order=sell_order, price=Decimal("60"), date=d0, fee=Decimal("1"))
        new_state2 = strat.on_fill(new_state, [fill2])
        # cumulative = 1000 - (5*60 - 1) = 1000 - 299 = 701
        self.assertEqual(new_state2.cumulative_net_invested, Decimal("701"))
        self.assertEqual(new_state2.trade_count, 2)


class VAEngineIntegrationTest(unittest.TestCase):
    """엔진을 통째로 돌려 2회 평가 사이클(가격 불변, 수수료 0 -> equity 불변이어야
    함)을 손계산 대조한다."""

    def test_two_cycles_via_run_backtest(self):
        d0 = date(2021, 1, 1)
        history = flat_history(d0, 11, "50")  # idx 0..10

        strat = ValueAveragingStrategy(
            ticker="TQQQ",
            price_history=history,
            C=Decimal("1000"),
            R=Decimal("0"),
            no_sell=False,
            eval_interval_trading_days=5,
            fee_rate_hint=Decimal("0"),
        )
        initial_cash = Decimal("5000")
        initial_state = ValueAveragingStrategy.initial_state()

        result = run_backtest(
            strategy=strat,
            price_data={"TQQQ": history},
            initial_cash=initial_cash,
            initial_state=initial_state,
            fee_rate=Decimal("0"),
        )

        # idx0(t=0): V_0=0, 무매매
        # idx5(t=1): V_1=1000.00, 보유0 -> 매수 qty=floor(1000/50)=20, cash 5000->4000
        # idx10(t=2): V_2=1000*2*(1+0)^2=2000.00, 보유20*50=1000 -> diff=1000 -> 매수
        #             qty=floor(1000/50)=20, cash 4000->3000, 보유 40주
        self.assertTrue(result.rejected_log.empty)
        self.assertEqual(len(result.trades), 2)
        self.assertEqual(result.trades.iloc[0]["qty"], 20)
        self.assertEqual(result.trades.iloc[1]["qty"], 20)

        final_state = result.final_state
        self.assertEqual(final_state.trade_count, 2)
        self.assertEqual(final_state.cumulative_net_invested, Decimal("2000"))

        last_row = result.equity_curve.iloc[-1]
        self.assertEqual(last_row["cash"], Decimal("3000"))
        self.assertEqual(last_row["market_value"], Decimal("50") * 40)
        self.assertEqual(last_row["equity"], Decimal("5000"))  # 가격 불변+수수료0 -> 총자산 불변


if __name__ == "__main__":
    unittest.main()
