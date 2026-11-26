"""Local persistence with Python's built-in sqlite3."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations(
    series_key TEXT NOT NULL, obs_date TEXT NOT NULL, value REAL,
    PRIMARY KEY(series_key, obs_date));
CREATE TABLE IF NOT EXISTS series_meta(
    series_key TEXT PRIMARY KEY, title TEXT, units TEXT, frequency TEXT, source TEXT,
    source_url TEXT, last_obs TEXT, last_success TEXT, last_attempt TEXT, last_error TEXT, extra TEXT);
CREATE TABLE IF NOT EXISTS alerts(
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, category TEXT, indicator TEXT,
    current_value REAL, previous_value REAL, condition TEXT, severity TEXT, obs_date TEXT, source_url TEXT,
    UNIQUE(indicator, condition, severity, obs_date));
CREATE TABLE IF NOT EXISTS analyses(
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, model TEXT, content TEXT, evidence TEXT);
CREATE TABLE IF NOT EXISTS reports(
    url TEXT PRIMARY KEY, title TEXT, report_date TEXT, fetched_at TEXT, text TEXT);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def connect(path: str | Path = "riskradar.db") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_series(conn, key: str, series: pd.Series, *, title="", units="", frequency="", source="",
                source_url="", extra: dict | None = None) -> None:
    s = series.dropna()
    ts = now_iso()
    conn.executemany(
        "INSERT OR REPLACE INTO observations(series_key, obs_date, value) VALUES (?,?,?)",
        [(key, pd.Timestamp(d).strftime("%Y-%m-%d"), float(v)) for d, v in s.items()],
    )
    last_obs = pd.Timestamp(s.index[-1]).strftime("%Y-%m-%d") if len(s) else None
    conn.execute(
        """INSERT INTO series_meta(series_key,title,units,frequency,source,source_url,last_obs,
               last_success,last_attempt,last_error,extra)
           VALUES (?,?,?,?,?,?,?,?,?,NULL,?)
           ON CONFLICT(series_key) DO UPDATE SET title=excluded.title, units=excluded.units,
               frequency=excluded.frequency, source=excluded.source, source_url=excluded.source_url,
               last_obs=excluded.last_obs, last_success=excluded.last_success,
               last_attempt=excluded.last_attempt, last_error=NULL, extra=excluded.extra""",
        (key, title, units, frequency, source, source_url, last_obs, ts, ts, json.dumps(extra or {})),
    )
    conn.commit()


def record_failure(conn, key: str, error: str, *, source="", source_url="") -> None:
    ts = now_iso()
    conn.execute(
        """INSERT INTO series_meta(series_key, source, source_url, last_attempt, last_error)
           VALUES (?,?,?,?,?)
           ON CONFLICT(series_key) DO UPDATE SET last_attempt=excluded.last_attempt,
               last_error=excluded.last_error""",
        (key, source, source_url, ts, error[:500]),
    )
    conn.commit()


def load_series(conn, key: str) -> pd.Series:
    rows = conn.execute(
        "SELECT obs_date, value FROM observations WHERE series_key=? ORDER BY obs_date", (key,)
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float, name=key)
    return pd.Series([r["value"] for r in rows], index=pd.to_datetime([r["obs_date"] for r in rows]), name=key)


def get_meta(conn, key: str) -> dict | None:
    row = conn.execute("SELECT * FROM series_meta WHERE series_key=?", (key,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["extra"] = json.loads(d["extra"]) if d.get("extra") else {}
    return d


def all_meta(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM series_meta ORDER BY series_key")]


def insert_alerts(conn, alerts: list[dict]) -> int:
    n = 0
    for a in alerts:
        cur = conn.execute(
            """INSERT OR IGNORE INTO alerts(created_at,category,indicator,current_value,previous_value,
                   condition,severity,obs_date,source_url)
               VALUES (:created_at,:category,:indicator,:current_value,:previous_value,
                       :condition,:severity,:obs_date,:source_url)""", a)
        n += cur.rowcount
    conn.commit()
    return n


def recent_alerts(conn, limit: int = 200) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]


def save_analysis(conn, model: str, content: str, evidence: str) -> None:
    conn.execute("INSERT INTO analyses(created_at,model,content,evidence) VALUES (?,?,?,?)",
                 (now_iso(), model, content, evidence))
    conn.commit()


def last_analysis(conn) -> dict | None:
    row = conn.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def save_report(conn, url: str, title: str, report_date: str, text: str) -> None:
    conn.execute("INSERT OR REPLACE INTO reports(url,title,report_date,fetched_at,text) VALUES (?,?,?,?,?)",
                 (url, title, report_date, now_iso(), text))
    conn.commit()


def list_reports(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM reports ORDER BY report_date DESC")]
