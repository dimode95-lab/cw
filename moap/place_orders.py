"""18:10 잡 — 매수 2 / 매도 2 예약주문 후 텔레그램으로 결과 통보."""
import traceback

from .config import load_settings
from .kis_client import KisClient, kst_today
from .sheets import append_rows
from .storage import save_order
from .strategy import select_orders
from .telegram_notify import send_telegram

SIDE_KO = {"buy": "매수", "sell": "매도"}


def run() -> None:
    settings = load_settings()
    client = KisClient(settings)
    now = kst_today()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    env_label = "모의투자" if settings.is_paper else "실전투자"

    try:
        specs = select_orders(client)
    except Exception:
        send_telegram(settings, f"🚨 [모압매수] 주문 준비 실패 ({now_str})\n"
                                f"종목 선정/시세 조회 중 오류:\n{traceback.format_exc(limit=3)}")
        raise

    lines, sheet_rows, fail_count = [], [], 0
    for spec in specs:
        if settings.dry_run:
            result = {"ok": True, "order_no": "DRY-RUN", "msg": "DRY_RUN 모드 (실제 주문 없음)", "raw": {}}
        else:
            try:
                result = client.place_reserved_order(
                    spec.side, spec.symbol, spec.exchange, spec.qty, spec.price)
            except Exception as e:
                result = {"ok": False, "order_no": "", "msg": str(e), "raw": {}}

        mark = "✅" if result["ok"] else "❌"
        if not result["ok"]:
            fail_count += 1
        lines.append(f"{mark} {SIDE_KO[spec.side]} {spec.symbol} {spec.qty}주 @ ${spec.price:.2f}"
                     + ("" if result["ok"] else f"\n   └ {result['msg']}"))

        save_order(settings, now.isoformat(), spec.side, spec.symbol,
                   spec.exchange, spec.qty, spec.price, result)
        sheet_rows.append([now_str, env_label, SIDE_KO[spec.side], spec.symbol,
                           spec.exchange, spec.qty, spec.price,
                           result["order_no"], "성공" if result["ok"] else "실패",
                           result["msg"]])

    append_rows(settings, "주문", sheet_rows)

    if fail_count == 0:
        title = f"📥 [모압매수] 예약주문 완료 ({env_label})"
    else:
        title = f"⚠️ [모압매수] 예약주문 일부 실패 {fail_count}/{len(specs)} ({env_label})"
    dry = "\n(DRY_RUN — 실제 주문은 전송되지 않았습니다)" if settings.dry_run else ""
    send_telegram(settings, f"{title}\n{now_str}\n\n" + "\n".join(lines)
                            + f"\n\n체결 결과는 내일 08:20에 알려드릴게요.{dry}")


if __name__ == "__main__":
    run()
