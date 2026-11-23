"""Turn a calibrated S11 sweep into hydration features.

Improvements over ghg.py:
  * the resonance is searched only inside the sensor band (default 2.0-2.5 GHz), so a
    spurious dip elsewhere in 1.5-3.0 GHz cannot be picked
  * 5-point moving-average smoothing (thesis section 6.5.6) before picking the dip
  * parabolic interpolation gives sub-step resolution of the resonant frequency and depth
    (the raw 101-point grid has 15 MHz steps)
  * -3 dB bandwidth and loaded Q are reported as secondary features
  * several sweeps are combined per reading, and their spread is used as a motion check
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class SweepFeatures:
    resonant_freq_hz: float
    s11_db: float              # depth of the dip (negative number)
    return_loss_db: float      # = -s11_db (positive number, as stored by ghg.py)
    bandwidth_hz: float | None
    q_factor: float | None
    at_band_edge: bool

    def to_dict(self):
        return asdict(self)


def s11_to_db(s11: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(s11), 1e-9))


def smooth(y: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return y.copy()
    pad = window // 2
    yp = np.pad(y, pad, mode="edge")
    return np.convolve(yp, np.ones(window) / window, mode="valid")


def extract(freqs: np.ndarray, s11_db: np.ndarray, band: tuple[float, float],
            smooth_window: int = 5) -> SweepFeatures:
    raw = np.asarray(s11_db, float)
    ys = smooth(raw, smooth_window)
    idx = np.where((freqs >= band[0]) & (freqs <= band[1]))[0]
    if len(idx) < 3:
        raise ValueError("search band contains fewer than 3 sweep points")
    # Locate the dip on the smoothed trace (robust to noise spikes), then measure it on the
    # unsmoothed trace: a moving average on a coarse grid would make a deep, narrow dip look
    # several dB shallower than it is.
    i = int(idx[np.argmin(ys[idx])])
    near = idx[(idx >= i - 2) & (idx <= i + 2)]
    i = int(near[np.argmin(raw[near])])
    y = raw
    edge = i in (idx[0], idx[-1])

    f0, d0 = float(freqs[i]), float(y[i])
    if not edge:
        y1, y2, y3 = y[i - 1], y[i], y[i + 1]
        denom = y1 - 2 * y2 + y3
        if denom > 0:
            off = 0.5 * (y1 - y3) / denom              # in units of one step, |off| <= 0.5
            step = freqs[i + 1] - freqs[i]
            f0 = float(freqs[i] + off * step)
            d0 = float(y2 - 0.25 * (y1 - y3) * off)

    # -3 dB bandwidth around the dip (linear interpolation of the crossings)
    level = d0 + 3.0
    bw = None
    lo = i
    while lo > 0 and y[lo] < level:
        lo -= 1
    hi = i
    while hi < len(y) - 1 and y[hi] < level:
        hi += 1
    if y[lo] >= level and y[hi] >= level and lo < i < hi:
        def cross(a, b):
            return freqs[a] + (level - y[a]) * (freqs[b] - freqs[a]) / (y[b] - y[a])
        bw = float(cross(hi - 1, hi) - cross(lo + 1, lo))
        if bw <= 0:
            bw = None
    q = f0 / bw if bw else None
    return SweepFeatures(f0, d0, -d0, bw, q, edge)


def combine(features: list[SweepFeatures]) -> tuple[SweepFeatures, float]:
    """Median of several sweeps -> one reading; also return the return-loss spread (dB)."""
    rl = np.array([f.return_loss_db for f in features])
    fr = np.array([f.resonant_freq_hz for f in features])
    bws = [f.bandwidth_hz for f in features if f.bandwidth_hz]
    bw = float(np.median(bws)) if bws else None
    f0 = float(np.median(fr))
    med = SweepFeatures(
        resonant_freq_hz=f0,
        s11_db=-float(np.median(rl)),
        return_loss_db=float(np.median(rl)),
        bandwidth_hz=bw,
        q_factor=(f0 / bw) if bw else None,
        at_band_edge=any(f.at_band_edge for f in features),
    )
    return med, float(rl.max() - rl.min())


def contact_distance_db(s11_db: np.ndarray, free_air_db: np.ndarray | None) -> float | None:
    """RMS difference (dB) between this sweep and the stored free-air sweep.
    A small value means the sensor is effectively in air (no skin contact)."""
    if free_air_db is None or len(free_air_db) != len(s11_db):
        return None
    return float(np.sqrt(np.mean((np.asarray(s11_db) - np.asarray(free_air_db)) ** 2)))
