"""Background uploader: drains the SQLite outbox to the PHP/MySQL server over HTTPS.

The Pi never talks to MySQL directly. That keeps database passwords off the device and works
on shared hosting (e.g. Hostinger), where remote MySQL access is normally blocked. Each device
has its own API key, and the server only accepts messages that carry it.
"""
from __future__ import annotations

import logging
import threading
import time

import requests

log = logging.getLogger("lidsense.uploader")


class Uploader(threading.Thread):
    def __init__(self, store, url: str, device_id: str, api_key: str,
                 status_fn, period_s: float = 5.0, batch: int = 100):
        super().__init__(daemon=True, name="uploader")
        self.store, self.url, self.device_id, self.api_key = store, url, device_id, api_key
        self.status_fn, self.period_s, self.batch = status_fn, period_s, batch
        self.session = requests.Session()
        self.last_ok: float | None = None
        self.last_error: str | None = None
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        backoff = self.period_s
        while not self._stop.is_set():
            try:
                sent = self.flush_once()
                backoff = self.period_s
                if sent >= self.batch:          # more waiting: keep draining
                    continue
            except Exception as e:              # network down, server error, ...
                self.last_error = str(e)
                log.warning("upload failed: %s (outbox=%d)", e, self.store.outbox_size())
                backoff = min(backoff * 2, 300)
            self._stop.wait(backoff)

    def flush_once(self) -> int:
        items = self.store.pending(self.batch)
        body = {
            "device_id": self.device_id,
            "status": self.status_fn(),
            "messages": [{"id": i, "kind": k, "data": p} for i, k, p in items],
        }
        r = self.session.post(self.url, json=body, timeout=15,
                              headers={"X-Device-Key": self.api_key})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        accepted = r.json().get("accepted", [])
        self.store.ack(accepted)
        self.last_ok, self.last_error = time.time(), None
        return len(items)
