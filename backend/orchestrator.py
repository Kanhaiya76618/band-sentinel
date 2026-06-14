"""
Aegis — orchestrator.

Drives the incident lifecycle by posting every step through the bus. The
reject-then-fix loop is the heart of it: the remediator's first fix is chaos-
replayed and REJECTED, it revises, the second fix PASSES, the commander gates on
a human, executes, and files the postmortem.

On LocalBus this prints a transcript. On BandBus the identical calls happen
inside a Band room — that's the "Band is the real coordination layer" proof.
"""
from __future__ import annotations

import time

from .agents.roster import (
    Commander, Diagnostician, Observer, Remediator, Validator,
)
from .bus import AgentBus, make_bus
from .contracts import (
    Hypothesis, Intent, Remediation, RoomMessage, Signal, ValidationResult,
)
from .llm import make_llm
from .mockservice import Scenario

# Modeled wall-time each step would take in a real incident (seconds). The agent
# code runs in microseconds; these give an honest, demo-able MTTR and cost.
MODELED_SECONDS = {
    Intent.SIGNAL: 5.0,
    Intent.HYPOTHESIS: 9.0,
    Intent.REMEDIATION: 11.0,
    Intent.VALIDATION: 14.0,        # chaos replay is the slow part
    Intent.APPROVAL_REQUEST: 25.0,  # waiting on a human
    Intent.DECISION: 60.0,          # executing rollback + failover
}


async def run_incident(bus: AgentBus | None = None) -> tuple[list[RoomMessage], dict]:
    bus = bus or make_bus()
    s = Scenario()

    observer = Observer("@observer", make_llm("aiml"))
    diagnostician = Diagnostician("@diagnostician", make_llm("featherless"))
    remediator = Remediator("@remediator", make_llm("aiml"))
    validator = Validator("@validator", make_llm("featherless"))
    commander = Commander("@commander", make_llm("aiml"))

    t0 = time.perf_counter()
    timeline: list[str] = []

    def log(m: RoomMessage) -> None:
        timeline.append(f"{m.sender}: {m.text}")

    # 1) Observer opens the incident
    sig_msg, real = await _post(bus, observer.open_incident(s), log)
    if not real:
        return await bus.history(), {}
    sig = Signal(**sig_msg.payload)

    # 2) Diagnostician forms a root-cause hypothesis
    hyp_msg = await _post(bus, diagnostician.diagnose(s, sig), log)
    hyp = Hypothesis(**hyp_msg.payload)

    # 3) Reject-then-fix loop (max 2 attempts in the spine)
    approved_rem: Remediation | None = None
    approved_vr: ValidationResult | None = None
    for attempt in (1, 2):
        rem_msg = await _post(bus, remediator.propose(attempt), log)
        rem = Remediation(**rem_msg.payload)

        val_msg = await _post(bus, validator.replay(s, rem), log)
        vr = ValidationResult(**val_msg.payload)

        if vr.passed:
            approved_rem, approved_vr = rem, vr
            break

    if not approved_rem:
        return await bus.history(), {"resolved": False}

    # 4) Human-approval gate for the irreversible action
    if not approved_rem.reversible:
        await _post(bus, commander.request_approval(approved_rem), log)
        approver = "human:oncall"      # auto-approved in the offline demo
    else:
        approver = "auto:policy"

    # 5) Execute + resolve. MTTR is modeled from the steps so far; decision
    #    latency is the real agent wall-clock (the speed flex).
    modeled_mttr = sum(MODELED_SECONDS.get(m.intent, 0.0) for m in await bus.history())
    latency_ms = (time.perf_counter() - t0) * 1000.0
    dec_msg = await _post(
        bus, commander.execute(s, approved_rem, approved_vr, approver, modeled_mttr, latency_ms), log
    )
    from .contracts import Decision
    dec = Decision(**dec_msg.payload)

    # 6) Auto-postmortem
    await _post(bus, commander.write_postmortem(s, hyp, dec, timeline.copy()), log)

    verdict = {
        "resolved": True,
        "action": dec.action,
        "approved_by": dec.approved_by,
        "mttr_seconds": dec.mttr_seconds,
        "decision_latency_ms": dec.decision_latency_ms,
        "downtime_cost_usd": dec.downtime_cost_usd,
        "remediation_cost_usd": dec.remediation_cost_usd,
        "averted_cost_usd": dec.averted_cost_usd,
        "attempts": 2,
    }
    return await bus.history(), verdict


async def _post(bus: AgentBus, produced, log):
    """Post a produced message (or (message, flag) tuple) and log it."""
    if isinstance(produced, tuple):
        msg, flag = produced
        await bus.post(msg)
        log(msg)
        return msg, flag
    await bus.post(produced)
    log(produced)
    return produced
