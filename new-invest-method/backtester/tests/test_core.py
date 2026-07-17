"""broker_sim 체결 판정 / tax 계산(경계값) / metrics 기본 케이스 단위테스트.

pytest가 없는 환경 기준: `python3 -m unittest tests.test_core` 또는
`cd backtester && python3 -m unittest discover -s tests` 로 실행한다.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from decimal import Decimal

# backtester/ 를 sys.path에 넣어 core/broker_sim/engine/metrics/tax를 단순 임포트한다
_BACKTESTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

import pandas as pd

from broker_sim import DEFAULT_FEE_RATE, simulate_day
from core import OHLC, Order, OrderType, Portfolio, Side
import metrics
import tax


def bar(d, o, h, l, c, dividend="0"):
    return OHLC(
        date=d,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        dividend=Decimal(dividend),
    )


class BrokerSimFillJudgementTests(unittest.TestCase):
    def test_loc_buy_fills_at_close_when_close_lte_limit(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.0")
        order = Order("TQQQ", Side.BUY, OrderType.LOC, Decimal("10.5"), 10, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].price, Decimal("10.0"))

    def test_loc_buy_rejected_when_close_gt_limit(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.6")
        order = Order("TQQQ", Side.BUY, OrderType.LOC, Decimal("10.5"), 10, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 0)
        self.assertEqual(result.rejected[0].reason, "no_fill_price_condition")

    def test_loc_sell_fills_at_close_when_close_gte_limit(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.5")
        order = Order("TQQQ", Side.SELL, OrderType.LOC, Decimal("10.5"), 5, "TEST")
        portfolio = Portfolio(cash=Decimal("0"))
        portfolio.apply_buy("TQQQ", 5, Decimal("9.0"), Decimal("0"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].price, Decimal("10.5"))

    def test_moc_always_fills_at_close(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "9.99")
        order = Order("TQQQ", Side.SELL, OrderType.MOC, None, 3, "TEST")
        portfolio = Portfolio(cash=Decimal("0"))
        portfolio.apply_buy("TQQQ", 3, Decimal("9.0"), Decimal("0"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].price, Decimal("9.99"))

    def test_limit_buy_fills_at_limit_price_when_low_lte_limit(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.0", "9.8")
        order = Order("TQQQ", Side.BUY, OrderType.LIMIT, Decimal("9.5"), 4, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 1)
        # 보수적 가정: 체결가는 저가가 아니라 지정가 그대로
        self.assertEqual(result.fills[0].price, Decimal("9.5"))

    def test_limit_buy_rejected_when_low_gt_limit(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.6", "9.8")
        order = Order("TQQQ", Side.BUY, OrderType.LIMIT, Decimal("9.5"), 4, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 0)

    def test_limit_sell_fills_at_limit_price_when_high_gte_limit(self):
        b = bar(date(2024, 1, 2), "10", "11.0", "9.5", "10.2")
        order = Order("TQQQ", Side.SELL, OrderType.LIMIT, Decimal("10.8"), 2, "TEST")
        portfolio = Portfolio(cash=Decimal("0"))
        portfolio.apply_buy("TQQQ", 2, Decimal("9.0"), Decimal("0"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].price, Decimal("10.8"))

    def test_mkt_fills_at_open(self):
        b = bar(date(2024, 1, 2), "10.1", "10.5", "9.5", "10.0")
        order = Order("TQQQ", Side.BUY, OrderType.MKT, None, 1, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(result.fills[0].price, Decimal("10.1"))

    def test_fee_is_fee_rate_times_notional_rounded_half_up_cents(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.0")
        order = Order("TQQQ", Side.BUY, OrderType.MOC, None, 3, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date, fee_rate=Decimal("0.0007"))
        # notional = 10.0*3 = 30, fee = 30*0.0007 = 0.021 -> HALF_UP 2자리 = 0.02
        self.assertEqual(result.fills[0].fee, Decimal("0.02"))

    def test_default_fee_rate_is_0_0007(self):
        self.assertEqual(DEFAULT_FEE_RATE, Decimal("0.0007"))

    def test_buy_rejected_when_insufficient_cash(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.0")
        order = Order("TQQQ", Side.BUY, OrderType.MOC, None, 100, "TEST")  # 필요 1000+수수료
        portfolio = Portfolio(cash=Decimal("50"))
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 0)
        self.assertEqual(result.rejected[0].reason, "insufficient_cash")

    def test_sell_proceeds_extend_same_day_buy_affordability(self):
        # 매도가 먼저 반영되어 그날 매수 여력이 늘어나는지 확인
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.0")
        sell = Order("TQQQ", Side.SELL, OrderType.MOC, None, 50, "SELL_TEST")
        buy = Order("TQQQ", Side.BUY, OrderType.MOC, None, 50, "BUY_TEST")
        portfolio = Portfolio(cash=Decimal("10"))  # 매수 하나만으로는 턱없이 부족
        portfolio.apply_buy("TQQQ", 50, Decimal("5.0"), Decimal("0"))  # 보유 50주 확보 (cash 마이너스는 테스트 편의상 무시)
        portfolio.cash = Decimal("10")
        result = simulate_day([sell, buy], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 2)

    def test_sell_rejected_when_insufficient_shares(self):
        b = bar(date(2024, 1, 2), "10", "10.5", "9.5", "10.0")
        order = Order("TQQQ", Side.SELL, OrderType.MOC, None, 10, "TEST")
        portfolio = Portfolio(cash=Decimal("0"))  # 보유수량 0
        result = simulate_day([order], {"TQQQ": b}, portfolio, b.date)
        self.assertEqual(len(result.fills), 0)
        self.assertEqual(result.rejected[0].reason, "insufficient_shares")

    def test_no_bar_today_rejects_order(self):
        order = Order("SOXL", Side.BUY, OrderType.MOC, None, 1, "TEST")
        portfolio = Portfolio(cash=Decimal("1000000"))
        result = simulate_day([order], {}, portfolio, date(2024, 1, 2))
        self.assertEqual(len(result.fills), 0)
        self.assertEqual(result.rejected[0].reason, "no_bar_today")


class TaxBoundaryTests(unittest.TestCase):
    def test_loss_year_has_zero_tax(self):
        result = tax.compute_capital_gains_tax({2024: Decimal("-1000000")})
        self.assertEqual(result[2024], Decimal("0"))

    def test_exactly_at_exemption_has_zero_tax(self):
        result = tax.compute_capital_gains_tax({2024: Decimal("2500000")})
        self.assertEqual(result[2024], Decimal("0"))

    def test_one_won_over_exemption_is_taxed(self):
        result = tax.compute_capital_gains_tax({2024: Decimal("2500001")})
        # taxable = 1, tax = 1*0.22 = 0.22 -> HALF_UP 정수 반올림 = 0
        self.assertEqual(result[2024], Decimal("0"))

    def test_clearly_over_exemption_taxed_at_22_percent(self):
        result = tax.compute_capital_gains_tax({2024: Decimal("12500000")})
        # taxable = 10,000,000 -> tax = 2,200,000
        self.assertEqual(result[2024], Decimal("2200000"))

    def test_no_loss_carryforward_between_years(self):
        # 2024년 큰 손실이 2025년 이익과 상계되지 않는다 (완전 독립 계산)
        result = tax.compute_capital_gains_tax(
            {2024: Decimal("-50000000"), 2025: Decimal("12500000")}
        )
        self.assertEqual(result[2024], Decimal("0"))
        self.assertEqual(result[2025], Decimal("2200000"))

    def test_apply_tax_to_equity_deducts_from_year_end_onward(self):
        df = pd.DataFrame(
            [
                {"date": date(2024, 12, 30), "equity": Decimal("100000000")},
                {"date": date(2024, 12, 31), "equity": Decimal("100100000")},
                {"date": date(2025, 1, 2), "equity": Decimal("100200000")},
            ]
        )
        tax_by_year = {2024: Decimal("2200000")}
        out = tax.apply_tax_to_equity(df, tax_by_year)
        self.assertEqual(out.loc[0, "after_tax_equity"], Decimal("100000000"))
        self.assertEqual(out.loc[1, "after_tax_equity"], Decimal("100100000") - Decimal("2200000"))
        self.assertEqual(out.loc[2, "after_tax_equity"], Decimal("100200000") - Decimal("2200000"))


class MetricsBasicTests(unittest.TestCase):
    def _equity_curve(self):
        # 100 -> 110 -> 99 -> 121 (하루 낙폭 후 회복), 4 거래일
        rows = [
            {"date": date(2024, 1, 1), "cash": Decimal("0"), "equity": Decimal("100")},
            {"date": date(2024, 1, 2), "cash": Decimal("0"), "equity": Decimal("110")},
            {"date": date(2024, 1, 3), "cash": Decimal("0"), "equity": Decimal("99")},
            {"date": date(2024, 1, 4), "cash": Decimal("0"), "equity": Decimal("121")},
        ]
        return pd.DataFrame(rows)

    def test_mdd_is_negative_and_matches_worst_drop(self):
        df = self._equity_curve()
        m = metrics.mdd(df)
        # peak 110 -> trough 99: (99-110)/110 = -0.1
        self.assertAlmostEqual(m, -0.1, places=6)

    def test_cagr_positive_for_growing_equity(self):
        rows = [
            {"date": date(2020, 1, 1), "equity": Decimal("10000")},
            {"date": date(2024, 1, 1), "equity": Decimal("20000")},
        ]
        df = pd.DataFrame(rows)
        c = metrics.cagr(df)
        self.assertGreater(c, 0.0)
        # 4년간 2배 -> 연복리 약 18.9%
        self.assertAlmostEqual(c, 0.189, places=2)

    def test_cagr_zero_for_single_row(self):
        df = pd.DataFrame([{"date": date(2020, 1, 1), "equity": Decimal("10000")}])
        self.assertEqual(metrics.cagr(df), 0.0)

    def test_worst_drawdowns_returns_nonempty_for_declining_series(self):
        df = self._equity_curve()
        episodes = metrics.worst_drawdowns(df, n=5)
        self.assertGreaterEqual(len(episodes), 1)
        self.assertLess(episodes[0]["drawdown_pct"], 0)

    def test_avg_cash_ratio_basic(self):
        rows = [
            {"date": date(2024, 1, 1), "cash": Decimal("50"), "equity": Decimal("100")},
            {"date": date(2024, 1, 2), "cash": Decimal("30"), "equity": Decimal("100")},
        ]
        df = pd.DataFrame(rows)
        ratio = metrics.avg_cash_ratio(df)
        self.assertAlmostEqual(ratio, 0.4, places=6)

    def test_annual_trade_count_groups_by_year(self):
        trades = pd.DataFrame(
            [
                {"date": date(2024, 1, 1)},
                {"date": date(2024, 6, 1)},
                {"date": date(2025, 1, 1)},
            ]
        )
        counts = metrics.annual_trade_count(trades)
        self.assertEqual(counts[2024], 2)
        self.assertEqual(counts[2025], 1)

    def test_annual_trade_count_empty(self):
        self.assertEqual(metrics.annual_trade_count(pd.DataFrame()), {})


class PortfolioArithmeticTests(unittest.TestCase):
    def test_apply_buy_updates_weighted_average(self):
        p = Portfolio(cash=Decimal("10000"))
        p.apply_buy("TQQQ", 10, Decimal("80.00"), Decimal("0"))
        p.apply_buy("TQQQ", 10, Decimal("76.12"), Decimal("0"))
        pos = p.position("TQQQ")
        self.assertEqual(pos.qty, 20)
        # (10*80.00 + 10*76.12) / 20 = 78.06
        self.assertEqual(pos.avg_price, Decimal("78.06"))

    def test_apply_sell_does_not_change_avg_price(self):
        p = Portfolio(cash=Decimal("0"))
        p.apply_buy("TQQQ", 10, Decimal("80.00"), Decimal("0"))
        realized = p.apply_sell("TQQQ", 4, Decimal("90.00"), Decimal("0"))
        pos = p.position("TQQQ")
        self.assertEqual(pos.qty, 6)
        self.assertEqual(pos.avg_price, Decimal("80.00"))
        self.assertEqual(realized, Decimal("40.00"))  # (90-80)*4


if __name__ == "__main__":
    unittest.main()
