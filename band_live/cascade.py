"""
band_live — the 5 agents as deterministic reactive handlers.

Each handler reacts to the @mention it receives over Band and hands off to the
next agent. NO scripting/orchestrator: the only thing that drives the order is
who each agent @mentions next. All decisions/cost/postmortem reuse the backend
roster (`backend/agents/roster.py`) + chaos replay (`backend/mockservice`), so
nothing is faked and no LLM is required (OfflineLLM gives the deterministic line).

Handoffs (each over a real Band @mention):
  observer       trigger        -> SEV1 signal            -> @diagnostician
  diagnostician  signal         -> root-cause hypothesis  -> @remediator
  remediator     hypothesis     -> fix #1 scale_pods      -> @validator
                 validation_reject -> fix #2 rollback...   -> @validator
  validator      remediation    -> chaos replay:
                                    PASS   -> @commander
                                    REJECT -> @remediator
  commander      validation_pass -> (irreversible fix) RECRUITS @security into the
                                    room via Band participant tools, asks for sign-off
                 security_signoff -> human approval request   -> @human
                 human "approve" -> execute + decision + postmortem
  security       security_review -> deterministic risk check  -> sign-off @commander
                 (NOT a pre-added participant — discovered + added at runtime)
"""
from __future__ import annotations

import logging
import time

from backend.agents.roster import (
    Commander, Diagnostician, Observer, Remediator, Validator,
)
from backend.contracts import (
    Decision, Hypothesis, Intent, Remediation, Signal, ValidationResult,
)
from backend.llm import OfflineLLM
from backend.mockservice import Scenario
from backend.orchestrator import MODELED_SECONDS

from . import protocol as P

log = logging.getLogger("band_live")

# Deterministic, zero-network LLM for the room lines (so it's reliable + no keys).
_LLM = OfflineLLM()
_observer = Observer("@observer", _LLM)
_diagnostician = Diagnostician("@diagnostician", _LLM)
_remediator = Remediator("@remediator", _LLM)
_validator = Validator("@validator", _LLM)
_commander = Commander("@commander", _LLM)

# Words a human can use to approve / reject in the room.
_APPROVE = ("approve", "approved", "yes", "lgtm", "ship it", "go ahead", "👍")
_REJECT = ("reject", "rejected", "no", "deny", "abort", "hold")


def _mention(handle: str) -> str:
    """Resolve a handle to the Band id used for the @mention (human -> BAND_HUMAN_ID)."""
    if handle == "human":
        return P.human_id() or P.agent_id("observer")
    return P.agent_id(handle)


async def _post(tools, text: str, to, intent: str, ctx: dict) -> None:
    """Post a room line + our structured marker, @mentioning the next participant(s).
    ``to`` is a handle or list of handles. Terminal/human-facing messages also
    @mention @observer so they stay fetchable via an agent key for the transcript."""
    handles = [to] if isinstance(to, str) else list(to)
    content = P.encode(text, {"intent": intent, "ctx": ctx})
    await tools.send_message(content, mentions=[_mention(h) for h in handles])


# --------------------------------------------------------------------------- #
# Handlers (one per agent)
# --------------------------------------------------------------------------- #
async def observer_handler(msg, tools, room_id) -> None:
    data = P.decode(msg.content)
    if not data or data.get("intent") != "trigger":
        return
    s = Scenario()
    sig_msg, real = _observer.open_incident(s)        # generate telemetry + detect (real)
    if not real:
        return
    sig = Signal(**sig_msg.payload)
    ctx = {
        "t0": time.time(),                            # real wall-clock start of the cascade
        "steps": [Intent.SIGNAL.value],
        "signal": sig.model_dump(mode="json"),
    }
    await _post(tools, sig_msg.text, "diagnostician", "signal", ctx)
    log.info("@observer      SEV1 signal posted → @diagnostician")


async def diagnostician_handler(msg, tools, room_id) -> None:
    data = P.decode(msg.content)
    if not data or data.get("intent") != "signal":
        return
    ctx = data["ctx"]
    sig = Signal(**ctx["signal"])
    hyp_msg = _diagnostician.diagnose(Scenario(), sig)
    hyp = Hypothesis(**hyp_msg.payload)
    ctx["hypothesis"] = hyp.model_dump(mode="json")
    ctx["steps"].append(Intent.HYPOTHESIS.value)
    await _post(tools, hyp_msg.text, "remediator", "hypothesis", ctx)
    log.info("@diagnostician root-cause hypothesis → @remediator")


async def remediator_handler(msg, tools, room_id) -> None:
    data = P.decode(msg.content)
    if not data or data.get("intent") not in ("hypothesis", "validation_reject"):
        return
    ctx = data["ctx"]
    # Stateless: a hypothesis kicks off attempt 1; a REJECT triggers the revision.
    attempt = 1 if data["intent"] == "hypothesis" else 2
    rem_msg = _remediator.propose(Scenario(), attempt)
    rem = Remediation(**rem_msg.payload)
    ctx["remediation"] = rem.model_dump(mode="json")
    ctx["steps"].append(Intent.REMEDIATION.value)
    await _post(tools, rem_msg.text, "validator", "remediation", ctx)
    log.info("@remediator    proposed `%s` (attempt %d) → @validator", rem.action, attempt)


async def validator_handler(msg, tools, room_id) -> None:
    data = P.decode(msg.content)
    if not data or data.get("intent") != "remediation":
        return
    ctx = data["ctx"]
    rem = Remediation(**ctx["remediation"])
    val_msg = _validator.replay(Scenario(), rem)      # reuses simulate_remediation (chaos replay)
    vr = ValidationResult(**val_msg.payload)
    ctx["validation"] = vr.model_dump(mode="json")
    ctx["steps"].append(Intent.VALIDATION.value)
    if vr.passed:
        await _post(tools, val_msg.text, "commander", "validation_pass", ctx)
        log.info("@validator     PASS `%s` (p99 %.0fms) → @commander", vr.action, vr.projected_p99_ms)
    else:
        await _post(tools, val_msg.text, "remediator", "validation_reject", ctx)
        log.info("@validator     REJECT `%s` (p99 %.0fms) → @remediator", vr.action, vr.projected_p99_ms)


# commander state per room: the held context + which gate we're waiting on.
_pending: dict[str, dict] = {}
_phase: dict[str, str] = {}        # room_id -> "security" | "human"


def _peer_field(p, name: str):
    return p.get(name) if isinstance(p, dict) else getattr(p, name, None)


def _is_security(p) -> bool:
    sid = P.agent_id("security")
    return (_peer_field(p, "id") == sid
            or (_peer_field(p, "handle") or "").lstrip("@").lower() == "security"
            or (_peer_field(p, "name") or "").lower() == "security")


async def _recruit_security(tools, ctx: dict, rem) -> None:
    """Discover + add the security specialist to THIS room, then @mention it for a
    sign-off. Pure Band participant tools — a fixed pipeline can't pull in a new
    agent mid-incident."""
    sec_id = P.agent_id("security")
    # (a) discover addable peers (the SDK filters to peers NOT already in the room)
    resp = await tools.lookup_peers()
    peers = getattr(resp, "data", None) or []
    discovered = next((p for p in peers if _is_security(p)), None)
    # (b) add it to the room (idempotent — SDK returns already_in_room if present)
    added = await tools.add_participant(sec_id, role="member")
    await tools.get_participants()    # refresh the cache so the @mention resolves
    log.info("@commander     RECRUITED @security via Band — discovered=%s, add=%s",
             bool(discovered), (added or {}).get("status"))

    vr = ValidationResult(**ctx["validation"])
    text = (f"This fix is irreversible (region failover), so I'm pulling in a specialist. "
            f"@security — recruited you to this room for a risk sign-off: proposed action "
            f"`{rem.action}`, validator projects p99 {vr.projected_p99_ms:.0f}ms / errors "
            f"{vr.projected_error_rate:.2%} (within SLO). Clear to proceed?")
    await _post(tools, text, "security", "security_review", ctx)


async def _ask_human(tools, ctx: dict, security: dict | None) -> None:
    rem = Remediation(**ctx["remediation"])
    text = _commander.request_approval(rem).text
    if security:
        text += (f" (@security signed off: {security['risk']} risk — {security['reason']})"
                 if security.get("signed_off") else
                 f" (⚠ @security flagged {security['risk']} risk: {security['reason']})")
    if Intent.APPROVAL_REQUEST.value not in ctx["steps"]:
        ctx["steps"].append(Intent.APPROVAL_REQUEST.value)
    await _post(tools, text, ["human", "observer"], "approval_request", ctx)
    log.info("@commander     approval request → @human%s (awaiting a human 'approve')",
             " citing @security sign-off" if security else "")


async def commander_handler(msg, tools, room_id) -> None:
    data = P.decode(msg.content)

    # 1) Validator cleared a fix. If it's irreversible, RECRUIT @security first;
    #    a reversible fix goes straight to the human gate (unchanged behaviour).
    if data and data.get("intent") == "validation_pass":
        ctx = data["ctx"]
        rem = Remediation(**ctx["remediation"])
        _pending[room_id] = ctx
        if not rem.reversible:
            _phase[room_id] = "security"
            await _recruit_security(tools, ctx, rem)
        else:
            _phase[room_id] = "human"
            await _ask_human(tools, ctx, security=None)
        return

    # 2) Security signed off (or flagged) → now ask the human, citing it.
    if data and data.get("intent") == "security_signoff":
        ctx = _pending.get(room_id, data["ctx"])
        verdict = data["ctx"].get("security") or {}
        ctx["security"] = verdict
        _pending[room_id] = ctx
        _phase[room_id] = "human"
        await _ask_human(tools, ctx, security=verdict)
        return

    # 3) A human's free-text reply (no marker), only once we're at the human gate.
    if data is None and _phase.get(room_id) == "human":
        text = (msg.content or "").lower()
        if any(w in text for w in _APPROVE):
            _phase.pop(room_id, None)
            await _execute(tools, room_id, _pending.pop(room_id),
                           approver=f"human:{msg.sender_name or 'oncall'}")
        elif any(w in text for w in _REJECT):
            _phase.pop(room_id, None)
            _pending.pop(room_id, None)
            await _post(tools, "Human rejected the action — escalating to on-call, nothing executed.",
                        ["human", "observer"], "halted", {"steps": []})
            log.info("@commander     human REJECTED → halted (escalated, no action)")


# --------------------------------------------------------------------------- #
# Security specialist — the recruited 6th agent (deterministic risk sign-off).
# --------------------------------------------------------------------------- #
def _risk_check(rem, vr) -> dict:
    """Deterministic residual-risk assessment of a validated fix. Low risk only
    when the fix removes the root cause AND the replay is within SLO."""
    action = rem.action
    removes_root = "rollback" in action            # rollback removes the leaking deploy at source
    sheds_load = "failover" in action              # failover shifts load to a healthy region
    if removes_root and vr.passed:
        reason = (f"`{action}` removes the leaking deploy at source"
                  + (" and shifts load to a healthy region" if sheds_load else "")
                  + f"; validator-projected p99 {vr.projected_p99_ms:.0f}ms within SLO, no residual.")
        return {"signed_off": True, "risk": "low", "reason": reason}
    return {"signed_off": False, "risk": "elevated",
            "reason": f"`{action}` does not remove the root cause / leaves residual risk — "
                      "recommend a rollback at source before proceeding."}


async def security_handler(msg, tools, room_id) -> None:
    data = P.decode(msg.content)
    if not data or data.get("intent") != "security_review":
        return
    ctx = data["ctx"]
    rem = Remediation(**ctx["remediation"])
    vr = ValidationResult(**ctx["validation"])
    verdict = _risk_check(rem, vr)
    ctx["security"] = verdict
    text = (f"Risk sign-off — {verdict['risk'].upper()} residual risk. {verdict['reason']} "
            + ("Signed off, safe to proceed. @commander."
               if verdict["signed_off"] else "Recommend holding. @commander."))
    await _post(tools, text, "commander", "security_signoff", ctx)
    log.info("@security      %s risk → %s, → @commander",
             verdict["risk"], "SIGNED OFF" if verdict["signed_off"] else "HOLD")


async def _execute(tools, room_id: str, ctx: dict, approver: str) -> None:
    s = Scenario()
    rem = Remediation(**ctx["remediation"])
    vr = ValidationResult(**ctx["validation"])
    hyp = Hypothesis(**ctx["hypothesis"])
    # MTTR is modeled from the steps so far (real wall-clock latency tracked separately).
    mttr_s = sum(MODELED_SECONDS.get(Intent(st), 0.0) for st in ctx["steps"])
    latency_ms = (time.time() - ctx["t0"]) * 1000.0       # REAL through-Band round-trip time
    dec_msg = _commander.execute(s, rem, vr, approver, mttr_s, latency_ms)
    dec = Decision(**dec_msg.payload)
    ctx["steps"].append(Intent.DECISION.value)
    await _post(tools, dec_msg.text, ["human", "observer"], "decision", ctx)

    sig = Signal(**ctx["signal"])
    timeline = [
        f"observer: SEV1 {sig.service}/{sig.region}",
        f"diagnostician: {hyp.root_cause}",
        f"remediator: {rem.action}",
        f"validator: PASS p99 {vr.projected_p99_ms:.0f}ms within SLO",
        f"commander: {approver} approved, executed {dec.action}",
    ]
    pm_msg = _commander.write_postmortem(s, hyp, dec, timeline)
    await _post(tools, pm_msg.text, ["human", "observer"], "postmortem", ctx)
    log.info("@commander     %s → EXECUTED %s, postmortem filed (MTTR %.0fs, ~$%s averted)",
             approver, dec.action, mttr_s, f"{dec.averted_cost_usd:,.0f}")


# Map each agent handle to its handler — used by the runner.
HANDLERS = {
    "observer": observer_handler,
    "diagnostician": diagnostician_handler,
    "remediator": remediator_handler,
    "validator": validator_handler,
    "commander": commander_handler,
    "security": security_handler,
}
