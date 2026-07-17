"""전략 비교 리포트 생성기.

run_comparison.py(웨이브 3)가 Scenario 목록을 정의해 `run_and_report()`를 호출하면
report/ 폴더에 comparison.md + 차트 PNG를 만든다.

세금: 백테스트 통화는 USD, 양도세 공제(250만원)는 KRW → 고정 환율 파라미터로 환산
(기본 1,350 KRW/USD ⇒ 공제 $1,851.85). 환율 고정은 단순화 가정이며 리포트에 명시.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import metrics as M
import tax as T
from core import OHLC
from engine import BacktestResult, run_backtest

DATA_DIR = Path(__file__).resolve().parent / "data"

# dataviz 기본 카테고리 팔레트 (light, 고정 순서 — 순환 금지)
PALETTE = ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834", "#4a3aa7", "#e34948"]

KRW_PER_USD = Decimal("1350")          # 단순화: 고정 환율
EXEMPTION_KRW = Decimal("2500000")     # 연 기본공제
EXEMPTION_USD = (EXEMPTION_KRW / KRW_PER_USD).quantize(Decimal("0.01"))


def load_ohlc(ticker: str, start: Optional[str] = None, end: Optional[str] = None) -> List[OHLC]:
    """data/<ticker>.csv → [OHLC]. start/end는 'YYYY-MM-DD' 포함 경계."""
    path = DATA_DIR / f"{ticker.upper()}.csv"
    out: List[OHLC] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            d = Date.fromisoformat(row["date"])
            if start and row["date"] < start:
                continue
            if end and row["date"] > end:
                continue
            out.append(
                OHLC(
                    date=d,
                    open=Decimal(row["open"] or row["close"]),
                    high=Decimal(row["high"] or row["close"]),
                    low=Decimal(row["low"] or row["close"]),
                    close=Decimal(row["close"]),
                    dividend=Decimal(row.get("dividend") or "0"),
                )
            )
    return out


@dataclass
class Scenario:
    name: str                                   # 표·차트에 쓰는 표시 이름
    strategy_factory: Callable[[], Any]         # Strategy 인스턴스 생성
    state_factory: Callable[[], Any]            # 초기 상태 생성
    price_data: Dict[str, List[OHLC]]           # {ticker: [OHLC]}
    initial_cash: Decimal
    note: str = ""                              # 결과 표에 붙는 각주 (배당 누락 등)


@dataclass
class ScenarioResult:
    scenario: Scenario
    result: BacktestResult
    row: Dict[str, Any] = field(default_factory=dict)


def _metrics_row(name: str, r: BacktestResult, note: str) -> Dict[str, Any]:
    ec = r.equity_curve
    tax_by_year = T.compute_capital_gains_tax(
        r.realized_pnl_by_year, exemption=EXEMPTION_USD
    )
    ec_tax = T.apply_tax_to_equity(ec, tax_by_year)
    trades_per_year = M.annual_trade_count(r.trades)
    avg_trades = (sum(trades_per_year.values()) / len(trades_per_year)) if trades_per_year else 0.0
    worst = M.worst_drawdowns(ec, n=5)
    return {
        "전략": name,
        "CAGR(세전)": M.cagr(ec),
        "CAGR(세후)": M.cagr(ec_tax, equity_col="after_tax_equity"),
        "MDD": M.mdd(ec),
        "연변동성": M.annual_volatility(ec),
        "Sharpe": M.sharpe_ratio(ec),
        "평균현금비중": M.avg_cash_ratio(ec),
        "연평균매매": avg_trades,
        "총세금": float(sum(tax_by_year.values())),
        "최종평가액": float(ec["equity"].iloc[-1]),
        "_worst": worst,
        "_ec": ec,
        "_ec_tax": ec_tax,
        "비고": note,
    }


def _equity_chart(rows: List[Dict[str, Any]], out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 6), dpi=130)
    fig.patch.set_facecolor("white")
    for i, row in enumerate(rows):
        ec = row["_ec"]
        ax.plot(
            pd.to_datetime(ec["date"]),
            ec["equity"].astype(float),
            color=PALETTE[i % len(PALETTE)],
            linewidth=1.6,
            label=row["전략"],
        )
    ax.set_yscale("log")
    ax.set_title(title, fontsize=12, color="#333")
    ax.set_ylabel("평가액 ($, 로그)", fontsize=9, color="#666")
    ax.grid(True, which="major", axis="y", color="#e8e8e8", linewidth=0.7)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def _drawdown_chart(rows: List[Dict[str, Any]], out_path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 4), dpi=130)
    fig.patch.set_facecolor("white")
    for i, row in enumerate(rows):
        ec = row["_ec"]
        eq = ec["equity"].astype(float)
        dd = eq / eq.cummax() - 1.0
        ax.plot(
            pd.to_datetime(ec["date"]), dd * 100,
            color=PALETTE[i % len(PALETTE)], linewidth=1.2, label=row["전략"],
        )
    ax.set_title(title, fontsize=12, color="#333")
    ax.set_ylabel("낙폭 (%)", fontsize=9, color="#666")
    ax.grid(True, axis="y", color="#e8e8e8", linewidth=0.7)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=3)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def run_and_report(
    scenarios: List[Scenario],
    out_dir: Path,
    title: str,
    preamble_md: str = "",
    chart_stub: str = "comparison",
) -> List[ScenarioResult]:
    """시나리오 전부 실행 → out_dir에 <chart_stub>.md + PNG 저장."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: List[ScenarioResult] = []
    for sc in scenarios:
        r = run_backtest(
            strategy=sc.strategy_factory(),
            price_data=sc.price_data,
            initial_cash=sc.initial_cash,
            initial_state=sc.state_factory(),
        )
        results.append(ScenarioResult(sc, r, _metrics_row(sc.name, r, sc.note)))

    rows = [sr.row for sr in results]
    _equity_chart(rows, out_dir / f"{chart_stub}_equity.png", f"{title} — 평가액 추이")
    _drawdown_chart(rows, out_dir / f"{chart_stub}_drawdown.png", f"{title} — 낙폭")

    def pct(x: float) -> str:
        return f"{x*100:.2f}%"

    lines = [f"# {title}", ""]
    if preamble_md:
        lines += [preamble_md, ""]
    lines += [
        f"- 세후 계산: 연도별 실현손익 − 공제 ${EXEMPTION_USD}(250만원/{KRW_PER_USD}원 고정환율) 초과분 22%, 손실 이월 없음",
        f"- 수수료: 체결금액의 0.07% (KIS 우대 가정, broker_sim 기본값)",
        "",
        "| 전략 | CAGR(세전) | CAGR(세후) | MDD | 연변동성 | Sharpe | 평균현금비중 | 연평균매매 | 최종평가액 | 비고 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {} | {} | {} | {} | {} | {:.2f} | {} | {:.0f} | ${:,.0f} | {} |".format(
                row["전략"], pct(row["CAGR(세전)"]), pct(row["CAGR(세후)"]), pct(row["MDD"]),
                pct(row["연변동성"]), row["Sharpe"], pct(row["평균현금비중"]),
                row["연평균매매"], row["최종평가액"], row["비고"],
            )
        )
    lines += ["", f"![equity]({chart_stub}_equity.png)", "", f"![drawdown]({chart_stub}_drawdown.png)", ""]
    lines += ["## 최악 낙폭 구간 (전략별 상위 5)", ""]
    for row in rows:
        lines.append(f"### {row['전략']}")
        for w in row["_worst"]:
            lines.append(f"- {w}")
        lines.append("")

    (out_dir / f"{chart_stub}.md").write_text("\n".join(lines), encoding="utf-8")
    return results
