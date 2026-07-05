"""CLI 진입점.

사용법:
  python -m moap place          # 예약주문 실행 (18:10 크론)
  python -m moap check          # 체결 확인 (08:20 크론)
  python -m moap test-telegram  # 텔레그램 연결 테스트
  python -m moap test-sheets    # 구글시트 연결 테스트
  python -m moap test-kis       # KIS 토큰/시세 테스트
"""
import sys


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "place":
        from .place_orders import run
        run()
    elif cmd == "check":
        from .check_fills import run
        run()
    elif cmd == "test-telegram":
        from .config import load_settings
        from .telegram_notify import send_telegram
        ok = send_telegram(load_settings(), "✅ [모압매수] 텔레그램 연결 테스트 성공!")
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
        price = client.get_price("NASD", "AAPL")
        print(f"KIS 연결 성공 — AAPL 현재가: ${price}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
