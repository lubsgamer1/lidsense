"""Local web server on the Pi for the touchscreen.

It serves the same dashboard as the cloud and answers the same /api/*.php URLs, from the
local SQLite store instead of MySQL. The screen therefore keeps working with no internet,
and the frontend has a single code path. The control endpoint (baseline, subject, free-air)
exists only here: the cloud copy is read-only.

By default it listens on 127.0.0.1 only, so the controls cannot be reached from the network.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, jsonify, request, send_from_directory

RANGES = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}


def _since(rng: str | None) -> str | None:
    h = RANGES.get(rng or "6h")
    if h is None:
        return None
    t = datetime.now(timezone.utc) - timedelta(hours=h)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def create_app(mon, cfg) -> Flask:
    frontend = os.path.abspath(cfg["paths"].get("frontend_dir")
                               or os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
    app = Flask(__name__, static_folder=None)
    controls = bool(cfg.get("local_ui", {}).get("enable_controls", True))
    dev = cfg["device_id"]

    @app.get("/")
    def index():
        return send_from_directory(frontend, "index.html")

    @app.get("/assets/<path:p>")
    def assets(p):
        return send_from_directory(os.path.join(frontend, "assets"), p)

    @app.get("/api/info.php")
    def info():
        st = mon.status()
        return jsonify({
            "source": "device", "controls": controls, "now": datetime.now(timezone.utc).isoformat(),
            "devices": [{"device_id": dev, "name": cfg.get("device_name", dev), "online": True,
                         "last_seen": st["updated_at"]}],
            "bands": cfg["classification"]["bands"],
            "alert_delta_db": cfg["alerts"]["baseline_delta_db"],
        })

    @app.get("/api/latest.php")
    def latest():
        rows = mon.store.readings(None, 1)
        return jsonify({"device_id": dev, "online": True, "status": mon.status(),
                        "reading": rows[-1] if rows else None})

    @app.get("/api/readings.php")
    def readings():
        rows = mon.store.readings(_since(request.args.get("range")), 5000,
                                  request.args.get("subject") or None)
        return jsonify({"readings": rows})

    @app.get("/api/sweep.php")
    def sweep():
        return jsonify({"sweep": mon.store.latest_sweep()})

    @app.get("/api/alerts.php")
    def alerts():
        return jsonify({"alerts": mon.store.alerts(30)})

    @app.get("/api/export.php")
    def export():
        rows = mon.store.readings(_since(request.args.get("range", "all")), 1_000_000,
                                  request.args.get("subject") or None)
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={dev}-readings.csv"})

    @app.post("/api/control.php")
    def control():
        if not controls:
            return jsonify({"ok": False, "error": "controls disabled"}), 403
        body = request.get_json(silent=True) or {}
        res = mon.command(str(body.get("action", "")), body.get("value"))
        return jsonify(res), (200 if res.get("ok") else 400)

    return app
