"""일봉 루프 엔진 (PLAN.md §4.1/§4.4).

매 거래일:
  (a) 전략 on_bar 호출 → 주문 수집
  (b) broker_sim으로 체결 판정
  (c) Portfolio 갱신 (현금·수량·평단 + 배당 발생 시 보유수량×배당 현금 가산)
  (d) 체결이 하나라도 있으면 on_fill 호출 (하루 전체를 1회로)
  (e) 일별 평가액(현금+보유평가액) 기록

결과: equity curve DataFrame + 거래 로그 + 연도별 실현손익(세금 계산용).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal
from typing import Any, Dict, List

import pandas as pd

from broker_sim import DEFAULT_FEE_RATE, simulate_day
from core import OHLC, Order, Portfolio, Side, Strategy


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame  # columns: date, cash, market_value, equity
    trades: pd.DataFrame  # columns: date, ticker, side, type, role, qty, price, fee
    realized_pnl_by_year: Dict[int, Decimal]  # 세금 계산용 (매도가-평단)×수량-수수료의 연도별 합
    rejected_log: pd.DataFrame  # 참고용: 거부된 주문 (date, ticker, side, type, role, reason)
    final_state: Any


def run_backtest(
    strategy: Strategy,
    price_data: Dict[str, List[OHLC]],
    initial_cash: Decimal,
    initial_state: Any,
    fee_rate: Decimal = DEFAULT_FEE_RATE,
) -> BacktestResult:
    """일봉 루프를 처음부터 끝까지 실행한다.

    price_data: {ticker: [OHLC, ...]}. 각 티커 리스트는 날짜순 정렬을 요구하지 않는다
    (내부에서 날짜 기준 dict로 재색인). 거래 캘린더는 모든 티커의 날짜 합집합 —
    상장일이 다른 종목(UPRO/TMF 등)이 섞여도 없는 날은 그냥 bars에서 빠진다.
    initial_state: 전략이 정의하는 초기 상태 객체(엔진은 내용을 해석하지 않는다).
    """
    bars_by_ticker_date: Dict[str, Dict[Date, OHLC]] = {
        ticker: {bar.date: bar for bar in bars} for ticker, bars in price_data.items()
    }
    all_dates = sorted({bar.date for bars in price_data.values() for bar in bars})

    portfolio = Portfolio(cash=initial_cash)
    state = initial_state

    last_close: Dict[str, Decimal] = {}
    equity_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    rejected_rows: List[Dict[str, Any]] = []
    realized_pnl_by_year: Dict[int, Decimal] = {}

    for trade_date in all_dates:
        bars_today: Dict[str, OHLC] = {}
        for ticker, by_date in bars_by_ticker_date.items():
            bar = by_date.get(trade_date)
            if bar is not None:
                bars_today[ticker] = bar
                last_close[ticker] = bar.close

        # (a) 전략 on_bar 호출 → 주문 수집. portfolio는 read-only 스냅샷만 전달.
        orders: List[Order] = strategy.on_bar(state, bars_today, portfolio.snapshot())

        # 배당은 "그날 새로 산 주식"이 아니라 "그날 이전부터 보유하던 주식" 기준이어야
        # 하므로, 체결 반영 전 보유수량을 미리 떠 둔다.
        qty_before: Dict[str, Any] = {
            ticker: portfolio.position(ticker).qty for ticker in bars_today
        }

        # (b) broker_sim으로 체결 판정 (여기선 portfolio를 읽기만 함)
        fill_result = simulate_day(orders, bars_today, portfolio, trade_date, fee_rate)

        # (c) Portfolio 갱신 (현금·수량·평단)
        for fill in fill_result.fills:
            order = fill.order
            if order.side == Side.BUY:
                portfolio.apply_buy(order.ticker, order.qty, fill.price, fill.fee)
            else:
                realized = portfolio.apply_sell(order.ticker, order.qty, fill.price, fill.fee)
                realized_pnl_by_year[trade_date.year] = (
                    realized_pnl_by_year.get(trade_date.year, Decimal("0")) + realized
                )
            trade_rows.append(
                {
                    "date": trade_date,
                    "ticker": order.ticker,
                    "side": order.side.value,
                    "type": order.type.value,
                    "role": order.role,
                    "qty": order.qty,
                    "price": fill.price,
                    "fee": fill.fee,
                }
            )

        for rej in fill_result.rejected:
            rejected_rows.append(
                {
                    "date": trade_date,
                    "ticker": rej.order.ticker,
                    "side": rej.order.side.value,
                    "type": rej.order.type.value,
                    "role": rej.order.role,
                    "reason": rej.reason,
                }
            )

        # (c-계속) 배당 가산 — 체결 반영 이전 보유수량 기준
        for ticker, bar in bars_today.items():
            if bar.dividend and bar.dividend != 0:
                qty = qty_before.get(ticker, 0)
                if qty:
                    portfolio.apply_dividend(ticker, bar.dividend)

        # (d) 체결이 있으면 on_fill을 하루에 1회 호출
        if fill_result.fills:
            state = strategy.on_fill(state, fill_result.fills)

        # (e) 일별 평가액 기록: 현금 + 보유수량 × 최신 종가(오늘 데이터 없는 티커는 직전 종가 유지)
        market_value = Decimal("0")
        for ticker in bars_by_ticker_date.keys():
            qty = portfolio.position(ticker).qty
            if qty and ticker in last_close:
                market_value += last_close[ticker] * qty
        equity_rows.append(
            {
                "date": trade_date,
                "cash": portfolio.cash,
                "market_value": market_value,
                "equity": portfolio.cash + market_value,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    rejected_log = pd.DataFrame(rejected_rows)

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        realized_pnl_by_year=realized_pnl_by_year,
        rejected_log=rejected_log,
        final_state=state,
    )
