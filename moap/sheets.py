"""구글 스프레드시트 기록 — 로우데이터를 '주문'/'체결' 워크시트에 누적 저장."""
from .config import Settings

ORDER_HEADER = ["기록일시", "환경", "구분", "종목", "거래소", "수량", "지정가",
                "주문번호", "성공여부", "응답메시지"]
FILL_HEADER = ["기록일시", "주문일", "구분", "종목", "주문수량", "체결수량",
               "체결단가", "체결금액", "통화", "처리상태", "주문번호"]

_HEADERS = {"주문": ORDER_HEADER, "체결": FILL_HEADER}


def _open_sheet(settings: Settings):
    import gspread
    gc = gspread.service_account(filename=settings.google_sa_file)
    return gc.open_by_key(settings.sheets_id)


def append_rows(settings: Settings, worksheet: str, rows: list[list]) -> bool:
    """워크시트에 행 추가. 시트/워크시트가 없으면 헤더와 함께 생성."""
    if not settings.sheets_id:
        print(f"[sheets] GOOGLE_SHEETS_ID 미설정 — 기록 생략 ({worksheet}, {len(rows)}행)")
        return False
    try:
        sh = _open_sheet(settings)
        try:
            ws = sh.worksheet(worksheet)
        except Exception:
            ws = sh.add_worksheet(title=worksheet, rows=1000, cols=len(_HEADERS[worksheet]))
            ws.append_row(_HEADERS[worksheet])
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        return True
    except Exception as e:  # 시트 기록 실패가 주문 흐름을 막으면 안 됨
        print(f"[sheets] 기록 실패 ({worksheet}): {e}")
        return False
