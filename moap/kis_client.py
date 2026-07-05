"""한국투자증권 OpenAPI 클라이언트 (해외주식 - 미국).

지원 기능:
  - 접근토큰 발급/캐시 (KIS는 1분 내 재발급을 차단하므로 파일 캐시 필수)
  - 해외주식 현재가 조회
  - 해외주식 미국 예약주문 (매수/매도)
  - 해외주식 주문체결내역 조회

주의: TR ID는 KIS Developers 문서 기준이며, 계정/시점에 따라 다를 수 있으니
      https://apiportal.koreainvestment.com 에서 최종 확인하세요.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .config import Settings

# 거래소 코드: 주문용(OVRS_EXCG_CD) ↔ 시세조회용(EXCD)
EXCD_MAP = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}

# TR ID 매핑 (해외주식 미국)
TR_IDS = {
    "real": {
        "resv_buy": "TTTT3016U",   # 미국 예약 매수
        "resv_sell": "TTTT3017U",  # 미국 예약 매도
        "ccnl": "TTTS3035R",       # 주문체결내역
    },
    "paper": {
        "resv_buy": "VTTT3016U",
        "resv_sell": "VTTT3017U",
        "ccnl": "VTTS3035R",
    },
}


class KisError(RuntimeError):
    pass


class KisClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.base = settings.kis_base_url
        self.tr = TR_IDS[settings.kis_env]
        self._token_cache = Path.home() / f".kis_token_{settings.kis_env}.json"

    # ── 토큰 ──────────────────────────────────────────────
    def _get_token(self) -> str:
        if self._token_cache.exists():
            try:
                cached = json.loads(self._token_cache.read_text())
                if cached.get("expires_at", 0) > time.time() + 600:
                    return cached["access_token"]
            except (json.JSONDecodeError, KeyError):
                pass
        resp = requests.post(
            f"{self.base}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.s.kis_app_key,
                "appsecret": self.s.kis_app_secret,
            },
            timeout=10,
        )
        data = resp.json()
        if "access_token" not in data:
            raise KisError(f"토큰 발급 실패: {data}")
        self._token_cache.write_text(json.dumps({
            "access_token": data["access_token"],
            "expires_at": time.time() + int(data.get("expires_in", 86400)),
        }))
        return data["access_token"]

    def _headers(self, tr_id: str, body: dict | None = None) -> dict:
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.s.kis_app_key,
            "appsecret": self.s.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if body is not None:
            hk = requests.post(
                f"{self.base}/uapi/hashkey",
                headers={
                    "content-type": "application/json; charset=utf-8",
                    "appkey": self.s.kis_app_key,
                    "appsecret": self.s.kis_app_secret,
                },
                json=body,
                timeout=10,
            ).json().get("HASH")
            if hk:
                headers["hashkey"] = hk
        return headers

    # ── 시세 ──────────────────────────────────────────────
    def get_price(self, exchange: str, symbol: str) -> float:
        """해외주식 현재체결가 (HHDFS00000300)."""
        resp = requests.get(
            f"{self.base}/uapi/overseas-price/v1/quotations/price",
            headers=self._headers("HHDFS00000300"),
            params={"AUTH": "", "EXCD": EXCD_MAP.get(exchange, exchange), "SYMB": symbol},
            timeout=10,
        )
        data = resp.json()
        last = (data.get("output") or {}).get("last")
        if not last:
            raise KisError(f"{symbol} 현재가 조회 실패: {data.get('msg1', data)}")
        return float(last)

    # ── 예약주문 ──────────────────────────────────────────
    def place_reserved_order(self, side: str, symbol: str, exchange: str,
                             qty: int, price: float) -> dict:
        """미국 주식 예약주문. side: 'buy' | 'sell'. 지정가 주문.

        반환: {'ok': bool, 'order_no': str, 'msg': str, 'raw': dict}
        """
        tr_id = self.tr["resv_buy"] if side == "buy" else self.tr["resv_sell"]
        body = {
            "CANO": self.s.kis_account_no,
            "ACNT_PRDT_CD": self.s.kis_account_prod,
            "PDNO": symbol,
            "OVRS_EXCG_CD": exchange,
            "FT_ORD_QTY": str(qty),
            "FT_ORD_UNPR3": f"{price:.2f}",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",  # 지정가
        }
        if side == "sell":
            body["SLL_TYPE"] = "00"  # 일반매도
        resp = requests.post(
            f"{self.base}/uapi/overseas-stock/v1/trading/order-resv",
            headers=self._headers(tr_id, body),
            json=body,
            timeout=10,
        )
        data = resp.json()
        ok = data.get("rt_cd") == "0"
        output = data.get("output") or {}
        return {
            "ok": ok,
            "order_no": output.get("ODNO") or output.get("OVRS_RSVN_ODNO", ""),
            "msg": data.get("msg1", "").strip(),
            "raw": data,
        }

    # ── 체결내역 ──────────────────────────────────────────
    def get_ccnl(self, start_date: str, end_date: str) -> list[dict]:
        """해외주식 주문체결내역 (기간 조회, YYYYMMDD). 연속조회 포함."""
        results: list[dict] = []
        fk, nk = "", ""
        for _ in range(10):  # 연속조회 최대 10페이지
            resp = requests.get(
                f"{self.base}/uapi/overseas-stock/v1/trading/inquire-ccnl",
                headers=self._headers(self.tr["ccnl"]),
                params={
                    "CANO": self.s.kis_account_no,
                    "ACNT_PRDT_CD": self.s.kis_account_prod,
                    "PDNO": "%",
                    "ORD_STRT_DT": start_date,
                    "ORD_END_DT": end_date,
                    "SLL_BUY_DVSN": "00",     # 전체
                    "CCLD_NCCS_DVSN": "00",   # 체결+미체결 전체
                    "OVRS_EXCG_CD": "%",
                    "SORT_SQN": "DS",
                    "ORD_DT": "",
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "CTX_AREA_FK200": fk,
                    "CTX_AREA_NK200": nk,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("rt_cd") != "0":
                raise KisError(f"체결내역 조회 실패: {data.get('msg1', data)}")
            results.extend(data.get("output") or [])
            tr_cont = resp.headers.get("tr_cont", "")
            if tr_cont not in ("F", "M"):
                break
            fk = data.get("ctx_area_fk200", "").strip()
            nk = data.get("ctx_area_nk200", "").strip()
            time.sleep(0.2)
        return results


def kst_today() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Seoul"))


def yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")
