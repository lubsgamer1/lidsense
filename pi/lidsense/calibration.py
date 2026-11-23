"""One-port Short-Open-Load (SOL) calibration.

The maths matches the original ghg.py (SOL_compute_coefficients / SOL_compute_reflection),
so existing calibration_S/O/L.npy files still work. A small JSON sidecar now records the
sweep grid the files were taken on, because a calibration is only valid on that exact grid.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import numpy as np


@dataclass
class Calibration:
    short: np.ndarray
    open: np.ndarray
    load: np.ndarray
    start_hz: float
    stop_hz: float
    points: int
    created: str = "unknown"

    @property
    def cal_id(self) -> str:
        return f"sol-{self.created}"

    def apply(self, raw_s11: np.ndarray) -> np.ndarray:
        S, O, L = self.short, self.open, self.load
        Z = (2.0 * L - O - S) / (O - S)
        X = L - S * (1.0 - Z)
        Y = L
        return (Y - raw_s11) / (raw_s11 * Z - X)

    def matches(self, start_hz: float, stop_hz: float, points: int) -> bool:
        return (points == self.points and abs(start_hz - self.start_hz) < 1
                and abs(stop_hz - self.stop_hz) < 1)


def _s11_column(arr: np.ndarray) -> np.ndarray:
    """Old files store SPar(S11, S21) tuples -> shape (N, 2). New files store S11 only."""
    arr = np.asarray(arr)
    return arr[:, 0] if arr.ndim == 2 else arr


def load(directory: str, default_grid: tuple[float, float, int]) -> Calibration | None:
    paths = [os.path.join(directory, f"calibration_{k}.npy") for k in "SOL"]
    if not all(os.path.exists(p) for p in paths):
        return None
    S, O, L = (_s11_column(np.load(p, allow_pickle=False)) for p in paths)
    meta_path = os.path.join(directory, "calibration_meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        grid = (meta["start_hz"], meta["stop_hz"], meta["points"])
        created = meta.get("created", "unknown")
    else:
        # Legacy files from ghg.py were taken on its fixed 1.5-3.0 GHz, 101-point grid.
        grid, created = default_grid, "legacy"
    if len(S) != grid[2]:
        raise ValueError(f"calibration has {len(S)} points but metadata says {grid[2]}")
    return Calibration(S, O, L, grid[0], grid[1], grid[2], created)


def save(directory: str, S, O, L, start_hz: float, stop_hz: float, points: int) -> Calibration:
    os.makedirs(directory, exist_ok=True)
    for k, arr in zip("SOL", (S, O, L)):
        np.save(os.path.join(directory, f"calibration_{k}.npy"), np.asarray(arr, complex))
    created = time.strftime("%Y%m%d-%H%M%S")
    with open(os.path.join(directory, "calibration_meta.json"), "w") as f:
        json.dump({"start_hz": start_hz, "stop_hz": stop_hz, "points": points,
                   "created": created}, f, indent=2)
    return Calibration(np.asarray(S), np.asarray(O), np.asarray(L), start_hz, stop_hz, points, created)
