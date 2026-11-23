"""SOL calibration wizard and quick check (replaces calibration_process / demo_read_points).

    python -m lidsense.calibrate --config /etc/lidsense/config.yaml           # new SOL calibration
    python -m lidsense.calibrate --config /etc/lidsense/config.yaml --check   # one test reading

Stop the service first (sudo systemctl stop lidsense): only one program can use the NanoVNA.
"""
from __future__ import annotations

import argparse

import numpy as np
import yaml

from . import calibration, features
from .logic import classify
from .nanovna_v2 import NanoVNAV2


def _avg_sweep(vna, n=5):
    return np.mean([vna.read_s11_raw() for _ in range(n)], axis=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/etc/lidsense/config.yaml")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    sw = cfg["sweep"]
    grid = (float(sw["start_hz"]), float(sw["stop_hz"]), int(sw["points"]))
    caldir = cfg["paths"]["calibration_dir"]

    with NanoVNAV2(cfg["serial_port"]) as vna:
        vna.set_sweep(*grid, int(sw.get("avg", 1)))
        print(f"NanoVNA V2 firmware {vna.firmware[0]}.{vna.firmware[1]}; sweep "
              f"{grid[0]/1e9:.3f}-{grid[1]/1e9:.3f} GHz, {grid[2]} points")
        if args.check:
            cal = calibration.load(caldir, grid)
            if not cal or not cal.matches(*grid):
                raise SystemExit("No calibration for this sweep grid - run without --check first.")
            db = features.s11_to_db(cal.apply(vna.read_s11_raw()))
            f = features.extract(np.linspace(*grid), db, tuple(float(x) for x in cfg["search_band_hz"]), cfg["smooth_window"])
            print(f"Resonance {f.resonant_freq_hz/1e9:.4f} GHz, S11 {f.s11_db:.2f} dB, "
                  f"RL {f.return_loss_db:.2f} dB, BW {f.bandwidth_hz}, edge={f.at_band_edge}")
            print("Status:", classify(f.s11_db, cfg["classification"]["bands"]))
            return

        meas = {}
        for name in ("SHORT", "OPEN", "LOAD"):
            input(f"Connect the {name} standard to the end of the antenna cable, then press Enter...")
            meas[name] = _avg_sweep(vna)
            print("  captured")
        cal = calibration.save(caldir, meas["SHORT"], meas["OPEN"], meas["LOAD"], *grid)
        input("Verification: leave the LOAD connected (or fit a second 50 ohm load) and press Enter...")
        rl = -features.s11_to_db(cal.apply(vna.read_s11_raw()))
        print(f"LOAD return loss after calibration: min {rl.min():.1f} dB, median {np.median(rl):.1f} dB")
        print("Good calibration" if rl.min() > 30 else
              "WARNING: below 30 dB - check connectors and repeat (thesis achieved better than 40 dB).")
        print(f"Saved to {caldir} as {cal.cal_id}. Restart the service: sudo systemctl start lidsense")


if __name__ == "__main__":
    main()
