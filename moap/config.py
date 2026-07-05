"""환경설정 로더 — .env 파일과 환경변수에서 설정을 읽는다."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

KIS_BASE_URLS = {
    "real": "https://openapi.koreainvestment.com:9443",
    "paper": "https://openapivts.koreainvestment.com:29443",
}


@dataclass
class Settings:
    kis_env: str            # "paper"(모의) | "real"(실전)
    kis_app_key: str
    kis_app_secret: str
    kis_account_no: str     # 계좌번호 앞 8자리
    kis_account_prod: str   # 계좌번호 뒤 2자리 (보통 "01")
    telegram_bot_token: str
    telegram_chat_id: str
    sheets_id: str          # 구글 스프레드시트 ID (URL의 /d/ 뒤 부분)
    google_sa_file: str     # 구글 서비스계정 JSON 파일 경로
    dry_run: bool           # True면 실제 주문 없이 알림/기록만
    db_path: str

    @property
    def kis_base_url(self) -> str:
        return KIS_BASE_URLS[self.kis_env]

    @property
    def is_paper(self) -> bool:
        return self.kis_env == "paper"


def _account_parts(raw: str) -> tuple[str, str]:
    """'12345678-01' 또는 '1234567801' 형식 모두 허용."""
    raw = raw.replace("-", "").strip()
    if len(raw) < 10:
        return raw[:8], "01"
    return raw[:8], raw[8:10]


def load_settings() -> Settings:
    cano, prod = _account_parts(os.getenv("KIS_ACCOUNT_NO", ""))
    env = os.getenv("KIS_ENV", "paper").lower()
    if env not in KIS_BASE_URLS:
        raise ValueError(f"KIS_ENV 값은 paper 또는 real 이어야 합니다: {env}")
    return Settings(
        kis_env=env,
        kis_app_key=os.getenv("KIS_APP_KEY", ""),
        kis_app_secret=os.getenv("KIS_APP_SECRET", ""),
        kis_account_no=cano,
        kis_account_prod=prod,
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        sheets_id=os.getenv("GOOGLE_SHEETS_ID", ""),
        google_sa_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json")),
        dry_run=os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes"),
        db_path=os.getenv("DB_PATH", str(BASE_DIR / "moap.db")),
    )
