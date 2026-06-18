"""
Aegis — anomaly detection (idea #13, log/metric anomaly detection).

Deliberately dependency-free: a rolling-baseline z-score detector using only the
stdlib `statistics`. Real enough to be honest in an interview ("unsupervised,
rolling-window z-score with k-sigma breach + consecutive-point confirmation"),
light enough to run anywhere.
"""
from __future__ import annotations

import statistics
from typing import Optional

# Metrics where "higher is worse".
WATCHED = ("p99_ms", "error_rate", "mem_util")


def detect(
    timeline: list[dict],
    baseline_window: int = 16,
    z_threshold: float = 3.0,
    confirm: int = 3,
) -> Optional[dict]:
    """
    Walk the timeline; the first metric that breaches z_threshold for `confirm`
    consecutive points opens an incident. Returns the breach summary or None.
    """
    # Dynamically scale down baseline and confirm counts for short timelines
    if len(timeline) < baseline_window + confirm:
        if len(timeline) < 2:
            return None
        baseline_window = max(1, len(timeline) // 2)
        confirm = max(1, len(timeline) - baseline_window)

    base = timeline[:baseline_window]
    breaches: dict[str, int] = {m: 0 for m in WATCHED}
    anomalies: list[str] = []
    fired_at: Optional[int] = None

    stats = {}
    for m in WATCHED:
        vals = [p[m] for p in base]
        mu = statistics.mean(vals)
        sd = statistics.pstdev(vals) or 1e-6
        stats[m] = (mu, sd)

    for p in timeline[baseline_window:]:
        for m in WATCHED:
            mu, sd = stats[m]
            z = (p[m] - mu) / sd
            if z >= z_threshold:
                breaches[m] += 1
                if breaches[m] == confirm and m not in [a.split()[0] for a in anomalies]:
                    anomalies.append(f"{m} z={z:.1f} (={p[m]} vs baseline {mu:.1f})")
                    fired_at = fired_at if fired_at is not None else p["t"]
            else:
                breaches[m] = 0

    if not anomalies:
        return None

    # correlate with the nearest preceding deploy marker
    deploy_marker = None
    for p in timeline:
        if p.get("deploy") and (fired_at is None or p["t"] <= fired_at):
            deploy_marker = p["deploy"]

    last = timeline[-1]
    return {
        "fired_at": fired_at,
        "anomalies": anomalies,
        "deploy_marker": deploy_marker,
        "metrics": {m: last[m] for m in WATCHED},
        "baseline": {m: round(stats[m][0], 2) for m in WATCHED},
    }
