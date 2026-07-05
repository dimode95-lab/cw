"""무한매수 상태(State)와 당일 주문(pending) SQLite 저장소."""
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict

from .config import Settings
from .mubae import State

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mubae_state (
    symbol TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placed_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    intent TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    price REAL NOT NULL,
    qty INTEGER NOT NULL,
    t_inc REAL NOT NULL DEFAULT 0,
    order_no TEXT,
    placed_ok INTEGER NOT NULL DEFAULT 1,
    settled INTEGER NOT NULL DEFAULT 0
);
"""


def _connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.executescript(_SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def load_state(settings: Settings, symbol: str) -> State | None:
    with closing(_connect(settings)) as conn:
        row = conn.execute("SELECT state_json FROM mubae_state WHERE symbol=?",
                           (symbol,)).fetchone()
    return State(**json.loads(row["state_json"])) if row else None


def save_state(settings: Settings, st: State, updated_at: str) -> None:
    with closing(_connect(settings)) as conn, conn:
        conn.execute(
            "INSERT INTO mubae_state (symbol, state_json, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(symbol) DO UPDATE SET state_json=excluded.state_json,"
            " updated_at=excluded.updated_at",
            (st.symbol, json.dumps(asdict(st), ensure_ascii=False), updated_at))


def add_pending(settings: Settings, placed_at: str, symbol: str, order: dict) -> None:
    with closing(_connect(settings)) as conn, conn:
        conn.execute(
            "INSERT INTO pending_orders (placed_at, symbol, intent, side, order_type,"
            " price, qty, t_inc, order_no, placed_ok) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (placed_at, symbol, order["intent"], order["side"], order["order_type"],
             order["price"], order["qty"], order.get("t_inc", 0),
             order.get("order_no", ""), int(order.get("placed_ok", True))))


def get_unsettled(settings: Settings, symbol: str) -> list[dict]:
    with closing(_connect(settings)) as conn:
        rows = conn.execute(
            "SELECT * FROM pending_orders WHERE symbol=? AND settled=0 AND placed_ok=1",
            (symbol,)).fetchall()
    return [dict(r) for r in rows]


def settle_all(settings: Settings, symbol: str) -> None:
    with closing(_connect(settings)) as conn, conn:
        conn.execute("UPDATE pending_orders SET settled=1 WHERE symbol=? AND settled=0",
                     (symbol,))
