"""웨이브 3 — 코어 6종 전략 통합 비교 백테스트 실행기.

report.py의 Scenario/run_and_report를 그대로 사용해 두 시나리오를 실행하고
report/comparison_2017.md, report/comparison_2000.md (+ PNG)를 생성한다.
전체 종합 리포트(report/comparison.md)는 이 스크립트가 마지막에 직접 작성한다.

실행: `cd backtester && python3 run_comparison.py`
"""
from __future__ import annotations

import sys
from datetime import date as Date
from decimal import Decimal
from pathlib import Path

_BACKTESTER_DIR = str(Path(__file__).resolve().parent)
if _BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, _BACKTESTER_DIR)

import matplotlib  # noqa: E402
import matplotlib.font_manager  # noqa: E402

matplotlib.use("Agg")
# report.py의 차트가 한글 라벨(전략명 등)을 쓰므로, 시스템에 나눔고딕이 있으면
# 그걸로 폰트를 교체한다(없으면 DejaVu Sans 기본값 그대로 두부 글자로 렌더링됨).
for _candidate in ("NanumGothic", "Noto Sans CJK KR", "Malgun Gothic"):
    if any(_candidate in f.name for f in matplotlib.font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = _candidate
        matplotlib.rcParams["axes.unicode_minus"] = False
        break

from report import Scenario, load_ohlc, run_and_report  # noqa: E402

from strategies.dca import DCAStrategy  # noqa: E402
from strategies.hfea import HFEAStrategy  # noqa: E402
from strategies.mumae import MumaeStrategy, initial_mumae_state  # noqa: E402
from strategies.sma200 import SMA200Strategy  # noqa: E402
from strategies.value_averaging import ValueAveragingStrategy  # noqa: E402
from strategies.vr import VRStrategy  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent.parent / "report"
INITIAL_CASH = Decimal("20000")

SYNTH_NOTE = "합성 시계열(drag 2.0%), 닷컴버블 -83% 구간 포함"
SYNTH_NOTE_MUMAE = (
    SYNTH_NOTE
    + "; 합성 OHLC가 open=high=low=close라 최종매도(지정가)가 실제보다 보수적으로"
      "(늦게) 체결됨 — 장중 변동 미반영, LOC/MOC는 원래 종가 기준이라 영향 없음"
)
SYNTH_NOTE_SMA = (
    SYNTH_NOTE
    + "; SMA/밴드 판정은 원래 종가 기준이라 합성 OHLC 단일화의 영향 없음, 단 데이터가"
      " 2000-01-03부터 시작해 앞 200거래일은 워밍업(무매매) 구간"
)
HFEA_NOTE = "TMF 배당 누락, CAGR 연 2~4%p 과소"


def _first_date(bars) -> Date:
    return min(b.date for b in bars)


def build_scenario_2017() -> list[Scenario]:
    start, end = "2017-01-03", "2026-07-16"
    tqqq = load_ohlc("TQQQ", start=start, end=end)
    tqqq_warmup = load_ohlc("TQQQ", start=None, end=end)  # SMA200 워밍업용 (2010~)
    upro = load_ohlc("UPRO", start=start, end=end)
    tmf = load_ohlc("TMF", start=start, end=end)
    start_date = _first_date(tqqq)

    scenarios = [
        Scenario(
            name="① DCA 분할적립",
            strategy_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                interval_trading_days=10, lump_sum=False,
            ),
            state_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                interval_trading_days=10, lump_sum=False,
            ).initial_state(start_date),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note="2주 $500 적립, 잔돈 유휴(A_IDLE)",
        ),
        Scenario(
            name="② DCA 일괄투입",
            strategy_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                lump_sum=True,
            ),
            state_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                lump_sum=True,
            ).initial_state(start_date),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note="시작일 1회 전액 매수 후 매수도 매도도 없음(순수 보유)",
        ),
        Scenario(
            name="③ 무한매수 V4.0",
            strategy_factory=lambda: MumaeStrategy(ticker="TQQQ"),
            state_factory=lambda: initial_mumae_state(
                ticker="TQQQ", principal=INITIAL_CASH, divisions=40, target_rate=0.15,
            ),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note="40분할, R=15%, 큰수 10%",
        ),
        Scenario(
            name="④ VR5.0",
            strategy_factory=lambda: VRStrategy(
                ticker="TQQQ", price_history=tqqq, band=Decimal("0.15"),
                G=10, pool_limit=Decimal("0.75"),
            ),
            state_factory=lambda: VRStrategy.initial_state(V0=INITIAL_CASH, pool0=INITIAL_CASH),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note="band=0.15, G=10, pool_limit=0.75(적립식 기본값), 2주 평가",
        ),
        Scenario(
            name="⑤ VA",
            strategy_factory=lambda: ValueAveragingStrategy(
                ticker="TQQQ", price_history=tqqq, C=Decimal("300"), R=Decimal("0.01"),
            ),
            state_factory=lambda: ValueAveragingStrategy.initial_state(),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note="C=$300, R=1%/월(≈21거래일), 매도 허용",
        ),
        Scenario(
            name="⑥ SMA200",
            strategy_factory=lambda: SMA200Strategy(
                ticker="TQQQ", price_history=tqqq_warmup, whipsaw_band_pct=Decimal("0"),
            ),
            state_factory=lambda: SMA200Strategy.initial_state(),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note="band=0(단순 교차), 2010년 데이터로 워밍업 완료 상태에서 시작",
        ),
        Scenario(
            name="⑦ HFEA",
            strategy_factory=lambda: HFEAStrategy(),
            state_factory=lambda: HFEAStrategy.initial_state(),
            price_data={"UPRO": upro, "TMF": tmf},
            initial_cash=INITIAL_CASH,
            note=HFEA_NOTE,
        ),
    ]
    return scenarios


def build_scenario_2000() -> list[Scenario]:
    start, end = "2000-01-03", "2026-07-16"
    tqqq = load_ohlc("TQQQ_SYNTH_2.0", start=start, end=end)
    start_date = _first_date(tqqq)

    scenarios = [
        Scenario(
            name="① DCA 분할적립",
            strategy_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                interval_trading_days=10, lump_sum=False,
            ),
            state_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                interval_trading_days=10, lump_sum=False,
            ).initial_state(start_date),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note=SYNTH_NOTE,
        ),
        Scenario(
            name="② DCA 일괄투입",
            strategy_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                lump_sum=True,
            ),
            state_factory=lambda: DCAStrategy(
                ticker="TQQQ", contribution_amount=Decimal("500"),
                lump_sum=True,
            ).initial_state(start_date),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note=SYNTH_NOTE,
        ),
        Scenario(
            name="③ 무한매수 V4.0",
            strategy_factory=lambda: MumaeStrategy(ticker="TQQQ"),
            state_factory=lambda: initial_mumae_state(
                ticker="TQQQ", principal=INITIAL_CASH, divisions=40, target_rate=0.15,
            ),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note=SYNTH_NOTE_MUMAE,
        ),
        Scenario(
            name="④ VR5.0",
            strategy_factory=lambda: VRStrategy(
                ticker="TQQQ", price_history=tqqq, band=Decimal("0.15"),
                G=10, pool_limit=Decimal("0.75"),
            ),
            state_factory=lambda: VRStrategy.initial_state(V0=INITIAL_CASH, pool0=INITIAL_CASH),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note=SYNTH_NOTE,
        ),
        Scenario(
            name="⑤ VA",
            strategy_factory=lambda: ValueAveragingStrategy(
                ticker="TQQQ", price_history=tqqq, C=Decimal("300"), R=Decimal("0.01"),
            ),
            state_factory=lambda: ValueAveragingStrategy.initial_state(),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note=SYNTH_NOTE,
        ),
        Scenario(
            name="⑥ SMA200",
            strategy_factory=lambda: SMA200Strategy(
                ticker="TQQQ", price_history=tqqq, whipsaw_band_pct=Decimal("0"),
            ),
            state_factory=lambda: SMA200Strategy.initial_state(),
            price_data={"TQQQ": tqqq},
            initial_cash=INITIAL_CASH,
            note=SYNTH_NOTE_SMA,
        ),
    ]
    return scenarios


PREAMBLE_2017 = """## 시나리오 A — 실측 데이터 (2017-01-03 ~ 2026-07-16, 각 $20,000)

- TQQQ/UPRO/TMF 실측 종가(GOOGLEFINANCE, 배당 미조정 — data/META.md 참고).
- 시작일을 2010년 상장 직후가 아니라 2017-01-03으로 잡은 것은 저가(<$10) 구간의
  낮은 정밀도(META.md 한계 2)를 피하고, UPRO/TMF/TQQQ가 모두 안정적으로 거래되는
  공통 구간으로 7종 전략을 동일 조건에서 비교하기 위함이다.
- 배당: TQQQ/UPRO는 배당이 미미해 영향 작음. TMF(장기채 ETF)는 배당수익률이
  유의미해 HFEA 결과가 과소평가된다(전략별 비고 참고).
"""

PREAMBLE_2000 = """## 시나리오 B — 스트레스 테스트 (2000-01-03 ~ 2026-07-16, 합성 TQQQ, 각 $20,000)

- TQQQ_SYNTH_2.0 = 3×QQQ 총수익률(배당재투자 포함) − drag 2.0%/년, synth.py로 생성.
  2010-02-11 TQQQ 상장 이전 구간(닷컴버블 붕괴 -83%, 2008 금융위기 포함)까지 확장해
  실측으로는 볼 수 없는 초장기 하락장에서의 생존성을 본다.
- 합성 시계열의 OHLC는 open=high=low=close로 단일화되어 있다(synth.py — 일중 변동을
  모델링하지 않음). LOC/MOC/SMA 판정은 원래 종가 기준이라 이 단일화의 영향이 없지만,
  무한매수법의 최종매도(지정가, LIMIT)는 정규장 고저 범위로 판정하므로 실제보다
  체결이 보수적으로(늦게) 일어난다 — 전략별 비고에 명시.
- HFEA는 제외했다(합성 UPRO/TMF 시계열이 없음 — synth.py는 QQQ 기반 TQQQ만 합성).
"""


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== 시나리오 A (2017~2026, 실측) 실행 ===")
    results_2017 = run_and_report(
        build_scenario_2017(), REPORT_DIR, "코어 6+1종 비교 — 실측 2017-01-03~2026-07-16",
        preamble_md=PREAMBLE_2017, chart_stub="comparison_2017",
    )
    for sr in results_2017:
        row = sr.row
        print(f"  {row['전략']:14s} CAGR(세전) {row['CAGR(세전)']*100:7.2f}%  "
              f"CAGR(세후) {row['CAGR(세후)']*100:7.2f}%  MDD {row['MDD']*100:7.2f}%  "
              f"최종 ${row['최종평가액']:,.0f}")
        if not sr.result.rejected_log.empty:
            print(f"    거부주문 {len(sr.result.rejected_log)}건 "
                  f"(사유: {sr.result.rejected_log['reason'].value_counts().to_dict()})")

    print("\n=== 시나리오 B (2000~2026, 합성 스트레스) 실행 ===")
    results_2000 = run_and_report(
        build_scenario_2000(), REPORT_DIR, "코어 6종 비교 — 스트레스 2000-01-03~2026-07-16(합성)",
        preamble_md=PREAMBLE_2000, chart_stub="comparison_2000",
    )
    for sr in results_2000:
        row = sr.row
        print(f"  {row['전략']:14s} CAGR(세전) {row['CAGR(세전)']*100:7.2f}%  "
              f"CAGR(세후) {row['CAGR(세후)']*100:7.2f}%  MDD {row['MDD']*100:7.2f}%  "
              f"최종 ${row['최종평가액']:,.0f}")
        if not sr.result.rejected_log.empty:
            print(f"    거부주문 {len(sr.result.rejected_log)}건 "
                  f"(사유: {sr.result.rejected_log['reason'].value_counts().to_dict()})")

    print(f"\n완료. {REPORT_DIR} 에 comparison_2017.md / comparison_2000.md (+PNG) 생성됨.")


if __name__ == "__main__":
    main()
