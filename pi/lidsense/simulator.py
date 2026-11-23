"""Simulated NanoVNA for testing the whole pipeline without hardware.

It produces a calibrated S11 sweep with a resonance near 2.24 GHz (thesis Table 6.1).
The depth drifts slowly from well hydrated (about -26 dB) to dehydrated (about -12 dB) and
back, over a cycle of `period_s` seconds, so every status and alert can be exercised. The
sensor is occasionally lifted off the skin (free-air response, 2.20 GHz at -9.3 dB).
"""
from __future__ import annotations

import math
import time

import numpy as np


class SimulatedVNA:
    simulated = True

    def __init__(self, period_s: float = 900.0, seed: int = 1):
        self.rng = np.random.default_rng(seed)
        self.period_s = period_s
        self.t0 = time.time()
        self.start_hz = self.stop_hz = 0.0
        self.points = 0
        self.firmware = ("sim", 0)

    def open(self):
        return self

    def close(self):
        pass

    def set_sweep(self, start_hz, stop_hz, points, avg=1):
        self.start_hz, self.stop_hz, self.points = start_hz, stop_hz, points

    def frequencies(self):
        return np.linspace(self.start_hz, self.stop_hz, self.points)

    def _state(self):
        t = time.time() - self.t0
        phase = (t % self.period_s) / self.period_s
        off_skin = 0.80 < phase < 0.84                 # sensor lifted for a moment
        depth_db = -19.0 - 7.0 * math.cos(2 * math.pi * phase)   # -26 .. -12 dB
        f0 = 2.24e9 + (depth_db + 19.0) * 1.2e6         # small coupled frequency shift
        return off_skin, depth_db, f0

    def read_s11_calibrated(self) -> np.ndarray:
        off_skin, depth_db, f0 = self._state()
        if off_skin:
            depth_db, f0, hw = -9.3, 2.20e9, 70e6
        else:
            hw = 45e6
        f = self.frequencies()
        gmin = 10 ** ((depth_db + self.rng.normal(0, 0.25)) / 20)
        lor = 1.0 / (1.0 + ((f - f0) / hw) ** 2)
        mag = 1.0 - (1.0 - gmin) * lor
        mag *= 1 + self.rng.normal(0, 0.004, len(f))
        phase = np.arctan((f - f0) / hw)
        return mag * np.exp(1j * phase)
