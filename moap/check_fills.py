"""08:20 잡 — 전일 예약주문의 체결 결과를 조회해 텔레그램으로 통보."""
from datetime import timedelta

from .config import load_settings
from .kis_client import KisClient, KisError, kst_today, yyyymmdd
from .sheets import append_rows
from .storage import save_fill
from .telegram_notify import send_telegram

SIDE_CODE = {"01": "매도", "02": "매수"}


def run() -> None:
    settings = load_settings()
    client = KisClient(settings)
    now = kst_today()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    env_label = "모의투자" if settings.is_paper else "실전투자"

    start = yyyymmdd(now - timedelta(days=1))  # 전일 18:10 주문분부터
    end = yyyymmdd(now)

    try:
        records = client.get_ccnl(start, end)
    except KisError as e:
        send_telegram(settings, f"🚨 [모압매수] 체결 조회 실패 ({now_str})\n{e}")
        raise

    if not records:
        send_telegram(settings, f"📭 [모압매수] 체결 내역 없음 ({env_label})\n{now_str}\n"
                                f"{start}~{end} 조회 결과 주문 내역이 없습니다.\n"
                                f"(미국 휴장일이거나 예약주문이 접수되지 않았을 수 있어요)")
        return

    lines, sheet_rows = [], []
    filled = unfilled = 0
    for r in records:
        side = SIDE_CODE.get(r.get("sll_buy_dvsn_cd", ""), r.get("sll_buy_dvsn_cd_name", "?"))
        symbol = r.get("pdno", "?")
        ord_qty = int(float(r.get("ft_ord_qty") or 0))
        fill_qty = int(float(r.get("ft_ccld_qty") or 0))
        fill_price = float(r.get("ft_ccld_unpr3") or 0)
        fill_amt = float(r.get("ft_ccld_amt3") or 0)
        currency = r.get("tr_crcy_cd", "USD")
        status = (r.get("prcs_stat_name") or "").strip()
        ord_date = r.get("ord_dt", "")
        order_no = r.get("odno", "")

        if fill_qty >= ord_qty and ord_qty > 0:
            filled += 1
            lines.append(f"✅ {side} {symbol} {fill_qty}주 체결 @ ${fill_price:.2f}"
                         f" (총 ${fill_amt:,.2f})")
        elif fill_qty > 0:
            unfilled += 1
            lines.append(f"◐ {side} {symbol} 부분체결 {fill_qty}/{ord_qty}주 @ ${fill_price:.2f}")
        else:
            unfilled += 1
            lines.append(f"❌ {side} {symbol} 미체결 (주문 {ord_qty}주, 상태: {status or '미체결'})")

        save_fill(settings, now.isoformat(), {
            "ord_date": ord_date, "side": side, "symbol": symbol,
            "ord_qty": ord_qty, "fill_qty": fill_qty, "fill_price": fill_price,
            "fill_amount": fill_amt, "currency": currency, "status": status,
            "order_no": order_no, "raw": r,
        })
        sheet_rows.append([now_str, ord_date, side, symbol, ord_qty, fill_qty,
                           fill_price, fill_amt, currency, status, order_no])

    append_rows(settings, "체결", sheet_rows)

    if unfilled == 0:
        title = f"🎉 [모압매수] 체결 완료 ({env_label})"
    else:
        title = f"📊 [모압매수] 체결 결과 — 체결 {filled} / 미체결·부분 {unfilled} ({env_label})"
    send_telegram(settings, f"{title}\n{now_str} 기준, 주문일 {start}~{end}\n\n" + "\n".join(lines))


if __name__ == "__main__":
    run()
