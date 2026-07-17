"""합성 TQQQ 생성: 3×QQQ 총수익률(가격+배당재투자) - drag/252.

PLAN.md §0-4 결정: 2000~2010 닷컴버블 스트레스 구간을 백테스트에 포함하기 위해
TQQQ 상장(2010-02-11) 이전 구간을 QQQ로부터 합성한다.

레버리지 ETF는 기초지수의 "총수익률(가격+배당재투자)"의 일별 배수를 매일
재조정(리밸런스)해서 추종한다. 따라서 비교 기준은 QQQ의 가격 수익률이 아니라
배당을 포함한 총수익률이어야 한다 — QQQ 배당(quarterly, 소액)을 무시하면 장기
구간에서 합성 시계열이 실제보다 계통적으로 낮게 나온다.

drag(연율, %)는 운용보수 + 매일 재조정 비용 + 레버리지 차입비용을 뭉뚱그린 근사치.
PLAN 기본값 1.5%, 민감도 시나리오 {1.0, 1.5, 2.0}.

실행: python3 synth.py
  - data/QQQ.csv, data/TQQQ.csv 필요 (fetch_data.py로 먼저 받을 것)
  - drag 시나리오별로 data/TQQQ_SYNTH_<drag>.csv 저장
  - 실측 구간(TQQQ 상장 이후) 대조 오차율 출력
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
DRAG_SCENARIOS = (1.0, 1.5, 2.0)   # 연율 %, PLAN §0-4
LEVERAGE = 3
TRADING_DAYS = 252
SYNTH_START = "2000-01-01"  # QQQ 실제 상장은 1999-03-10. PLAN §4.3: "2000년~"


def load_csv(ticker: str) -> pd.DataFrame:
    path = DATA_DIR / f"{ticker}.csv"
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df


def qqq_total_return(qqq: pd.DataFrame) -> pd.Series:
    """QQQ 배당재투자 총수익률(일별). dividend는 배당락일 주당 현금액이라
    전일 종가 대비 배당수익률로 환산해 가격수익률에 더한다."""
    price_return = qqq["close"].pct_change()
    div_yield = qqq["dividend"] / qqq["close"].shift(1)
    total = price_return.fillna(0) + div_yield.fillna(0)
    return total.iloc[1:]


def synthesize(qqq: pd.DataFrame, drag_pct: float, start: str = SYNTH_START) -> pd.DataFrame:
    """일별 3×QQQ총수익률 - drag/252 로 합성 종가(cumulative) 시계열 생성.

    OHLC가 필요한 백테스터 인터페이스에 맞춰 open=high=low=close로 채운다
    (합성 시계열은 일중 변동을 모델링하지 않는다 — META.md 한계 참고).
    """
    total_ret = qqq_total_return(qqq)
    synth_ret = LEVERAGE * total_ret - (drag_pct / 100) / TRADING_DAYS
    synth_ret = synth_ret[synth_ret.index >= pd.Timestamp(start)]
    if synth_ret.empty:
        raise ValueError(f"no QQQ data on/after {start}")

    price = (1.0 + synth_ret).cumprod() * 100.0
    anchor_date = synth_ret.index[0] - pd.Timedelta(days=1)
    price = pd.concat([pd.Series([100.0], index=[anchor_date]), price]).sort_index()

    df = pd.DataFrame({
        "open": price, "high": price, "low": price, "close": price,
        "volume": 0, "dividend": 0.0,
    })
    df.index.name = "date"
    return df


def validate(actual: pd.DataFrame, synth: pd.DataFrame) -> dict:
    """실측 TQQQ와 합성 시계열이 겹치는 구간에서 누적수익률·CAGR 오차 계산."""
    idx = actual.index.intersection(synth.index).sort_values()
    if len(idx) < 2:
        raise ValueError("겹치는 구간이 부족합니다 (실측 TQQQ와 합성 구간 미교차)")

    a = actual.loc[idx, "close"]
    s = synth.loc[idx, "close"]
    a_ret = a / a.iloc[0]
    s_ret = s / s.iloc[0]

    years = (idx[-1] - idx[0]).days / 365.25
    a_cagr = a_ret.iloc[-1] ** (1 / years) - 1
    s_cagr = s_ret.iloc[-1] ** (1 / years) - 1

    daily_a = a.pct_change().dropna()
    daily_s = s.pct_change().dropna()
    corr = daily_a.corr(daily_s)

    return {
        "start": idx[0].date(), "end": idx[-1].date(), "years": years,
        "actual_cum_return": a_ret.iloc[-1] - 1,
        "synth_cum_return": s_ret.iloc[-1] - 1,
        "actual_cagr": a_cagr, "synth_cagr": s_cagr,
        "cagr_diff_pp": (s_cagr - a_cagr) * 100,
        "cum_diff_pp": (s_ret.iloc[-1] - a_ret.iloc[-1]) * 100,
        "daily_return_corr": corr,
    }


def main() -> None:
    try:
        qqq = load_csv("QQQ")
        tqqq = load_csv("TQQQ")
    except FileNotFoundError as exc:
        print(f"필요한 데이터가 없습니다: {exc}", file=sys.stderr)
        print("먼저 python3 fetch_data.py 로 QQQ, TQQQ CSV를 받으세요.", file=sys.stderr)
        sys.exit(1)

    header = f"{'drag%':>6} {'실측CAGR':>10} {'합성CAGR':>10} {'CAGR오차(pp)':>13} {'누적오차(pp)':>13} {'상관':>6}"
    print(header)
    results = []
    for drag in DRAG_SCENARIOS:
        synth = synthesize(qqq, drag)
        out = DATA_DIR / f"TQQQ_SYNTH_{drag}.csv"
        synth.to_csv(out, date_format="%Y-%m-%d")

        v = validate(tqqq, synth)
        results.append((drag, v))
        print(f"{drag:>6.1f} {v['actual_cagr']*100:>9.2f}% {v['synth_cagr']*100:>9.2f}% "
              f"{v['cagr_diff_pp']:>12.2f}pp {v['cum_diff_pp']:>12.2f}pp {v['daily_return_corr']:>6.3f}")

    best = min(results, key=lambda r: abs(r[1]["cagr_diff_pp"]))
    print(f"\n대조 구간: {results[0][1]['start']} ~ {results[0][1]['end']} "
          f"({results[0][1]['years']:.1f}년)")
    print(f"CAGR 오차 최소 drag: {best[0]}% (오차 {best[1]['cagr_diff_pp']:+.2f}pp)")


if __name__ == "__main__":
    main()
