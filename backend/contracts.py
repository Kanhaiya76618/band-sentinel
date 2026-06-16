"""
Aegis — shared message contracts.

Every agent speaks this one schema inside the Band room. Keeping the wire
format typed and validated is what lets five agents on different frameworks
coordinate without misreading each other.

`RoomMessage` is the envelope that travels over the bus (Local now, Band at
kickoff). The typed payload models (Signal, Hypothesis, Remediation,
ValidationResult, Decision, Postmortem) are dumped into `RoomMessage.payload`
so the transport only ever carries plain JSON.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class Intent(str, Enum):
    # ── Incident-resolution workflow ──────────────────────────────────────
    SIGNAL = "signal"                       # observer declares an incident
    HYPOTHESIS = "hypothesis"               # diagnostician's root-cause guess
    REMEDIATION = "remediation_proposal"    # remediator proposes a fix
    VALIDATION = "validation_result"        # validator's chaos-replay verdict
    APPROVAL_REQUEST = "approval_request"   # commander asks a human
    DECISION = "decision"                   # commander executes / resolves
    POSTMORTEM = "postmortem"               # auto-written incident report

    # ── Job-application workflow (Phase 3) — same room, second domain ─────
    SEARCH_PROFILE = "search_profile"       # observer parses criteria/resume
    JOB_MATCHES = "job_matches"             # validator's ranked real postings
    TAILOR_RESULT = "tailor_result"         # tailor's rewritten resume
    APPLICATION = "application"             # applier's submitted/queued package


class Severity(str, Enum):
    SEV1 = "SEV1"   # full / partial outage, customer-facing
    SEV2 = "SEV2"   # degraded, SLO at risk
    SEV3 = "SEV3"   # minor


# --------------------------------------------------------------------------- #
# Typed payloads
# --------------------------------------------------------------------------- #
class Signal(BaseModel):
    """What the observer saw that opened the incident."""
    service: str
    region: str
    severity: Severity
    metrics: dict[str, float]           # current values, e.g. {"p99_ms": 4200}
    baseline: dict[str, float]          # rolling baseline for the same metrics
    anomalies: list[str]                # human-readable z-score breaches
    deploy_marker: Optional[str] = None # suspicious deploy seen near the breach


class Hypothesis(BaseModel):
    """The diagnostician's root-cause theory, with evidence."""
    root_cause: str
    confidence: float                   # 0..1
    evidence: list[str]
    suspected_change: Optional[str] = None
    telemetry_query: Optional[str] = None  # the text-to-SQL/PromQL it ran


class Remediation(BaseModel):
    """A concrete, machine-executable fix proposal."""
    action: str                         # canonical action id (see mockservice)
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    reversible: bool                    # drives the human-approval gate
    attempt: int = 1


class ValidationResult(BaseModel):
    """The validator's chaos-replay verdict on a proposed remediation."""
    action: str
    passed: bool
    projected_p99_ms: float
    projected_error_rate: float
    slo_p99_ms: float
    slo_error_rate: float
    trace: list[str]                    # why it passed / failed
    regression: bool = False            # did it make something else worse?


class Decision(BaseModel):
    """The commander's executed outcome."""
    action: str
    approved_by: str                    # "human:oncall" or "auto:policy"
    executed: bool
    mttr_seconds: float                 # modeled detection->resolution
    decision_latency_ms: float          # real agent wall-clock (the speed flex)
    downtime_cost_usd: float
    remediation_cost_usd: float
    averted_cost_usd: float             # vs the human-on-call baseline


class Postmortem(BaseModel):
    incident_id: str
    title: str
    severity: Severity
    timeline: list[str]
    root_cause: str
    resolution: str
    mttr_seconds: float
    cost_summary: str
    follow_ups: list[str]


# --------------------------------------------------------------------------- #
# The envelope that travels over the bus
# --------------------------------------------------------------------------- #
class RoomMessage(BaseModel):
    seq: int = 0
    sender: str                         # "@observer", "@validator", ...
    mentions: list[str] = Field(default_factory=list)
    intent: Intent
    text: str                           # the natural-language line in the room
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)

    # convenience: build a message from a typed payload model
    @classmethod
    def of(
        cls,
        sender: str,
        intent: Intent,
        text: str,
        mentions: Optional[list[str]] = None,
        payload_model: Optional[BaseModel] = None,
    ) -> "RoomMessage":
        return cls(
            sender=sender,
            intent=intent,
            text=text,
            mentions=mentions or [],
            payload=payload_model.model_dump(mode="json") if payload_model else {},
        )
