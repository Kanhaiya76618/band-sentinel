"""
Aegis — the mock production service + chaos simulator.

No real cloud needed. This module owns the *ground truth* of the incident and
exposes two real, deterministic computations:

    1. generate_telemetry()      -> a metric timeline the observer detects on
    2. simulate_remediation(...) -> a physics-ish projection of what a proposed
                                    fix would do, which the validator uses as a
                                    chaos replay to PROVE or REJECT a fix.

The point: the reject-then-fix cascade is *computed*, not hardcoded. A bad fix
(scale the pods) is rejected because the model shows the leak still saturates;
the good fix (rollback + failover) passes because the model shows it doesn't.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Service Level Objectives the incident is breaching.
SLO_P99_MS = 1000.0
SLO_ERROR_RATE = 0.01


@dataclass
class Scenario:
    """Ground truth of the incident."""
    service: str = "checkout-api"
    region: str = "us-east-1"
    healthy_region: str = "us-west-2"
    deploy: str = "v2.3.1"
    load_rps: float = 1200.0
    pods: int = 6
    pod_capacity_rps: float = 200.0     # healthy per-pod capacity
    leak_penalty: float = 0.55          # bad deploy cripples per-pod capacity
    revenue_per_min_usd: float = 950.0  # for downtime cost
    human_baseline_mttr_s: float = 2520.0   # ~42 min: typical SEV1 w/o automation
    # injected fault flags
    bad_deploy_active: bool = True
    normal_p99_ms: float = 220.0
    timeline: list[dict] = field(default_factory=list)
    incident_id: str = "INC-2041"


# --------------------------------------------------------------------------- #
# Telemetry
# --------------------------------------------------------------------------- #
def generate_telemetry(s: Scenario, points: int = 40, deploy_at: int = 24) -> list[dict]:
    """
    Emit a metric timeline: calm baseline, a deploy marker, then a spike once the
    bad deploy starts leaking. Deterministic so the demo is reproducible.
    """
    out: list[dict] = []
    for t in range(points):
        if t < deploy_at:
            p99 = s.normal_p99_ms + (t % 4) * 6      # gentle jitter
            err = 0.002 + (t % 3) * 0.0005
            mem = 0.42 + (t % 5) * 0.01
            deploy = None
        else:
            ramp = min(1.0, (t - deploy_at) / 6.0)   # leak ramps over ~6 ticks
            cur = project_steady_state(s)
            p99 = s.normal_p99_ms + (cur["p99_ms"] - s.normal_p99_ms) * ramp
            err = 0.002 + (cur["error_rate"] - 0.002) * ramp
            mem = 0.42 + (0.97 - 0.42) * ramp
            deploy = s.deploy if t == deploy_at else None
        out.append(
            {"t": t, "p99_ms": round(p99, 1), "error_rate": round(err, 4),
             "mem_util": round(mem, 3), "deploy": deploy}
        )
    s.timeline = out
    return out


# --------------------------------------------------------------------------- #
# The physics-ish projection model (shared by telemetry + chaos replay)
# --------------------------------------------------------------------------- #
def _project(
    pods: int,
    load_rps: float,
    pod_capacity_rps: float,
    leak_penalty: float,
    leak_recurs: bool,
) -> dict:
    """Project steady-state p99 / error_rate for a given configuration."""
    eff_capacity_per_pod = pod_capacity_rps * (1.0 - leak_penalty)
    capacity = max(1.0, pods * eff_capacity_per_pod)
    util = load_rps / capacity

    if util < 1.0:
        p99 = 200.0 / max(0.05, (1.0 - util))        # queueing blow-up near 1.0
        error_rate = max(0.0, (util - 0.9)) * 0.5
    else:
        p99 = 8000.0                                  # saturated
        error_rate = min(0.6, 0.10 + (util - 1.0) * 0.25)

    # A leak that isn't removed keeps growing -> memory saturates over time ->
    # errors recur regardless of how many pods you add. The validator treats
    # this as a steady-state failure even if instantaneous util looks ok.
    if leak_recurs:
        error_rate = max(error_rate, 0.12)
        p99 = max(p99, 1800.0)

    return {"p99_ms": round(p99, 1), "error_rate": round(error_rate, 4), "util": round(util, 3)}


def project_steady_state(s: Scenario) -> dict:
    """Current (un-remediated) projection — drives the telemetry spike."""
    return _project(
        pods=s.pods,
        load_rps=s.load_rps,
        pod_capacity_rps=s.pod_capacity_rps,
        leak_penalty=s.leak_penalty if s.bad_deploy_active else 0.0,
        leak_recurs=s.bad_deploy_active,
    )


# --------------------------------------------------------------------------- #
# Chaos replay — the validator's core
# --------------------------------------------------------------------------- #
# Canonical action ids the remediator may propose.
ACTIONS = {"scale_pods", "restart_pods", "rollback_deploy", "failover_region", "rollback_and_failover"}


def simulate_remediation(s: Scenario, action: str, params: dict | None = None) -> dict:
    """
    Replay the incident under a proposed remediation and return projected
    metrics + a human-readable trace. This is the function the validator calls.
    """
    params = params or {}
    trace: list[str] = []

    pods = s.pods
    load = s.load_rps
    leak = s.leak_penalty if s.bad_deploy_active else 0.0
    leak_recurs = s.bad_deploy_active
    capacity_per_pod = s.pod_capacity_rps

    if action == "scale_pods":
        pods = int(params.get("pods", s.pods * 2))
        trace.append(f"Scaled {s.pods} -> {pods} pods. Per-pod capacity still crippled by the leak ({leak:.0%} penalty).")
        trace.append("Leak is unbounded: memory keeps climbing, GC pauses recur regardless of pod count.")

    elif action == "restart_pods":
        trace.append("Restart frees memory momentarily, but the leaking deploy is still live.")
        trace.append("Projection to t+10m: memory re-saturates, incident recurs.")

    elif action == "rollback_deploy":
        leak = 0.0
        leak_recurs = False
        trace.append(f"Rolled back {s.deploy}. Leak removed, per-pod capacity restored.")
        trace.append("us-east still carries 100% load on freshly-rolled pods during drain.")

    elif action == "failover_region":
        # shift traffic to healthy region running the good version on fresh pods
        load = s.load_rps * 0.30
        leak = 0.0
        leak_recurs = False
        trace.append(f"Failed traffic over to {s.healthy_region} (good version, fresh pods).")
        trace.append("Bad deploy remains latent in us-east — residual risk if traffic returns.")

    elif action == "rollback_and_failover":
        leak = 0.0
        leak_recurs = False
        load = s.load_rps * 0.35
        trace.append(f"Rolled back {s.deploy} AND shed load via {s.healthy_region}.")
        trace.append("Leak removed at source and load relieved during the rollout. No residual.")

    else:
        trace.append(f"Unknown action '{action}'.")
        return {"action": action, "passed": False, "projected_p99_ms": 9999.0,
                "projected_error_rate": 0.99, "trace": trace, "regression": False}

    proj = _project(pods, load, capacity_per_pod, leak, leak_recurs)

    passed = proj["p99_ms"] <= SLO_P99_MS and proj["error_rate"] <= SLO_ERROR_RATE
    regression = action in {"scale_pods", "restart_pods"}  # cost/effort up, no real fix

    trace.append(
        f"Projected p99={proj['p99_ms']}ms (SLO {SLO_P99_MS}ms), "
        f"errors={proj['error_rate']:.2%} (SLO {SLO_ERROR_RATE:.2%}) -> "
        f"{'PASS' if passed else 'REJECT'}."
    )

    return {
        "action": action,
        "passed": passed,
        "projected_p99_ms": proj["p99_ms"],
        "projected_error_rate": proj["error_rate"],
        "trace": trace,
        "regression": regression and not passed,
    }
