import sqlite3
from pathlib import Path

DB_PATH = Path("data/trading.db")


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS price_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        name TEXT,
        price REAL,
        diff REAL,
        rate REAL,
        volume INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        name TEXT,
        action TEXT NOT NULL,
        reason TEXT,
        price REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        name TEXT,
        side TEXT NOT NULL,
        qty INTEGER NOT NULL,
        price REAL NOT NULL,
        order_type TEXT NOT NULL,
        status TEXT NOT NULL,
        broker_order_no TEXT,
        raw_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def save_log(level: str, message: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (level, message) VALUES (?, ?)",
        (level, message)
    )
    conn.commit()
    conn.close()


def save_price_snapshot(symbol: str, name: str, price: float, diff: float, rate: float, volume: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO price_snapshots (symbol, name, price, diff, rate, volume)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (symbol, name, price, diff, rate, volume))
    conn.commit()
    conn.close()


def save_signal(symbol: str, name: str, action: str, reason: str, price: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO signals (symbol, name, action, reason, price)
    VALUES (?, ?, ?, ?, ?)
    """, (symbol, name, action, reason, price))
    conn.commit()
    conn.close()


def save_order(symbol: str, name: str, side: str, qty: int, price: float,
               order_type: str, status: str, broker_order_no: str = None, raw_json: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO orders (
        symbol, name, side, qty, price, order_type, status, broker_order_no, raw_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, name, side, qty, price, order_type, status, broker_order_no, raw_json))
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    return order_id


def update_order_status(order_id: int, status: str, raw_json: str = None, broker_order_no: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    UPDATE orders
    SET status = ?,
        raw_json = COALESCE(?, raw_json),
        broker_order_no = COALESCE(?, broker_order_no),
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (status, raw_json, broker_order_no, order_id))
    conn.commit()
    conn.close()


def count_open_like_buy_orders_today(symbol: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT COUNT(*) AS cnt
    FROM orders
    WHERE symbol = ?
      AND side = 'BUY'
      AND date(created_at, 'localtime') = date('now', 'localtime')
      AND status IN ('DRY_RUN', 'SUBMITTED', 'PENDING', 'PARTIAL')
    """, (symbol,))
    row = cur.fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0