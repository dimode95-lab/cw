"""CLI 진입점.

사용법:
  python -m moap place          # 무한매수 주문표 계산+주문 (18:10 크론)
  python -m moap check          # 체결 확인+상태 갱신 (08:20 크론)
  python -m moap init-state     # 무한매수 상태 초기화 (T=0, 잔금=원금)
  python -m moap status         # 현재 상태 출력 (+텔레그램 전송: status send)
  python -m moap test-telegram  # 텔레그램 연결 테스트
  python -m moap test-sheets    # 구글시트 연결 테스트
  python -m moap test-kis       # KIS 토큰/시세 테스트
"""
import sys


def _status_text() -> str:
    from .config import load_settings
    from .mubae import load_stock_cfgs, one_buy_amount, star_pct, star_point
    from .state_store import load_state
    settings = load_settings()
    parts = []
    for cfg in load_stock_cfgs():
        st = load_state(settings, cfg.symbol)
        if st is None:
            parts.append(f"■ {cfg.symbol}: 상태 없음 (init-state 필요)")
            continue
        star = f" · 별지점 ${star_point(cfg, st):.2f} ({star_pct(cfg, st.T):+.2f}%)" if st.shares else ""
        parts.append(
            f"■ {cfg.symbol} [{st.mode}] 사이클{st.cycle_no} ({cfg.divisions}분할)\n"
            f"  T={st.T:.3f} · 평단 ${st.avg_price:.2f} · 보유 {st.shares}주{star}\n"
            f"  원금 ${st.principal:,.2f} · 잔금 ${st.cash:,.2f} · 1회 ${one_buy_amount(cfg, st):,.2f}\n"
            f"  실현손익 누적 ${st.total_realized:,.2f}")
    return "📋 [무한매수 v4.0] 현재 상태\n\n" + "\n\n".join(parts)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "place":
        from .place_orders import run
        run()
    elif cmd == "check":
        from .check_fills import run
        run()
    elif cmd == "init-state":
        from .config import load_settings
        from .kis_client import kst_today
        from .mubae import State, load_stock_cfgs
        from .state_store import load_state, save_state
        settings = load_settings()
        force = "--force" in sys.argv
        for cfg in load_stock_cfgs():
            if load_state(settings, cfg.symbol) and not force:
                print(f"{cfg.symbol}: 이미 상태 존재 — 초기화하려면 --force")
                continue
            st = State(symbol=cfg.symbol, principal=cfg.principal, cash=cfg.principal,
                       cycle_start=kst_today().strftime("%Y-%m-%d"))
            save_state(settings, st, kst_today().isoformat())
            print(f"{cfg.symbol}: 초기화 완료 (원금 ${cfg.principal:,.2f}, {cfg.divisions}분할, T=0)")
    elif cmd == "status":
        text = _status_text()
        print(text)
        if len(sys.argv) > 2 and sys.argv[2] == "send":
            from .config import load_settings
            from .telegram_notify import send_telegram
            send_telegram(load_settings(), text)
    elif cmd == "test-telegram":
        from .config import load_settings
        from .telegram_notify import send_telegram
        ok = send_telegram(load_settings(), "✅ [무한매수] 텔레그램 연결 테스트 성공!")
        print("전송 성공" if ok else "전송 실패 — TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 확인")
    elif cmd == "test-sheets":
        from .config import load_settings
        from .kis_client import kst_today
        from .sheets import append_rows
        now = kst_today().strftime("%Y-%m-%d %H:%M")
        ok = append_rows(load_settings(), "주문",
                         [[now, "테스트", "-", "TEST", "-", 0, 0, "-", "연결테스트", "OK"]])
        print("기록 성공" if ok else "기록 실패 — GOOGLE_SHEETS_ID / 서비스계정 공유 설정 확인")
    elif cmd == "test-kis":
        from .config import load_settings
        from .kis_client import KisClient
        client = KisClient(load_settings())
        price = client.get_price("NASD", "TQQQ")
        closes = client.get_daily_closes("NASD", "TQQQ", count=5)
        print(f"KIS 연결 성공 — TQQQ 현재가 ${price}, 최근 종가 {[c['close'] for c in closes]}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
