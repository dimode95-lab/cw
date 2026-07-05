"""18:10 잡 — 무한매수법 v4.0 주문표 계산 후 주문 접수, 텔레그램 통보."""
import traceback

from .config import load_settings
from .kis_client import KisClient, kst_today
from .mubae import (State, load_stock_cfgs, one_buy_amount, plan_orders,
                    star_pct, star_point)
from .sheets import append_rows
from .state_store import add_pending, get_unsettled, load_state, save_state, settle_all
from .storage import save_order
from .telegram_notify import send_telegram

SIDE_KO = {"buy": "매수", "sell": "매도"}
INTENT_KO = {
    "big_buy": "큰수매수", "star_half": "별점매수(½)", "avg_half": "평단매수(½)",
    "star_full": "별점매수", "ladder": "추가매수", "quarter_sell": "쿼터매도",
    "limit_sell": "지정가매도", "reverse_moc": "리버스 MOC매도",
    "reverse_sell": "리버스매도", "quarter_buy": "쿼터매수", "quarter_buy_ladder": "추가매수",
}


def _fmt_order(o, result=None) -> str:
    price = "MOC(종가)" if o.order_type == "MOC" else f"${o.price:.2f}"
    line = f"{INTENT_KO.get(o.intent, o.intent)} {o.qty}주 @ {price}"
    if o.order_type == "LOC":
        line += " [LOC]"
    if result and not result["ok"]:
        line = "❌ " + line + f"\n      └ {result['msg']}"
    return line


def run() -> None:
    settings = load_settings()
    client = KisClient(settings)
    now = kst_today()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    env_label = "DRY-RUN" if settings.dry_run else ("모의투자" if settings.is_paper else "실전투자")

    sections, sheet_rows, had_error = [], [], False

    for cfg in load_stock_cfgs():
        if not cfg.enabled:
            continue
        st = load_state(settings, cfg.symbol)
        if st is None:
            sections.append(f"■ {cfg.symbol}\n⚠️ 상태 미초기화 — 서버에서 `python -m moap init-state` 를 먼저 실행하세요")
            had_error = True
            continue

        # 전일 주문이 정산 안 된 채 남아있으면 경고 후 초기화 (LOC/MOC는 당일 만료)
        stale = get_unsettled(settings, cfg.symbol)
        if stale:
            settle_all(settings, cfg.symbol)

        try:
            closes = client.get_daily_closes(cfg.exchange, cfg.symbol, count=6)
            prev_close = closes[0]["close"]
            avg5 = sum(c["close"] for c in closes[:5]) / min(len(closes), 5)
            orders = plan_orders(cfg, st, prev_close, avg5)
        except Exception:
            sections.append(f"■ {cfg.symbol}\n🚨 주문표 계산 실패:\n{traceback.format_exc(limit=2)}")
            had_error = True
            continue

        lines = []
        for o in orders:
            if settings.dry_run:
                result = {"ok": True, "order_no": "DRY-RUN", "msg": "", "raw": {}}
            else:
                try:
                    result = client.place_order(o.side, cfg.symbol, cfg.exchange,
                                                o.qty, o.price, o.order_type)
                except Exception as e:
                    result = {"ok": False, "order_no": "", "msg": str(e), "raw": {}}
            if not result["ok"]:
                had_error = True
            lines.append(_fmt_order(o, result))

            add_pending(settings, now.isoformat(), cfg.symbol, {
                "intent": o.intent, "side": o.side, "order_type": o.order_type,
                "price": o.price, "qty": o.qty, "t_inc": o.t_inc,
                "order_no": result["order_no"], "placed_ok": result["ok"],
            })
            save_order(settings, now.isoformat(), o.side, cfg.symbol, cfg.exchange,
                       o.qty, o.price, result)
            sheet_rows.append([now_str, env_label, SIDE_KO[o.side] + f"({o.order_type})",
                               cfg.symbol, cfg.exchange, o.qty, o.price,
                               result["order_no"], "성공" if result["ok"] else "실패",
                               result["msg"]])

        sp_txt = ""
        if st.shares > 0:
            sp_txt = f" · 별지점 ${star_point(cfg, st):.2f} ({star_pct(cfg, st.T):+.2f}%)"
        header = (f"■ {cfg.symbol} [{st.mode}] {cfg.divisions}분할 · 사이클{st.cycle_no}\n"
                  f"  T={st.T:.3f} · 평단 ${st.avg_price:.2f} · 보유 {st.shares}주\n"
                  f"  잔금 ${st.cash:,.2f} · 1회 ${one_buy_amount(cfg, st):,.2f}{sp_txt}\n"
                  f"  전일종가 ${prev_close:.2f}")
        buys = [l for o, l in zip(orders, lines) if o.side == "buy"]
        sells = [l for o, l in zip(orders, lines) if o.side == "sell"]
        body = ""
        if buys:
            body += "\n  [매수]\n   " + "\n   ".join(buys)
        if sells:
            body += "\n  [매도]\n   " + "\n   ".join(sells)
        if not orders:
            body = "\n  (오늘 주문 없음)"
        if stale:
            body += f"\n  ⚠️ 전일 미정산 주문 {len(stale)}건 자동 만료 처리"
        sections.append(header + body)

        save_state(settings, st, now.isoformat())

    append_rows(settings, "주문", sheet_rows)

    title = "📥 [무한매수 v4.0] 주문 완료" if not had_error else "⚠️ [무한매수 v4.0] 주문 일부 실패"
    footer = "\n\n체결 결과는 내일 08:20에 알려드릴게요."
    if settings.dry_run:
        footer += "\n(DRY_RUN — 실제 주문 전송 없음, 내일 종가로 체결 시뮬레이션)"
    send_telegram(settings, f"{title} ({env_label})\n{now_str}\n\n"
                            + "\n\n".join(sections) + footer)


if __name__ == "__main__":
    run()
