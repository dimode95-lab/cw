"""텔레그램 알림 전송."""
import requests

from .config import Settings


def send_telegram(settings: Settings, text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print("[telegram] 토큰/챗ID 미설정 — 전송 생략:\n" + text)
        return False
    resp = requests.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": text},
        timeout=10,
    )
    ok = resp.status_code == 200 and resp.json().get("ok", False)
    if not ok:
        print(f"[telegram] 전송 실패: {resp.status_code} {resp.text[:300]}")
    return ok
