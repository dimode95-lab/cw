"""성과 지표: CAGR, MDD, 연변동성, Sharpe(rf=0), 평균 현금비중, 연간 매매횟수, 최악 낙폭 5구간.

engine.run_backtest()가 만드는 equity_curve(DataFrame: date, cash, market_value, equity)와
trades(DataFrame: date, ticker, side, type, role, qty, price, fee)를 입력으로 받는다.

계산 편의를 위해 여기서는 float으로 캐스팅한다 (Decimal은 engine/broker_sim/tax처럼
"정확한 금액"이 필요한 곳에만 강제 — 지표는 통계치라 float으로 충분하고 훨씬 간단하다).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd


def _to_float_series(s: pd.Series) -> pd.Series:
    return s.apply(lambda v: float(v) if isinstance(v, Decimal) else float(v))


def cagr(equity_curve: pd.DataFrame, equity_col: str = "equity", date_col: str = "date") -> float:
    """연복리수익률. 구간이 1년 미만이면 0.0 반환(연환산 왜곡 방지)."""
    if len(equity_curve) < 2:
        return 0.0
    df = equity_curve.sort_values(date_col)
    start_value = float(df[equity_col].iloc[0])
    end_value = float(df[equity_col].iloc[-1])
    start_date = df[date_col].iloc[0]
    end_date = df[date_col].iloc[-1]
    years = (end_date - start_date).days / 365.25
    if years <= 0 or start_value <= 0:
        return 0.0
    return (end_value / start_value) ** (1.0 / years) - 1.0


def mdd(equity_curve: pd.DataFrame, equity_col: str = "equity", date_col: str = "date") -> float:
    """최대낙폭(음수 비율, 예: -0.35 = -35%)."""
    if equity_curve.empty:
        return 0.0
    eq = _to_float_series(equity_curve.sort_values(date_col)[equity_col]).reset_index(drop=True)
    running_max = eq.cummax()
    drawdown = (eq - running_max) / running_max
    return float(drawdown.min())


def daily_returns(equity_curve: pd.DataFrame, equity_col: str = "equity", date_col: str = "date") -> pd.Series:
    eq = _to_float_series(equity_curve.sort_values(date_col)[equity_col]).reset_index(drop=True)
    return eq.pct_change().dropna()


def annual_volatility(equity_curve: pd.DataFrame, equity_col: str = "equity", date_col: str = "date", periods_per_year: int = 252) -> float:
    rets = daily_returns(equity_curve, equity_col, date_col)
    if len(rets) < 2:
        return 0.0
    return float(rets.std(ddof=1) * math.sqrt(periods_per_year))


def sharpe_ratio(
    equity_curve: pd.DataFrame,
    rf: float = 0.0,
    equity_col: str = "equity",
    date_col: str = "date",
    periods_per_year: int = 252,
) -> float:
    """rf는 연율 무위험이자율(기본 0). 일간 수익률의 초과분으로 계산."""
    rets = daily_returns(equity_curve, equity_col, date_col)
    if len(rets) < 2:
        return 0.0
    rf_daily = rf / periods_per_year
    excess = rets - rf_daily
    std = excess.std(ddof=1)
    if std == 0 or math.isnan(std):
        return 0.0
    return float(excess.mean() / std * math.sqrt(periods_per_year))


def avg_cash_ratio(equity_curve: pd.DataFrame, cash_col: str = "cash", equity_col: str = "equity") -> float:
    """평균 현금비중 (현금 / 총평가액의 일별 평균)."""
    if equity_curve.empty:
        return 0.0
    cash = _to_float_series(equity_curve[cash_col])
    equity = _to_float_series(equity_curve[equity_col])
    ratios = cash / equity.replace(0, float("nan"))
    return float(ratios.mean())


def annual_trade_count(trades: pd.DataFrame, date_col: str = "date") -> Dict[int, int]:
    """연도별 체결(거래) 횟수. trades는 engine.run_backtest()의 trades DataFrame (체결된 것만 담김)."""
    if trades.empty:
        return {}
    years = pd.to_datetime(trades[date_col]).dt.year
    return {int(y): int(c) for y, c in years.value_counts().sort_index().items()}


def worst_drawdowns(
    equity_curve: pd.DataFrame,
    n: int = 5,
    equity_col: str = "equity",
    date_col: str = "date",
) -> List[Dict[str, Any]]:
    """최악 낙폭 구간 상위 n개. 각 항목: peak_date, trough_date, recovery_date(회복 전이면 None),
    drawdown_pct(음수), duration_days(고점→저점 일수).
    """
    if equity_curve.empty:
        return []
    df = equity_curve.sort_values(date_col).reset_index(drop=True)
    eq = _to_float_series(df[equity_col])
    dts = df[date_col]
    running_max = eq.cummax()
    drawdown = (eq - running_max) / running_max

    episodes: List[Dict[str, Any]] = []
    in_dd = False
    start_idx: Optional[int] = None
    peak_idx: Optional[int] = None

    for i in range(len(eq)):
        if drawdown.iloc[i] < 0 and not in_dd:
            in_dd = True
            start_idx = i
            peak_idx = i - 1 if i > 0 else i
        is_last = i == len(eq) - 1
        if in_dd and (drawdown.iloc[i] >= 0 or is_last):
            end_idx = i if drawdown.iloc[i] >= 0 else i
            segment = drawdown.iloc[start_idx : end_idx + 1]
            trough_pos = segment.idxmin()
            recovered = drawdown.iloc[i] >= 0
            episodes.append(
                {
                    "peak_date": dts.iloc[peak_idx],
                    "trough_date": dts.iloc[trough_pos],
                    "recovery_date": dts.iloc[i] if recovered else None,
                    "drawdown_pct": float(segment.min()),
                    "duration_days": (dts.iloc[trough_pos] - dts.iloc[peak_idx]).days,
                }
            )
            in_dd = False
            start_idx = None
            peak_idx = None

    episodes.sort(key=lambda e: e["drawdown_pct"])
    return episodes[:n]
