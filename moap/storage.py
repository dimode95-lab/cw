"""SQLite 로컬 백업 저장소 — 구글시트 장애 시에도 로우데이터가 남도록 이중 기록."""
import json
import sqlite3
from contextlib import closing

from .config import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    env TEXT NOT NULL,
    side TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    qty INTEGER NOT NULL,
    price REAL,
    order_no TEXT,
    ok INTEGER NOT NULL,
    msg TEXT,
    raw_json TEXT
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    ord_date TEXT,
    side TEXT,
    symbol TEXT,
    ord_qty INTEGER,
    fill_qty INTEGER,
    fill_price REAL,
    fill_amount REAL,
    currency TEXT,
    status TEXT,
    order_no TEXT,
    raw_json TEXT
);
"""


def _connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_order(settings: Settings, created_at: str, side: str, symbol: str,
               exchange: str, qty: int, price: float, result: dict) -> None:
    with closing(_connect(settings)) as conn, conn:
        conn.execute(
            "INSERT INTO orders (created_at, env, side, symbol, exchange, qty, price,"
            " order_no, ok, msg, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (created_at, settings.kis_env, side, symbol, exchange, qty, price,
             result.get("order_no", ""), int(result.get("ok", False)),
             result.get("msg", ""), json.dumps(result.get("raw", {}), ensure_ascii=False)),
        )


def save_fill(settings: Settings, created_at: str, row: dict) -> None:
    with closing(_connect(settings)) as conn, conn:
        conn.execute(
            "INSERT INTO fills (created_at, ord_date, side, symbol, ord_qty, fill_qty,"
            " fill_price, fill_amount, currency, status, order_no, raw_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (created_at, row.get("ord_date"), row.get("side"), row.get("symbol"),
             row.get("ord_qty"), row.get("fill_qty"), row.get("fill_price"),
             row.get("fill_amount"), row.get("currency"), row.get("status"),
             row.get("order_no"), json.dumps(row.get("raw", {}), ensure_ascii=False)),
        )
