"""백테스터용 일봉 데이터 다운로드 (yfinance).

PLAN.md §4.3 데이터 방침: 체결가 계산은 원종가(raw close), 배당은 별도 현금흐름.
yfinance는 auto_adjust=False일 때 close가 "액면분할은 소급 조정되었지만 배당은
조정되지 않은" 원종가를 반환한다 — 이 프로젝트가 원하는 방침과 정확히 일치한다.
(auto_adjust=True를 쓰면 배당까지 반영된 "Adj Close"가 close 자리에 들어와서
LOC/지정가 주문가 계산이 실제 체결가와 어긋나는 문제가 생긴다.)

실행: python3 fetch_data.py
출력: backtester/data/<TICKER>.csv (date,open,high,low,close,volume,dividend)
      backtester/data/META.md (다운로드 메타 + 종목별 결과)
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

TICKERS = ["TQQQ", "SOXL", "QQQ", "SPY", "UPRO", "TMF", "TLT", "GLD", "SHY"]
DATA_DIR = Path(__file__).resolve().parent / "data"

MAX_RETRIES = 5
BASE_DELAY = 3.0          # 초, 지수 백오프 기준값 (3,6,12,24,48...)
INTER_TICKER_DELAY = 2.0  # 초, 종목 간 딜레이 (레이트리밋 대비)


def _fetch_one(ticker: str) -> pd.DataFrame:
    """history() 호출을 지수 백오프로 재시도. 쿠키 전략(basic/csrf) 폴백도 시도."""
    import yfinance.data as yfdata

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="max", auto_adjust=False, actions=True)
            if df is None or df.empty:
                raise RuntimeError("empty response")
            return df
        except Exception as exc:  # yfinance는 레이트리밋/네트워크 오류를 다양한 예외로 던짐
            last_exc = exc
            if attempt == 1:
                # 첫 실패는 쿠키 전략(basic<->csrf) 토글 후 바로 한 번 더 시도해본다.
                # (신버전 yfinance는 crumb 발급용 쿠키 획득에 실패하면 자동 폴백이
                # 되지 않는 경우가 있어 수동으로 토글한다.)
                try:
                    yd = yfdata.YfData()
                    other = "csrf" if yd._cookie_strategy == "basic" else "basic"
                    yd._set_cookie_strategy(other)
                except Exception:
                    pass
            delay = BASE_DELAY * (2 ** (attempt - 1))
            print(f"[{ticker}] attempt {attempt}/{MAX_RETRIES} failed: {exc!r} -> retry in {delay:.0f}s",
                  file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(delay)
    raise RuntimeError(f"{ticker}: all {MAX_RETRIES} attempts failed") from last_exc


def fetch_ticker(ticker: str) -> tuple[bool, str]:
    try:
        raw = _fetch_one(ticker)
    except Exception as exc:
        return False, repr(exc)

    df = raw.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Volume": "volume", "Dividends": "dividend",
    })
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    cols = ["open", "high", "low", "close", "volume", "dividend"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return False, f"missing columns from yfinance response: {missing}"
    df = df[cols].sort_index()
    df = df[~df.index.duplicated(keep="last")]

    out = DATA_DIR / f"{ticker}.csv"
    df.to_csv(out, date_format="%Y-%m-%d")
    return True, f"{df.index[0].date()} ~ {df.index[-1].date()}, {len(df)} rows -> {out.name}"


def _write_meta(results: dict[str, tuple[bool, str]]) -> None:
    meta_path = DATA_DIR / "META.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 데이터 다운로드 메타",
        "",
        f"- 다운로드 시도 일자: {now}",
        f"- yfinance 버전: {yf.__version__}",
        f"- pandas 버전: {pd.__version__}",
        "- 조정 방침: `auto_adjust=False, actions=True` — close는 원종가",
        "  (액면분할은 소급 조정, 배당은 미조정). dividend 컬럼은 배당락일 기준",
        "  주당 현금배당액(별도 현금흐름, 재투자 여부는 전략/합성 로직에서 결정).",
        "- 컬럼: date,open,high,low,close,volume,dividend",
        "",
        "## 종목별 결과",
        "",
        "| 종목 | 상태 | 내용 |",
        "|---|---|---|",
    ]
    for ticker in TICKERS:
        ok, msg = results.get(ticker, (False, "not attempted"))
        lines.append(f"| {ticker} | {'OK' if ok else 'FAIL'} | {msg} |")
    meta_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, tuple[bool, str]] = {}
    for i, ticker in enumerate(TICKERS):
        ok, msg = fetch_ticker(ticker)
        results[ticker] = (ok, msg)
        print(f"{'OK' if ok else 'FAIL'} {ticker}: {msg}")
        if i < len(TICKERS) - 1:
            time.sleep(INTER_TICKER_DELAY)

    _write_meta(results)

    failed = [t for t, (ok, _) in results.items() if not ok]
    if failed:
        print(f"\n실패 종목: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
