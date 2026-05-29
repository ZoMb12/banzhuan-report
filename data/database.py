import json
import os
import sqlite3
from datetime import date, datetime
from typing import Any

import config

DB_PATH = os.path.join(config.STORAGE_DIR, "buff_arbitrage.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _serialize(obj: Any) -> str:
    def _default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        raise TypeError(f"Unserializable type: {type(o)}")
    return json.dumps(obj, ensure_ascii=False, default=_default)


def init_db():
    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            target_date TEXT NOT NULL,
            stable_days INTEGER NOT NULL,
            volatility_threshold REAL NOT NULL,
            lookback_days INTEGER NOT NULL,
            conversion_rate REAL NOT NULL,
            requested_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            raw_count INTEGER DEFAULT 0,
            filtered_count INTEGER DEFAULT 0,
            window_count INTEGER DEFAULT 0,
            steam_count INTEGER DEFAULT 0,
            target_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS run_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            name TEXT NOT NULL,
            buff_price REAL,
            volume INTEGER,
            turnover REAL,
            step_reached INTEGER DEFAULT 1,
            windows TEXT,
            steam_url TEXT,
            steam_price REAL,
            steam_sold_count INTEGER,
            steam_price_history TEXT,
            avg_buff_price REAL,
            avg_steam_usd REAL,
            avg_steam_cny REAL,
            avg_diff REAL,
            is_target INTEGER,
            date_pairs TEXT,
            fail_reason TEXT,
            debug_info TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_run_items_run ON run_items(run_id);
        CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
    """)
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Run lifecycle
# ──────────────────────────────────────────────

def create_run(target_date: date, stable_days: int,
               volatility_threshold: float, lookback_days: int,
               conversion_rate: float, target_count: int) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO runs (started_at, target_date, stable_days, volatility_threshold, "
        "lookback_days, conversion_rate, requested_count, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'running')",
        (datetime.now().isoformat(), target_date.isoformat(), stable_days,
         volatility_threshold, lookback_days, conversion_rate, target_count),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def finish_run(run_id: int, status: str = "completed"):
    conn = _get_conn()
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
        (datetime.now().isoformat(), status, run_id),
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Step data persistence
# ──────────────────────────────────────────────

def save_step1(run_id: int, raw_items: list, filtered_items: list, windows: list):
    """Persist raw + filtered items + window results after Step 1+2."""
    conn = _get_conn()
    conn.execute("DELETE FROM run_items WHERE run_id = ?", (run_id,))

    window_map = {}
    for w in windows:
        window_map.setdefault(w.item_id, []).append({
            "window_start": w.window_start.isoformat(),
            "window_end": w.window_end.isoformat(),
            "buff_avg_price": w.buff_avg_price,
            "volatility": w.volatility,
            "buff_records": [
                {"date": r.date, "price": r.price}
                for r in (w.buff_records or [])
            ],
        })

    filtered_ids = {it.item_id for it in filtered_items}
    rows = []
    for it in raw_items:
        item_windows = window_map.get(it.item_id, [])
        step = 3 if (it.item_id in filtered_ids and item_windows) else (
            2 if it.item_id in filtered_ids else 1
        )
        rows.append((
            run_id, it.item_id, it.name, it.buff_price, it.volume, it.turnover,
            step, _serialize(item_windows) if item_windows else None,
        ))
    conn.executemany(
        "INSERT INTO run_items (run_id, item_id, name, buff_price, volume, turnover, "
        "step_reached, windows) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows,
    )
    conn.execute("UPDATE runs SET raw_count=?, filtered_count=?, window_count=? WHERE id=?",
                 (len(raw_items), len(filtered_items), len(windows), run_id))
    conn.commit()
    conn.close()


def save_step2(run_id: int, item_results: list, steam_data: dict):
    """Update items with Steam market data after Step 3."""
    conn = _get_conn()
    success = 0
    for it in item_results:
        data = steam_data.get(it.item_id)
        if data:
            success += 1
            ph = [{"date": r.date.isoformat(), "price": r.price, "volume": r.volume}
                  for r in data.get("steam_price_history", [])]
            conn.execute(
                "UPDATE run_items SET step_reached=4, steam_url=?, steam_price=?, "
                "steam_sold_count=?, steam_price_history=? "
                "WHERE run_id=? AND item_id=?",
                (data.get("steam_url"), data.get("steam_price"),
                 data.get("steam_sold_count", 0), _serialize(ph),
                 run_id, it.item_id),
            )
        else:
            conn.execute(
                "UPDATE run_items SET fail_reason=CASE WHEN fail_reason IS NULL "
                "THEN 'Steam数据获取失败' ELSE fail_reason END WHERE run_id=? AND item_id=?",
                (run_id, it.item_id),
            )
    conn.execute("UPDATE runs SET steam_count=? WHERE id=?", (success, run_id))
    conn.commit()
    conn.close()


def save_step3(run_id: int, arbitrage_results: dict):
    """Update items with arbitrage comparison results and mark run completed."""
    conn = _get_conn()
    target_count = 0
    for item_id, ar in arbitrage_results.items():
        is_target = 1 if ar.get("is_target") else 0
        if is_target:
            target_count += 1
        conn.execute(
            "UPDATE run_items SET avg_buff_price=?, avg_steam_usd=?, avg_steam_cny=?, "
            "avg_diff=?, is_target=?, date_pairs=?, fail_reason=NULL "
            "WHERE run_id=? AND item_id=?",
            (ar.get("avg_buff_price"), ar.get("avg_steam_usd"), ar.get("avg_steam_cny"),
             ar.get("avg_diff"), is_target, _serialize(ar.get("date_pairs", [])),
             run_id, ar.get("item_id", item_id)),
        )
    conn.execute("UPDATE runs SET target_count=?, status='completed', finished_at=? WHERE id=?",
                 (target_count, datetime.now().isoformat(), run_id))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────

def get_recent_runs(limit: int = 20) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run_items(run_id: int, target_only: bool = False) -> list[dict]:
    conn = _get_conn()
    cond = "run_id=?"
    if target_only:
        cond += " AND is_target=1"
    rows = conn.execute(
        f"SELECT * FROM run_items WHERE {cond} ORDER BY is_target DESC, avg_diff DESC",
        (run_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_run(run_id: int):
    conn = _get_conn()
    conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
    conn.commit()
    conn.close()
