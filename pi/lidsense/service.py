"""LidSense hydration monitor: main service for the Raspberry Pi.

Replaces ghg.py + start.sh + auto_run.sh. One systemd service that:
  1. sweeps the NanoVNA V2 continuously (no ngrok, no HTTP POST needed to trigger it)
  2. calibrates, extracts features, checks contact and motion, classifies, applies the
     personal baseline and runs the alert logic
  3. stores everything locally (SQLite) and uploads to the cloud (PHP + MySQL)
  4. serves the dashboard locally for the 5" touchscreen (http://localhost:8080)

Run:  python -m lidsense.service --config /etc/lidsense/config.yaml
      python -m lidsense.service --config config.yaml --simulate     (no hardware)
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import yaml

from . import calibration, features
from .logic import AlertEngine, Baseline, classify, dehydration_delta
from .store import Store, utcnow

log = logging.getLogger("lidsense")


class Monitor:
    def __init__(self, cfg: dict, simulate: bool = False):
        self.cfg = cfg
        self.simulate = simulate or cfg.get("simulate", False)
        os.makedirs(cfg["paths"]["data_dir"], exist_ok=True)
        self.store = Store(os.path.join(cfg["paths"]["data_dir"], "lidsense.sqlite"))
        sw = cfg["sweep"]
        self.grid = (float(sw["start_hz"]), float(sw["stop_hz"]), int(sw["points"]))
        self.cal = None if self.simulate else calibration.load(cfg["paths"]["calibration_dir"], self.grid)
        if self.cal and not self.cal.matches(*self.grid):
            raise SystemExit(f"Calibration grid {self.cal.start_hz/1e9:.3f}-{self.cal.stop_hz/1e9:.3f} GHz/"
                             f"{self.cal.points} pts does not match config sweep. Re-run calibrate.py.")
        c = cfg["classification"]
        a = cfg["alerts"]
        self.alerts = AlertEngine(c["dehydrated_label"], c["hyperhydrated_label"],
                                  a["consecutive"], a["baseline_delta_db"], a["alert_on_hyper"],
                                  a["bad_quality_limit"])
        self.vna = None
        self.wake = threading.Event()
        self.stop_ev = threading.Event()
        self.pending_baseline: list | None = None
        self.pending_free_air = False
        self.state = {"state": "starting", "message": "Starting up", "last_reading_at": None}
        # restore an active alert after a restart, so it is not raised twice
        self.alerts.active = self.store.get("alert_active")
        self.alert_message = self.store.get("alert_message")
        self.uploader = None

    # ------------------------------------------------------------------ helpers
    @property
    def subject(self) -> str:
        return self.store.get("subject", "") or ""

    def baseline(self) -> Baseline | None:
        b = self.store.get(f"baseline:{self.subject}")
        return Baseline(**b) if b else None

    def status(self) -> dict:
        b = self.baseline()
        return {
            **self.state,
            "subject": self.subject,
            "baseline": b.__dict__ if b else None,
            "baseline_capture": None if self.pending_baseline is None else
                {"have": len(self.pending_baseline), "need": self.cfg["baseline"]["n_readings"]},
            "free_air_recorded": self.store.get("free_air") is not None,
            "active_alert": self.alerts.active,
            "active_alert_message": self.alert_message,
            "outbox": self.store.outbox_size(),
            "calibration": "simulated" if self.simulate else (self.cal.cal_id if self.cal else "NONE"),
            "simulated": self.simulate,
            "upload_error": self.uploader.last_error if self.uploader else None,
            "interval_s": self.cfg["interval_s"],
            "updated_at": utcnow(),
        }

    def _set_state(self, state, message):
        self.state.update(state=state, message=message)

    # ------------------------------------------------------------------ VNA
    def _open_vna(self):
        if self.simulate:
            from .simulator import SimulatedVNA
            self.vna = SimulatedVNA(period_s=self.cfg.get("simulator_period_s", 900)).open()
        else:
            from .nanovna_v2 import NanoVNAV2
            self.vna = NanoVNAV2(self.cfg["serial_port"]).open()
            log.info("NanoVNA V2 firmware %s.%s", *self.vna.firmware)
        self.vna.set_sweep(*self.grid, int(self.cfg["sweep"].get("avg", 1)))

    def _sweep_db(self) -> np.ndarray:
        if self.simulate:
            s11 = self.vna.read_s11_calibrated()
        else:
            raw = self.vna.read_s11_raw()
            if self.cal is None:
                raise RuntimeError("No calibration found. Run calibrate.py first.")
            s11 = self.cal.apply(raw)
        return features.s11_to_db(s11)

    # ------------------------------------------------------------------ one reading
    def measure_once(self):
        freqs = np.linspace(*self.grid)
        band = tuple(float(x) for x in self.cfg["search_band_hz"])
        traces, feats = [], []
        for _ in range(int(self.cfg["sweeps_per_reading"])):
            db = self._sweep_db()
            traces.append(db)
            feats.append(features.extract(freqs, db, band, int(self.cfg["smooth_window"])))
        mean_trace = np.mean(traces, axis=0)

        if self.pending_free_air:
            self.store.set("free_air", [round(float(x), 3) for x in mean_trace])
            self.pending_free_air = False
            self._info("Free-air reference recorded.")
            self._set_state("idle", "Free-air reference recorded. Place the sensor on the wrist.")
            return

        reading, spread = features.combine(feats)
        q = self.cfg["quality"]
        free_air = self.store.get("free_air")
        contact = features.contact_distance_db(mean_trace, np.array(free_air) if free_air else None)
        if contact is not None and contact < q["min_contact_rms_db"]:
            quality = "no_contact"
        elif spread > q["max_spread_db"]:
            quality = "unstable"
        elif reading.at_band_edge:
            quality = "out_of_band"
        else:
            quality = "good"

        if quality == "no_contact":
            # Sensor resting in air is normal between measurements: show it, don't store it.
            self._set_state("no_contact", "Sensor is not on the skin.")
            if not q.get("store_no_contact", False):
                return

        status = classify(reading.s11_db, self.cfg["classification"]["bands"]) if quality == "good" else None
        base = self.baseline()
        delta = dehydration_delta(reading.return_loss_db, base, int(self.cfg["baseline"]["dehydration_sign"]))
        event, msg = self.alerts.update(status, delta, quality)

        # baseline capture uses good readings only
        if self.pending_baseline is not None and quality == "good":
            self.pending_baseline.append(reading)
            if len(self.pending_baseline) >= int(self.cfg["baseline"]["n_readings"]):
                self._finish_baseline()

        row = {
            "measured_at": utcnow(), "subject": self.subject, "status": status, "quality": quality,
            "resonant_freq_hz": round(reading.resonant_freq_hz, 1),
            "s11_db": round(reading.s11_db, 3), "return_loss_db": round(reading.return_loss_db, 3),
            "bandwidth_hz": round(reading.bandwidth_hz, 1) if reading.bandwidth_hz else None,
            "q_factor": round(reading.q_factor, 2) if reading.q_factor else None,
            "rl_spread_db": round(spread, 3),
            "contact_rms_db": round(contact, 3) if contact is not None else None,
            "baseline_rl_db": round(base.return_loss_db, 3) if base else None,
            "delta_db": round(delta, 3) if delta is not None else None,
            "alert": self.alerts.active,
            "cal_id": "simulated" if self.simulate else self.cal.cal_id,
        }
        sweep = {"start_hz": self.grid[0], "stop_hz": self.grid[1], "points": self.grid[2],
                 "s11_db": [round(float(x), 2) for x in mean_trace]}
        seq = self.store.add_reading(row, sweep)
        msg_out = {**row, "seq": seq}
        every = int(self.cfg["cloud"].get("upload_sweep_every", 6))
        if every > 0 and seq % every == 0:
            msg_out["sweep"] = sweep
        self.store.enqueue("reading", msg_out)
        self._handle_alert(event, msg)

        self.state["last_reading_at"] = row["measured_at"]
        if quality == "good":
            self._set_state("measuring", f"{status}: S11 {reading.s11_db:.1f} dB at "
                                         f"{reading.resonant_freq_hz/1e9:.4f} GHz")
        elif quality != "no_contact":
            self._set_state("unstable", {"unstable": "Movement detected - keep the wrist still.",
                                         "out_of_band": "Resonance outside the search band - check sensor."}[quality])

    def _handle_alert(self, event, msg):
        if not event:
            return
        level = self.alerts.active if event == "raised" else None
        self.alert_message = msg if event == "raised" else None
        self.store.set("alert_active", self.alerts.active)
        self.store.set("alert_message", self.alert_message)
        a = self.store.add_alert(event, level, msg, self.subject)
        self.store.enqueue("alert", a)
        log.warning("ALERT %s: %s", event, msg)

    def _info(self, msg: str):
        self.store.enqueue("alert", self.store.add_alert("info", None, msg, self.subject))

    def _finish_baseline(self):
        rl = np.array([r.return_loss_db for r in self.pending_baseline])
        fr = np.array([r.resonant_freq_hz for r in self.pending_baseline])
        b = Baseline(round(float(rl.mean()), 3), round(float(fr.mean()), 1),
                     round(float(rl.std(ddof=1)) if len(rl) > 1 else 0.0, 3), len(rl), utcnow(), self.subject)
        self.store.set(f"baseline:{self.subject}", b.__dict__)
        self.pending_baseline = None
        self.store.enqueue("baseline", b.__dict__)
        self._info(f"Baseline saved for '{self.subject or 'default'}': return loss "
                   f"{b.return_loss_db:.1f} dB (±{b.sd_db:.2f}, n={b.n}).")

    # ------------------------------------------------------------------ commands (from local UI)
    def command(self, action: str, value: str | None = None) -> dict:
        if action == "baseline":
            self.pending_baseline = []
        elif action == "clear_baseline":
            self.store.set(f"baseline:{self.subject}", None)
        elif action == "free_air":
            self.pending_free_air = True
        elif action == "subject":
            v = (value or "").strip()[:32]
            if v and not all(ch.isalnum() or ch in "-_" for ch in v):
                return {"ok": False, "error": "Subject code: letters, digits, - and _ only"}
            self.store.set("subject", v)
            self.alerts = AlertEngine(**{k: getattr(self.alerts, k) for k in (
                "dehydrated_label", "hyperhydrated_label", "consecutive", "baseline_delta_db",
                "alert_on_hyper", "bad_quality_limit")})
            self.alert_message = None
            self.store.set("alert_active", None)
            self.store.set("alert_message", None)
        elif action != "measure":
            return {"ok": False, "error": "unknown action"}
        self.wake.set()
        return {"ok": True}

    # ------------------------------------------------------------------ loop
    def loop(self):
        while not self.stop_ev.is_set():
            t0 = time.time()
            try:
                if self.vna is None:
                    self._open_vna()
                self.measure_once()
            except Exception as e:
                log.exception("measurement failed")
                self._set_state("vna_error", f"NanoVNA error: {e}")
                if self.vna:
                    self.vna.close()
                self.vna = None
                self.stop_ev.wait(5)
            wait = max(0.5, float(self.cfg["interval_s"]) - (time.time() - t0))
            if self.pending_baseline is not None or self.pending_free_air:
                wait = min(wait, 2.0)
            self.wake.wait(wait)
            self.wake.clear()


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/etc/lidsense/config.yaml")
    ap.add_argument("--simulate", action="store_true", help="use the built-in NanoVNA simulator")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    mon = Monitor(cfg, args.simulate)

    cloud = cfg.get("cloud", {})
    if cloud.get("enabled"):
        key = os.environ.get(cloud.get("api_key_env", "LIDSENSE_API_KEY"), "")
        if not key:
            log.error("cloud upload enabled but %s is not set; readings are kept locally",
                      cloud.get("api_key_env"))
        else:
            from .uploader import Uploader
            mon.uploader = Uploader(mon.store, cloud["ingest_url"], cfg["device_id"], key, mon.status,
                                    float(cloud.get("period_s", 5)))
            mon.uploader.start()

    ui = cfg.get("local_ui", {})
    if ui.get("enabled", True):
        from .local_server import create_app
        app = create_app(mon, cfg)
        threading.Thread(target=lambda: app.run(host=ui.get("host", "127.0.0.1"),
                                                port=int(ui.get("port", 8080)), threaded=True,
                                                use_reloader=False),
                         daemon=True, name="local-ui").start()
    try:
        mon.loop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
