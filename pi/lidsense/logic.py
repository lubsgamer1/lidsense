"""Hydration classification, personal baseline and alert state machine.

Classification uses the S11 thresholds from the thesis (sections 6.5.6 and 6.6.2). They live
in config.yaml, so they can be changed without touching the code:
    S11 <  -22 dB          -> Hyperhydrated
    -22 dB <= S11 < -15 dB -> Euhydrated
    S11 >= -15 dB          -> Hypohydrated

Note: ghg.py used different, overlapping return-loss bands ("Moderately Hydrated" could
never be reached). They have been replaced by the thesis thresholds above.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def classify(s11_db: float, bands: list[dict]) -> str:
    """bands: ordered list of {label, below_s11_db}; the last band has no limit."""
    for b in bands:
        limit = b.get("below_s11_db")
        if limit is None or s11_db < limit:
            return b["label"]
    return bands[-1]["label"]


@dataclass
class Baseline:
    return_loss_db: float
    resonant_freq_hz: float
    sd_db: float
    n: int
    created_at: str
    subject: str = ""


def dehydration_delta(rl_db: float, baseline: Baseline | None, sign: int) -> float | None:
    """Positive number = drier than this person's baseline, in dB.

    sign = -1 means return loss FALLS as the person dehydrates (S11 moves towards 0 dB),
    which matches the thesis thresholds. Set sign = +1 in config if your data shows the
    opposite direction (see README, 'Direction of the effect')."""
    if baseline is None:
        return None
    return (rl_db - baseline.return_loss_db) * sign


@dataclass
class AlertEngine:
    dehydrated_label: str
    hyperhydrated_label: str
    consecutive: int = 3
    baseline_delta_db: float = 3.0
    alert_on_hyper: bool = True
    bad_quality_limit: int = 6
    _streak: dict = field(default_factory=dict)
    active: str | None = None          # "dehydration" | "hyperhydration" | "check_contact" | None

    def _bump(self, key: str, cond: bool) -> int:
        self._streak[key] = self._streak.get(key, 0) + 1 if cond else 0
        return self._streak[key]

    def update(self, status: str | None, delta_db: float | None, quality: str) -> tuple[str | None, str | None]:
        """Feed one reading. Returns (event, message); event is 'raised'/'cleared'/None."""
        good = quality == "good"
        bad_n = self._bump("bad", not good)
        if not good:
            if bad_n >= self.bad_quality_limit and self.active != "check_contact":
                prev, self.active = self.active, "check_contact"
                return "raised", ("Sensor readings are unreliable: check skin contact and keep "
                                  "the wrist still." + (f" (was: {prev})" if prev else ""))
            return None, None

        dry = (status == self.dehydrated_label) or (delta_db is not None and delta_db >= self.baseline_delta_db)
        wet = self.alert_on_hyper and status == self.hyperhydrated_label
        dry_n = self._bump("dry", dry)
        wet_n = self._bump("wet", wet)
        calm = not dry and not wet and (delta_db is None or delta_db < self.baseline_delta_db / 2)
        calm_n = self._bump("calm", calm)

        if dry_n >= self.consecutive and self.active != "dehydration":
            self.active = "dehydration"
            why = f"status {status}" + (f", {delta_db:+.1f} dB drier than baseline" if delta_db is not None else "")
            return "raised", f"Possible dehydration ({why})."
        if wet_n >= self.consecutive and self.active not in ("dehydration", "hyperhydration"):
            self.active = "hyperhydration"
            return "raised", f"Possible over-hydration (status {status})."
        if self.active and calm_n >= self.consecutive:
            old, self.active = self.active, None
            return "cleared", f"{old.replace('_', ' ').capitalize()} alert cleared: readings back in normal range."
        if self.active == "check_contact" and good:
            self.active = None
            return "cleared", "Sensor contact restored."
        return None, None
