"""Local SQLite store on the Pi.

  * readings / sweeps / alerts: used by the touchscreen dashboard, so it works offline
  * outbox: every message for the cloud is written here first and removed only after the
    server confirms it. Readings are not lost when Wi-Fi drops or the Pi reboots.
  * settings: current subject code, baseline, free-air reference trace
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS readings (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  measured_at TEXT NOT NULL, subject TEXT, status TEXT, quality TEXT,
  resonant_freq_hz REAL, s11_db REAL, return_loss_db REAL, bandwidth_hz REAL, q_factor REAL,
  rl_spread_db REAL, contact_rms_db REAL, baseline_rl_db REAL, delta_db REAL, alert TEXT, cal_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_readings_time ON readings(measured_at);
CREATE TABLE IF NOT EXISTS sweeps (
  seq INTEGER PRIMARY KEY, start_hz REAL, stop_hz REAL, points INTEGER, s11_db TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, event TEXT, level TEXT, message TEXT, subject TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Store:
    def __init__(self, path: str, keep_sweeps: int = 500):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.keep_sweeps = keep_sweeps

    # ------------------------------------------------------------------ settings
    def get(self, key, default=None):
        r = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value)))

    # ------------------------------------------------------------------ writes
    def add_reading(self, row: dict, sweep: dict | None) -> int:
        cols = ",".join(row)
        with self.lock:
            cur = self.db.execute(f"INSERT INTO readings({cols}) VALUES({','.join('?' * len(row))})",
                                  tuple(row.values()))
            seq = cur.lastrowid
            if sweep:
                self.db.execute("INSERT INTO sweeps VALUES(?,?,?,?,?)",
                                (seq, sweep["start_hz"], sweep["stop_hz"], sweep["points"],
                                 json.dumps(sweep["s11_db"])))
                self.db.execute("DELETE FROM sweeps WHERE seq <= ?", (seq - self.keep_sweeps,))
        return seq

    def add_alert(self, event: str, level: str | None, message: str, subject: str) -> dict:
        a = {"created_at": utcnow(), "event": event, "level": level, "message": message, "subject": subject}
        with self.lock:
            a["id"] = self.db.execute(
                "INSERT INTO alerts(created_at,event,level,message,subject) VALUES(?,?,?,?,?)",
                tuple(a.values())).lastrowid
        return a

    # ------------------------------------------------------------------ outbox
    def enqueue(self, kind: str, payload: dict):
        with self.lock:
            self.db.execute("INSERT INTO outbox(kind,payload) VALUES(?,?)", (kind, json.dumps(payload)))

    def pending(self, limit: int = 100):
        return [(r["id"], r["kind"], json.loads(r["payload"]))
                for r in self.db.execute("SELECT * FROM outbox ORDER BY id LIMIT ?", (limit,))]

    def ack(self, ids: list[int]):
        if ids:
            with self.lock:
                self.db.execute(f"DELETE FROM outbox WHERE id IN ({','.join('?' * len(ids))})", ids)

    def outbox_size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    # ------------------------------------------------------------------ reads (local dashboard)
    def readings(self, since: str | None, limit: int = 2000, subject: str | None = None):
        q, args = "SELECT * FROM readings WHERE 1=1", []
        if since:
            q += " AND measured_at >= ?"; args.append(since)
        if subject:
            q += " AND subject = ?"; args.append(subject)
        q += " ORDER BY seq DESC LIMIT ?"; args.append(limit)
        return [dict(r) for r in self.db.execute(q, args)][::-1]

    def latest_sweep(self):
        r = self.db.execute("SELECT * FROM sweeps ORDER BY seq DESC LIMIT 1").fetchone()
        if not r:
            return None
        d = dict(r); d["s11_db"] = json.loads(d["s11_db"])
        return d

    def alerts(self, limit: int = 50):
        return [dict(r) for r in self.db.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))]
