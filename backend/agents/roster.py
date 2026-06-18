"""
Aegis — the five agents.

Each agent is a thin role wrapper: it turns real computation (detection, chaos
replay, cost math) into a typed RoomMessage and posts it to the bus. The LLM is
used only for the natural-language line in the room, so swapping providers never
changes behaviour — only phrasing.

Framework / provider split (deliberate, for the criteria + both partner prizes):
    @observer      LangGraph  · AI/ML API
    @diagnostician CrewAI     · Featherless
    @remediator    LangGraph  · AI/ML API
    @validator     CrewAI     · Featherless
    @commander     orchestrator
"""
from __future__ import annotations

from ..contracts import (
    Decision, Hypothesis, Intent, Postmortem, Remediation, RoomMessage,
    Severity, Signal, ValidationResult,
)
from ..detector import detect
from ..llm import LLMClient
from ..mockservice import (
    SLO_ERROR_RATE, SLO_P99_MS, Scenario, generate_telemetry, simulate_remediation,
)


class Agent:
    framework = "—"
    provider = "offline"

    def __init__(self, agent_id: str, llm: LLMClient):
        self.id = agent_id
        self.llm = llm

    def _voice(self, tag: str, fallback: str, **ctx) -> str:
        """Room line via LLM; in offline mode returns the deterministic fallback."""
        return self.llm.complete(
            system=f"You are {self.id}, an SRE incident-response agent. One terse sentence.",
            user=fallback, role=self.id, tag=tag,
        ) or fallback


# --------------------------------------------------------------------------- #
class Observer(Agent):
    framework, provider = "LangGraph", "aiml"

    def open_incident(self, s: Scenario, telemetry: list[dict] | None = None) -> tuple[RoomMessage, bool]:
        # Phase 2: detect on REAL uploaded telemetry when provided; otherwise
        # fall back to the deterministic generated timeline (offline demo).
        timeline = telemetry if telemetry is not None else generate_telemetry(s)
        breach = detect(timeline)
        if not breach:
            return RoomMessage.of(self.id, Intent.SIGNAL, "All green. No incident."), False

        sig = Signal(
            service=s.service, region=s.region, severity=Severity.SEV1,
            metrics=breach["metrics"], baseline=breach["baseline"],
            anomalies=breach["anomalies"], deploy_marker=breach["deploy_marker"],
        )
        text = self._voice(
            "open",
            f"SEV1 on {s.service}/{s.region}. {', '.join(breach['anomalies'])}. "
            f"Anomaly began right after deploy {breach['deploy_marker']}. "
            f"Opening the room — @diagnostician, root cause?",
        )
        return RoomMessage.of(self.id, Intent.SIGNAL, text,
                              mentions=["@diagnostician"], payload_model=sig), True


# --------------------------------------------------------------------------- #
class Diagnostician(Agent):
    framework, provider = "CrewAI", "featherless"

    def diagnose(self, s: Scenario, sig: Signal) -> RoomMessage:
        query = (
            "SELECT deploy, p99_ms, mem_util FROM telemetry "
            f"WHERE service='{s.service}' AND region='{s.region}' "
            "AND t >= now()-15m ORDER BY t"
        )  # idea #08: text-to-SQL telemetry query
        hyp = Hypothesis(
            root_cause=f"Memory leak introduced by deploy {sig.deploy_marker}",
            confidence=0.86,
            evidence=[
                f"mem_util climbing to {sig.metrics['mem_util']} (baseline {sig.baseline['mem_util']})",
                f"p99 {sig.metrics['p99_ms']}ms tracks memory saturation, not raw traffic",
                f"onset aligns to deploy {sig.deploy_marker}",
            ],
            suspected_change=sig.deploy_marker,
            telemetry_query=query,
        )
        text = self._voice(
            "diag",
            f"Root cause: {hyp.root_cause} (conf {hyp.confidence:.0%}). p99 tracks "
            f"memory, not traffic — classic leak. @remediator, propose a fix.",
        )
        return RoomMessage.of(self.id, Intent.HYPOTHESIS, text,
                              mentions=["@remediator"], payload_model=hyp)


# --------------------------------------------------------------------------- #
class Remediator(Agent):
    framework, provider = "LangGraph", "aiml"

    def propose(self, s: Scenario, attempt: int) -> RoomMessage:
        if attempt == 1:
            rem = Remediation(
                action="scale_pods", params={"pods": 12},
                rationale="Latency looks like saturation — add capacity to absorb load.",
                reversible=True, attempt=1,
            )
            text = self._voice(
                "fix1",
                f"First pass: scale {s.pods} -> {s.pods * 2} pods to absorb the load. "
                "@validator, replay it before we touch prod.",
            )
        else:
            rem = Remediation(
                action="rollback_and_failover",
                params={"to_region": s.healthy_region},
                rationale="Leak is in the deploy itself; remove it at source and shed load.",
                reversible=False, attempt=2,
            )
            text = self._voice(
                "fix2",
                f"Revised: roll back {s.deploy} AND fail traffic to {s.healthy_region}. "
                f"Kills the leak at source. @validator, re-run.",
            )
        return RoomMessage.of(self.id, Intent.REMEDIATION, text,
                               mentions=["@validator"], payload_model=rem)


# --------------------------------------------------------------------------- #
class Validator(Agent):
    """The skeptic. Chaos-replays every fix before it ships (ideas #14/#15)."""
    framework, provider = "CrewAI", "featherless"

    def replay(self, s: Scenario, rem: Remediation) -> RoomMessage:
        r = simulate_remediation(s, rem.action, rem.params)
        vr = ValidationResult(
            action=rem.action, passed=r["passed"],
            projected_p99_ms=r["projected_p99_ms"], projected_error_rate=r["projected_error_rate"],
            slo_p99_ms=SLO_P99_MS, slo_error_rate=SLO_ERROR_RATE,
            trace=r["trace"], regression=r["regression"],
        )
        if r["passed"]:
            text = self._voice(
                "pass",
                f"Chaos replay PASSED: p99 {r['projected_p99_ms']}ms, "
                f"errors {r['projected_error_rate']:.2%}, within SLO. "
                "@commander, safe to execute with approval.",
            )
            mentions = ["@commander"]
        else:
            text = self._voice(
                "reject",
                f"REJECTED. Replay shows p99 {r['projected_p99_ms']}ms / "
                f"errors {r['projected_error_rate']:.2%} — still breaching. "
                f"{r['trace'][1]} @remediator, this won't hold.",
            )
            mentions = ["@remediator"]
        return RoomMessage.of(self.id, Intent.VALIDATION, text,
                              mentions=mentions, payload_model=vr)


# --------------------------------------------------------------------------- #
class Commander(Agent):
    """Incident commander: HITL gate, execution, MTTR + cost, postmortem."""
    framework, provider = "orchestrator", "aiml"

    def request_approval(self, rem: Remediation) -> RoomMessage:
        text = self._voice(
            "ask",
            f"Validator cleared `{rem.action}`, but it's irreversible "
            f"(failover). @human approve? [y/N]",
        )
        return RoomMessage.of(self.id, Intent.APPROVAL_REQUEST, text, mentions=["@human"])

    def execute(self, s: Scenario, rem: Remediation, vr: ValidationResult,
                approved_by: str, mttr_s: float, latency_ms: float) -> RoomMessage:
        minutes_down = mttr_s / 60.0
        downtime_cost = round(minutes_down * s.revenue_per_min_usd, 2)
        remediation_cost = 35.0 if "failover" in rem.action else 5.0  # idea #16: cost-aware
        baseline_cost = (s.human_baseline_mttr_s / 60.0) * s.revenue_per_min_usd
        averted = round(max(0.0, baseline_cost - downtime_cost - remediation_cost), 2)
        dec = Decision(
            action=rem.action, approved_by=approved_by, executed=True,
            mttr_seconds=round(mttr_s, 1), decision_latency_ms=round(latency_ms, 1),
            downtime_cost_usd=downtime_cost, remediation_cost_usd=remediation_cost,
            averted_cost_usd=averted,
        )
        text = self._voice(
            "exec",
            f"Approved by {approved_by}. Executing `{rem.action}`. "
            f"Incident RESOLVED in {mttr_s/60:.1f} min (vs ~{s.human_baseline_mttr_s/60:.0f} "
            f"min manual). ~${averted:,.0f} in downtime averted.",
        )
        return RoomMessage.of(self.id, Intent.DECISION, text, payload_model=dec)

    def write_postmortem(self, s: Scenario, hyp: Hypothesis, dec: Decision,
                         timeline: list[str]) -> RoomMessage:
        pm = Postmortem(
            incident_id=s.incident_id,
            title=f"{s.service} {s.region} — leak from {s.deploy}",
            severity=Severity.SEV1,
            timeline=timeline,
            root_cause=hyp.root_cause,
            resolution=f"{dec.action} (approved by {dec.approved_by})",
            mttr_seconds=dec.mttr_seconds,
            cost_summary=f"Downtime ~${dec.downtime_cost_usd:,.0f}; "
                         f"remediation ${dec.remediation_cost_usd:,.0f}.",
            follow_ups=[
                f"Add a memory-leak canary to the deploy gate for {s.service}.",
                "Block deploys that raise mem_util slope > 2x in canary.",
                f"Pre-warm {s.healthy_region} standby to cut failover time.",
            ],
        )
        text = self._voice("pm", f"Postmortem {s.incident_id} drafted and filed.")
        return RoomMessage.of(self.id, Intent.POSTMORTEM, text, payload_model=pm)
