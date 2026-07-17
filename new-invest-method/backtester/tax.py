"""한국 양도소득세 (경량 모델, PLAN.md §4.1/§0-3).

규칙:
  - 연도별 실현손익을 합산한다 (engine.run_backtest()의 realized_pnl_by_year).
  - 한 해 합산이 이익이면 250만원을 공제하고, 초과분에 22% 세율을 적용한다.
  - 한 해 합산이 손실이면 세금은 0 — 그리고 그 손실은 다른 해로 이월되지 않는다
    (연도별로 완전히 독립적으로 계산). 이것이 "손실 이월공제 없음"의 의미다.

통화 단위에 대한 가정: 이 모듈은 순수 계산기이며 realized_pnl_by_year에 들어오는 값의
통화 단위를 스스로 판단하지 않는다. 250만원 공제선은 원화 기준이므로, 백테스트가
달러 기준으로 실현손익을 집계했다면 호출자가 그 해의 적절한 환율로 환산한 값을
넘겨야 한다. (본 프로젝트의 1차 백테스트는 이 환산을 단순화해 달러 금액에 그대로
공제선을 적용하는 근사치로 다룰 수도 있다 — report.py에서 그 가정을 명시할 것.)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict

import pandas as pd

DEFAULT_EXEMPTION = Decimal("2500000")
DEFAULT_RATE = Decimal("0.22")


def compute_capital_gains_tax(
    realized_pnl_by_year: Dict[int, Decimal],
    exemption: Decimal = DEFAULT_EXEMPTION,
    rate: Decimal = DEFAULT_RATE,
) -> Dict[int, Decimal]:
    """연도별 실현손익 → 250만원 공제 → 초과분 rate(기본 22%). 손실 이월 없음.

    반환값은 {연도: 세액}. 세액은 원 단위 정수로 반올림(ROUND_HALF_UP)한다
    (통화 단위가 원이 아니어도 같은 정밀도 규칙을 그대로 쓴다 — 최소 단위는 호출자 책임).
    손실이거나 공제선 이하인 해는 0.
    """
    tax_by_year: Dict[int, Decimal] = {}
    for year, pnl in realized_pnl_by_year.items():
        if pnl is None:
            tax_by_year[year] = Decimal("0")
            continue
        taxable = pnl - exemption
        if taxable <= 0:
            tax_by_year[year] = Decimal("0")
            continue
        tax = (taxable * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        tax_by_year[year] = tax
    return tax_by_year


def apply_tax_to_equity(
    equity_curve: pd.DataFrame,
    tax_by_year: Dict[int, Decimal],
    date_col: str = "date",
    equity_col: str = "equity",
    out_col: str = "after_tax_equity",
) -> pd.DataFrame:
    """각 연도 말(그 해의 마지막 거래일)에 그 해의 세액을 equity에서 차감하고,
    이후 모든 날짜에 누적 반영한 새 DataFrame을 반환한다 (원본은 변경하지 않음).
    """
    if equity_curve.empty:
        df = equity_curve.copy()
        df[out_col] = df.get(equity_col)
        return df

    df = equity_curve.sort_values(date_col).reset_index(drop=True).copy()
    df[out_col] = df[equity_col].apply(lambda v: v if isinstance(v, Decimal) else Decimal(str(v)))

    years = df[date_col].apply(lambda d: d.year)
    for year in sorted(tax_by_year.keys()):
        tax = tax_by_year[year]
        if tax == 0:
            continue
        year_mask = years == year
        if not year_mask.any():
            continue
        last_idx_of_year = df.index[year_mask].max()
        df.loc[last_idx_of_year:, out_col] = df.loc[last_idx_of_year:, out_col] - tax

    return df
