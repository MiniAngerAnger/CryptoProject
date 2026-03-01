"""
src/storage/db.py — SQLite 数据库层

职责：
- 建表（行情 / 链上 / 健康 / paper trading）
- 提供统一读写接口
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_connection(db_path: str) -> sqlite3.Connection:
    """建立 SQLite 连接，并开启 WAL 模式（多线程更稳）"""
    abs_path = PROJECT_ROOT / db_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(abs_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tables(conn: sqlite3.Connection):
    """创建核心表"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS price_ticks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            symbol      TEXT    NOT NULL,
            price       REAL    NOT NULL,
            change_24h  REAL,
            volume_24h  REAL,
            source      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS onchain_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            tx_hash     TEXT    NOT NULL UNIQUE,
            from_addr   TEXT,
            to_addr     TEXT,
            amount_eth  REAL    NOT NULL,
            usd_value   REAL,
            block_no    INTEGER,
            source      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_health (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      TEXT    NOT NULL,
            module  TEXT    NOT NULL,
            status  TEXT    NOT NULL,
            message TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            TEXT    NOT NULL,
            symbol        TEXT    NOT NULL,
            side          TEXT    NOT NULL,
            qty           REAL    NOT NULL,
            order_type    TEXT    NOT NULL,
            status        TEXT    NOT NULL,
            signal_source TEXT,
            note          TEXT
        );

        CREATE TABLE IF NOT EXISTS fills (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT    NOT NULL,
            order_id   INTEGER NOT NULL,
            symbol     TEXT    NOT NULL,
            side       TEXT    NOT NULL,
            qty        REAL    NOT NULL,
            fill_price REAL    NOT NULL,
            fee_usd    REAL    NOT NULL DEFAULT 0,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS positions (
            symbol      TEXT PRIMARY KEY,
            qty         REAL    NOT NULL,
            avg_price   REAL    NOT NULL,
            updated_ts  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS equity_curve (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            TEXT    NOT NULL,
            balance_usd   REAL    NOT NULL,
            position_usd  REAL    NOT NULL,
            equity_usd    REAL    NOT NULL,
            note          TEXT
        );

        CREATE TABLE IF NOT EXISTS sentiment_snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ts               TEXT    NOT NULL,
            fear_greed_value INTEGER,
            news_score       REAL,
            regime           TEXT,
            source           TEXT
        );

        CREATE TABLE IF NOT EXISTS news_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT    NOT NULL,
            symbol       TEXT    NOT NULL,
            title        TEXT    NOT NULL,
            source       TEXT,
            url          TEXT    UNIQUE,
            published_at TEXT,
            score        REAL
        );
        """
    )
    _add_column_if_missing(conn, "price_ticks", "change_24h", "REAL")
    _add_column_if_missing(conn, "price_ticks", "volume_24h", "REAL")
    conn.commit()


def _add_column_if_missing(conn, table, column, col_type):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


# ─── price_ticks ─────────────────────────────────────────────────────────────

def insert_price(conn, symbol: str, price: float,
                 change_24h: float = None, volume_24h: float = None, source: str = ""):
    conn.execute(
        "INSERT INTO price_ticks (ts, symbol, price, change_24h, volume_24h, source) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), symbol, price, change_24h, volume_24h, source),
    )
    conn.commit()


def query_prices(conn, symbol: str, limit: int = 120):
    cur = conn.execute(
        "SELECT ts, price FROM price_ticks WHERE symbol=? ORDER BY id DESC LIMIT ?",
        (symbol, limit),
    )
    return cur.fetchall()


def query_prices_for_ohlc(conn, symbol: str, limit: int = 5000):
    cur = conn.execute(
        """
        SELECT ts, price FROM (
            SELECT ts, price FROM price_ticks
            WHERE symbol=?
            ORDER BY id DESC LIMIT ?
        ) ORDER BY ts ASC
        """,
        (symbol, limit),
    )
    return cur.fetchall()


def query_latest_price(conn, symbol: str):
    cur = conn.execute(
        "SELECT price, change_24h, volume_24h, ts FROM price_ticks WHERE symbol=? ORDER BY id DESC LIMIT 1",
        (symbol,),
    )
    return cur.fetchone()


# ─── onchain_events ──────────────────────────────────────────────────────────

def insert_onchain_event(conn, tx_hash: str, from_addr: str, to_addr: str,
                         amount_eth: float, usd_value: float,
                         block_no: int, source: str) -> bool:
    try:
        conn.execute(
            "INSERT INTO onchain_events (ts, tx_hash, from_addr, to_addr, amount_eth, usd_value, block_no, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), tx_hash, from_addr, to_addr, amount_eth, usd_value, block_no, source),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def query_onchain_events(conn, limit: int = 20, min_eth: float = 0):
    cur = conn.execute(
        "SELECT * FROM onchain_events WHERE amount_eth >= ? ORDER BY id DESC LIMIT ?",
        (min_eth, limit),
    )
    return cur.fetchall()


# ─── system_health ───────────────────────────────────────────────────────────

def log_health(conn, module: str, status: str, message: str = ""):
    conn.execute(
        "INSERT INTO system_health (ts, module, status, message) VALUES (?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), module, status, message),
    )
    conn.commit()


def query_latest_health(conn):
    cur = conn.execute(
        """
        SELECT module, status, message, ts FROM system_health
        WHERE id IN (SELECT MAX(id) FROM system_health GROUP BY module)
        """
    )
    return cur.fetchall()


# ─── paper trading ───────────────────────────────────────────────────────────

def create_order(conn, symbol: str, side: str, qty: float,
                 order_type: str = "market", status: str = "filled",
                 signal_source: str = "", note: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO orders (ts, symbol, side, qty, order_type, status, signal_source, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), symbol, side, qty, order_type, status, signal_source, note),
    )
    conn.commit()
    return cur.lastrowid


def create_fill(conn, order_id: int, symbol: str, side: str,
                qty: float, fill_price: float, fee_usd: float = 0.0):
    conn.execute(
        "INSERT INTO fills (ts, order_id, symbol, side, qty, fill_price, fee_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), order_id, symbol, side, qty, fill_price, fee_usd),
    )
    conn.commit()


def upsert_position(conn, symbol: str, qty: float, avg_price: float):
    conn.execute(
        """
        INSERT INTO positions (symbol, qty, avg_price, updated_ts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            qty=excluded.qty,
            avg_price=excluded.avg_price,
            updated_ts=excluded.updated_ts
        """,
        (symbol, qty, avg_price, datetime.utcnow().isoformat()),
    )
    conn.commit()


def query_position(conn, symbol: str):
    cur = conn.execute("SELECT symbol, qty, avg_price, updated_ts FROM positions WHERE symbol=?", (symbol,))
    return cur.fetchone()


def insert_equity(conn, balance_usd: float, position_usd: float, note: str = ""):
    equity = balance_usd + position_usd
    conn.execute(
        "INSERT INTO equity_curve (ts, balance_usd, position_usd, equity_usd, note) VALUES (?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), balance_usd, position_usd, equity, note),
    )
    conn.commit()


def query_latest_equity(conn):
    cur = conn.execute("SELECT * FROM equity_curve ORDER BY id DESC LIMIT 1")
    return cur.fetchone()


# ─── sentiment ───────────────────────────────────────────────────────────────

def insert_sentiment_snapshot(conn, fear_greed_value: int | None,
                              news_score: float | None,
                              regime: str,
                              source: str = ""):
    conn.execute(
        "INSERT INTO sentiment_snapshots (ts, fear_greed_value, news_score, regime, source) VALUES (?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), fear_greed_value, news_score, regime, source),
    )
    conn.commit()


def query_latest_sentiment(conn):
    cur = conn.execute("SELECT * FROM sentiment_snapshots ORDER BY id DESC LIMIT 1")
    return cur.fetchone()


def query_sentiment_snapshots(conn, limit: int = 50):
    cur = conn.execute("SELECT * FROM sentiment_snapshots ORDER BY id DESC LIMIT ?", (limit,))
    return cur.fetchall()


# ─── news_events ──────────────────────────────────────────────────────────────

def insert_news_event(conn, symbol: str, title: str, source: str,
                      url: str, published_at: str, score: float) -> bool:
    """插入一条新闻记录，URL 唯一约束，重复时静默跳过返回 False"""
    try:
        conn.execute(
            "INSERT INTO news_events (ts, symbol, title, source, url, published_at, score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), symbol, title, source, url, published_at, score),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # URL 已存在，跳过


def query_news_events(conn, limit: int = 10, symbol: str | None = None):
    """查询最近新闻，可选按 symbol 过滤"""
    if symbol:
        cur = conn.execute(
            "SELECT * FROM news_events WHERE symbol=? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM news_events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    return cur.fetchall()


def query_recent_news_scores(conn, hours: int = 1) -> list[float]:
    """取最近 N 小时内的新闻评分列表，供 sentiment_feed 聚合用"""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    cur = conn.execute(
        "SELECT score FROM news_events WHERE ts >= ? AND score IS NOT NULL",
        (since,),
    )
    return [float(r["score"]) for r in cur.fetchall()]


# ─── dashboard 辅助查询 ────────────────────────────────────────────────────────

def query_recent_orders(conn, limit: int = 5):
    """查询最近 N 笔订单（含 fill_price，JOIN fills 取成交价）"""
    cur = conn.execute(
        """
        SELECT o.ts, o.symbol, o.side, o.qty, o.signal_source, o.note,
               f.fill_price, f.fee_usd
        FROM orders o
        LEFT JOIN fills f ON f.order_id = o.id
        ORDER BY o.id DESC LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()
