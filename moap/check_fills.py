"""08:20 잡 — 전일 밤 미국장 체결 확인, 상태 갱신, 텔레그램 통보.

DRY_RUN 모드에서는 실제 주문이 없으므로 간밤 종가/고가로 체결을 시뮬레이션한다
(LOC/MOC/지정가 규칙 그대로 — 모의투자 API가 LOC를 지원하지 않아도 전략 검증 가능).
"""
import traceback
from datetime import timedelta

from .config import load_settings
from .kis_client import KisClient, kst_today, yyyymmdd
from .mubae import apply_fills, load_stock_cfgs, one_buy_amount, simulate_fills, star_pct
from .place_orders import INTENT_KO
from .sheets import append_rows
from .state_store import get_unsettled, load_state, save_state, settle_all
from .storage import save_fill
from .telegram_notify import send_telegram


def _real_fills(client: KisClient, pendings: list[dict], start: str, end: str) -> list[dict]:
    """KIS 체결내역을 주문번호로 매칭해 pending 주문의 체결 결과를 만든다."""
    records = {r.get("odno", ""): r for r in client.get_ccnl(start, end)}
    fills = []
    for p in pendings:
        r = records.get(p["order_no"])
        qty = int(float(r.get("ft_ccld_qty") or 0)) if r else 0
        price = float(r.get("ft_ccld_unpr3") or 0) if r else 0.0
        amount = float(r.get("ft_ccld_amt3") or 0) if r else 0.0
        fills.append({"intent": p["intent"], "side": p["side"], "qty": qty,
                      "price": price, "amount": amount, "t_inc": p["t_inc"]})
    return fills


def run() -> None:
    settings = load_settings()
    client = KisClient(settings)
    now = kst_today()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    env_label = "DRY-RUN" if settings.dry_run else ("모의투자" if settings.is_paper else "실전투자")
    start, end = yyyymmdd(now - timedelta(days=1)), yyyymmdd(now)

    sections, fill_rows, db_rows, diary_rows = [], [], [], []

    for cfg in load_stock_cfgs():
        if not cfg.enabled:
            continue
        st = load_state(settings, cfg.symbol)
        if st is None:
            continue
        pendings = get_unsettled(settings, cfg.symbol)

        try:
            closes = client.get_daily_closes(cfg.exchange, cfg.symbol, count=6)
        except Exception:
            sections.append(f"■ {cfg.symbol}\n🚨 시세 조회 실패:\n{traceback.format_exc(limit=2)}")
            continue
        latest = closes[0]
        close, high, close_date = latest["close"], latest["high"], latest["date"]
        avg5 = sum(c["close"] for c in closes[:5]) / min(len(closes), 5)

        # 간밤에 새 거래일이 없었으면 (미국 휴장) 주문은 만료만 처리
        if st.last_close_date and close_date <= st.last_close_date:
            settle_all(settings, cfg.symbol)
            sections.append(f"■ {cfg.symbol}\n📭 간밤 미국장 휴장 — 주문 만료, 상태 변화 없음")
            continue

        if not pendings:
            st.last_close_date = close_date
            save_state(settings, st, now.isoformat())
            sections.append(f"■ {cfg.symbol}\n(확인할 주문 없음 · 종가 ${close:.2f})")
            continue

        try:
            if settings.dry_run or all(p["order_no"] == "DRY-RUN" for p in pendings):
                fills = simulate_fills(pendings, close, high)
                sim_note = " (시뮬레이션)"
            else:
                fills = _real_fills(client, pendings, start, end)
                sim_note = ""
        except Exception:
            sections.append(f"■ {cfg.symbol}\n🚨 체결 조회 실패:\n{traceback.format_exc(limit=2)}")
            continue

        prev_cycle_no = st.cycle_no
        events = apply_fills(cfg, st, fills, close, close_date)
        settle_all(settings, cfg.symbol)
        save_state(settings, st, now.isoformat())

        # 기록 + 메시지
        lines, filled_n = [], 0
        for f, p in zip(fills, pendings):
            label = INTENT_KO.get(f["intent"], f["intent"])
            if f["qty"] > 0:
                filled_n += 1
                lines.append(f"✅ {label} {f['qty']}주 @ ${f['price']:.2f} (${f['amount']:,.2f})")
            else:
                lines.append(f"— {label} {p['qty']}주 미체결")
            save_fill(settings, now.isoformat(), {
                "ord_date": start, "side": f["side"], "symbol": cfg.symbol,
                "ord_qty": p["qty"], "fill_qty": f["qty"], "fill_price": f["price"],
                "fill_amount": f["amount"], "currency": "USD",
                "status": "체결" if f["qty"] else "미체결", "order_no": p["order_no"] or "",
                "raw": f,
            })
            fill_rows.append([now_str, start, ("매수" if f["side"] == "buy" else "매도") + f"({label})",
                              cfg.symbol, p["qty"], f["qty"], f["price"], f["amount"],
                              "USD", "체결" if f["qty"] else "미체결", p["order_no"] or ""])

        # 구글시트 'DB' 탭 — 업로드한 엑셀 DB 시트와 같은 컬럼
        buys_txt = " / ".join(f"{f['qty']}@{f['price']:.2f}" for f in fills
                              if f["side"] == "buy" and f["qty"]) or "-"
        s1 = next((f"{f['qty']}@{f['price']:.2f}" for f in fills
                   if f["intent"] in ("quarter_sell", "reverse_moc", "reverse_sell") and f["qty"]), "-")
        s2 = next((f"{f['qty']}@{f['price']:.2f}" for f in fills
                   if f["intent"] == "limit_sell" and f["qty"]), "-")
        db_rows.append([now.strftime("%Y-%m-%d"), f"{cfg.symbol} {cfg.divisions}", st.mode,
                        close, round(st.avg_price, 4), st.shares, round(st.T, 6),
                        round(star_pct(cfg, st.T), 4), round(avg5, 3),
                        round(st.shares * st.avg_price, 2), round(st.cash, 2),
                        round(one_buy_amount(cfg, st), 2), round(st.cycle_realized, 2),
                        buys_txt, s1, s2])

        # 사이클 종료 → 수익 일지 (엑셀 '수익 일지' 시트와 같은 컬럼)
        if st.cycle_no > prev_cycle_no:
            p0 = st.last_cycle_principal
            diary_rows.append([now.strftime("%Y-%m-%d"), cfg.symbol, round(p0, 2),
                               round(p0 + st.last_cycle_profit, 2), st.last_cycle_profit,
                               round(st.last_cycle_profit / p0 * 100, 2) if p0 else 0,
                               st.last_cycle_final_t])

        status = (f"  → T={st.T:.3f} · {st.mode} · 평단 ${st.avg_price:.2f}"
                  f" · 보유 {st.shares}주 · 잔금 ${st.cash:,.2f}")
        ev_txt = ("\n  " + "\n  ".join(events)) if events else ""
        sections.append(f"■ {cfg.symbol} 종가 ${close:.2f}{sim_note} — 체결 {filled_n}/{len(pendings)}\n   "
                        + "\n   ".join(lines) + f"\n{status}{ev_txt}")

    append_rows(settings, "체결", fill_rows)
    append_rows(settings, "DB", db_rows)
    if diary_rows:
        append_rows(settings, "수익 일지", diary_rows)

    all_done = all("미체결" not in s and "🚨" not in s for s in sections)
    title = "🎉 [무한매수 v4.0] 체결 완료" if all_done else "📊 [무한매수 v4.0] 체결 결과"
    send_telegram(settings, f"{title} ({env_label})\n{now_str}\n\n" + "\n\n".join(sections))


if __name__ == "__main__":
    run()
