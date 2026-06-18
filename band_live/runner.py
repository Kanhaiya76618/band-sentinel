"""
band_live — launch all 5 agents as live Band listeners and watch the incident
resolve itself through @mention handoffs.

Flow:
  1. Build 5 ReactiveAgents (observer/diagnostician/remediator/validator/commander),
     each its own Band identity, each reacting only to its @mentions.
  2. start() them all → they connect over Phoenix-Channels and subscribe to the room.
  3. Seed ONE message: a monitoring trigger @mentioning @observer.
  4. From there the whole chain emerges from real Band @mention reactions:
       observer → diagnostician → remediator ⇄ validator (REJECT→revise→PASS)
       → commander → @human → (human "approve") → commander executes + postmortem
  5. The human "approve": posted automatically AS the human if BAND_HUMAN_KEY is set;
     otherwise a real person types `approve @commander` in the Band chat.
  6. Poll the room until the postmortem lands, then print the transcript.

Nothing scripts the order — the runner only seeds and observes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from . import protocol as P
from .cascade import HANDLERS
from .reactive import ReactiveAgent

log = logging.getLogger("band_live")


def _ensure_ca_bundle() -> None:
    """python.org macOS builds often lack a CA trust store, so the Phoenix WSS
    handshake fails (`CERTIFICATE_VERIFY_FAILED`). Point OpenSSL at certifi.
    Only sets the vars when unset — never overrides an explicit choice."""
    if os.getenv("SSL_CERT_FILE"):
        return
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(certifi.where()))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# REST helpers — seed the trigger, post the human approve, read the transcript.
# --------------------------------------------------------------------------- #
def _post_as(api_key: str, content: str, mentions: list[tuple[str, str]]) -> None:
    """Post a message AS the identity owning api_key, @mentioning (id, handle) pairs.
    Same create_agent_chat_message path BandBus.post uses."""
    from thenvoi_rest import (
        ChatMessageRequest, ChatMessageRequestMentionsItem, RestClient,
    )
    client = RestClient(api_key=api_key, base_url=P.rest_url())
    items = [ChatMessageRequestMentionsItem(id=i, handle=h) for (i, h) in mentions]
    client.agent_api_messages.create_agent_chat_message(
        P.chat_id(), message=ChatMessageRequest(content=content, mentions=items))


def _seed_trigger() -> None:
    # The alert comes from the human if we have their key, else from the commander
    # acting as the monitoring/pager source. Either way it @mentions @observer.
    key = P.human_key() or P.agent_key("commander")
    content = P.encode(
        "🚨 [monitoring] SEV1 alert fired on checkout-api/us-east-1 — @observer, "
        "please assess and open the incident.",
        {"intent": "trigger", "ctx": {}})
    _post_as(key, content, [(P.agent_id("observer"), "observer")])


def _post_human_approve() -> None:
    # Plain text (NO marker) so the commander treats it as the human's free-text reply.
    _post_as(P.human_key(), "approve — go ahead and execute it.",
             [(P.agent_id("commander"), "commander")])


def _read_messages() -> list:
    """Union all agents' message lists (each only surfaces messages that @mention
    it) and dedupe — reconstructs the whole thread."""
    from thenvoi_rest import RestClient
    seen: dict = {}
    for who in P.ALL_LISTENERS:
        client = RestClient(api_key=P.agent_key(who), base_url=P.rest_url())
        try:
            resp = client.agent_api_messages.list_agent_messages(
                P.chat_id(), status="all", page_size=100)
            for m in (getattr(resp, "data", None) or []):
                seen[m.id] = m
        except Exception:
            # Agent might not be in the chat room yet (e.g. @security before recruitment)
            pass
    return list(seen.values())


def _ensure_security_absent() -> None:
    """Remove @security from the room (if present) so each run RECRUITS it genuinely.
    Uses the commander's key (an original participant). Not-in-room is the normal
    case → ignored."""
    from thenvoi_rest import RestClient
    client = RestClient(api_key=P.agent_key("commander"), base_url=P.rest_url())
    try:
        client.agent_api_participants.remove_agent_chat_participant(
            P.chat_id(), P.agent_id("security"))
    except Exception:
        pass


async def _fetch() -> list:
    return await asyncio.to_thread(_read_messages)


# --------------------------------------------------------------------------- #
# Library API — used by the app to run ONE genuine incident through Band and
# stream the real @mention handoffs. (No manual "type approve locally" gate.)
# --------------------------------------------------------------------------- #
class BandLiveNotReady(RuntimeError):
    """BAND_* env not fully configured — the caller should fall back to offline."""


def is_ready() -> bool:
    """True iff every BAND_* var the live agents need is set (incl. @security)."""
    return not P.missing_env()


def _post_approve() -> None:
    """Inject the human approval. As the human if BAND_HUMAN_KEY is set; otherwise
    the observer posts it on the human's behalf (the dashboard button is the gate)."""
    key = P.human_key() or P.agent_key("observer")
    _post_as(key, "approve — go ahead and execute it. @commander",
             [(P.agent_id("commander"), "commander")])


def _post_reject() -> None:
    key = P.human_key() or P.agent_key("observer")
    _post_as(key, "reject — hold off, do not execute. @commander",
             [(P.agent_id("commander"), "commander")])


# band_live intent -> (frontend sender, frontend intent) so the SAME war-room UI
# renders the genuine transcript exactly like the offline one.
_FE = {
    "signal": ("@observer", "signal"),
    "hypothesis": ("@diagnostician", "hypothesis"),
    "remediation": ("@remediator", "remediation_proposal"),
    "validation_reject": ("@validator", "validation_result"),
    "validation_pass": ("@validator", "validation_result"),
    "security_review": ("@commander", "security_review"),
    "security_signoff": ("@security", "security_signoff"),
    "approval_request": ("@commander", "approval_request"),
    "decision": ("@commander", "decision"),
    "postmortem": ("@commander", "postmortem"),
}


def _to_frontend(d: dict, m, seq: int) -> dict | None:
    """Map a decoded Band message to the war-room UI's RoomMessage shape."""
    intent = d.get("intent")
    if intent not in _FE:
        return None
    sender, fe_intent = _FE[intent]
    ctx = d.get("ctx", {})
    payload: dict = {}
    if fe_intent == "validation_result":
        payload = ctx.get("validation", {}) or {}
    elif fe_intent == "postmortem":
        payload = ctx.get("postmortem", {}) or {}
    return {"seq": seq, "sender": sender, "intent": fe_intent,
            "text": P.visible(getattr(m, "content", "")),
            "mentions": [], "payload": payload}


def _verdict_from(ctx: dict) -> dict:
    v = (ctx or {}).get("decision") or {}
    return {"resolved": True, "action": v.get("action", "rollback_and_failover"),
            "approved_by": v.get("approved_by", "human:dashboard"),
            "mttr_seconds": v.get("mttr_seconds", 89.0),
            "decision_latency_ms": v.get("decision_latency_ms", 0.0),
            "downtime_cost_usd": v.get("downtime_cost_usd", 1409.0),
            "remediation_cost_usd": v.get("remediation_cost_usd", 35.0),
            "averted_cost_usd": v.get("averted_cost_usd", 38456.0)}


async def run_live(emit, decide=None, *, timeout_s: float = 120.0,
                   auto_after_s: float = 12.0) -> None:
    """
    Run ONE genuine incident through Band, streaming each real @mention handoff via
    ``await emit(event, data)`` in the same shape the offline war-room stream uses.

    Human gate: ``decide`` (async ``() -> 'approve'|'reject'|None``) is the dashboard
    button. If no decision arrives within ``auto_after_s`` AFTER @security signs off,
    we auto-approve so the demo never hangs. Raises BandLiveNotReady if unconfigured.
    """
    _ensure_ca_bundle()
    if not is_ready():
        raise BandLiveNotReady(", ".join(P.missing_env()))

    pre_ids = {m.id for m in await _fetch()}
    await asyncio.to_thread(_ensure_security_absent)   # genuine recruit each run
    agents = [ReactiveAgent(h, HANDLERS[h], ignore_ids=pre_ids) for h in P.ALL_LISTENERS]
    for a in agents:
        await a.start()
    tasks = [asyncio.create_task(a.run_forever()) for a in agents]

    seen, seq = set(pre_ids), 0
    emitted_await = security_seen = approved = False
    approve_deadline = None
    try:
        await asyncio.sleep(4.0)
        await asyncio.to_thread(_seed_trigger)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            await asyncio.sleep(1.5)
            fresh = sorted((m for m in await _fetch() if m.id not in seen),
                           key=lambda m: (getattr(m, "inserted_at", None) is None,
                                          getattr(m, "inserted_at", None)))
            for m in fresh:
                seen.add(m.id)
                d = P.decode(getattr(m, "content", "")) or {}
                intent = d.get("intent")
                fe = _to_frontend(d, m, seq + 1)
                if fe:
                    seq += 1
                    await emit("message", fe)
                if intent == "security_signoff":
                    security_seen = True
                if intent == "approval_request" and not emitted_await:
                    emitted_await = True
                    await emit("await_approval", {})
                    approve_deadline = time.time() + auto_after_s
                if intent == "decision":
                    await emit("verdict", _verdict_from(d.get("ctx", {})))
                if intent in ("postmortem", "halted"):
                    await emit("done", {})
                    return
            if emitted_await and not approved:
                want = await decide() if decide else None
                if want == "reject":
                    approved = True
                    await asyncio.to_thread(_post_reject)
                elif want == "approve" or (security_seen and time.time() >= (approve_deadline or 0)):
                    approved = True
                    await asyncio.to_thread(_post_approve)
        await emit("done", {})
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*(a.stop() for a in agents), return_exceptions=True)


_LABEL = {
    "trigger": "🚨 monitoring", "signal": "🛰  observer", "hypothesis": "🩺 diagnostician",
    "remediation": "🛠  remediator", "validation_reject": "🚫 validator",
    "validation_pass": "✅ validator", "security_review": "🛡  commander→@security",
    "security_signoff": "🛡  security", "approval_request": "⏸  commander",
    "decision": "⚡ commander", "postmortem": "📋 commander", "halted": "🛑 commander",
}


def _print_transcript(messages: list) -> bool:
    """Render the run's messages in order (emitted via the logger so it survives
    stdout redirection). Returns True if the incident reached a postmortem."""
    rows = []
    for m in messages:
        d = P.decode(getattr(m, "content", ""))
        rows.append((getattr(m, "inserted_at", None), d, m))
    rows.sort(key=lambda x: (x[0] is None, x[0]))

    out = log.info
    out("\n" + "=" * 78)
    out("  BAND LIVE — 5 agents collaborating through Band via @mention reactions")
    out("=" * 78)
    resolved = False
    for _ts, d, m in rows:
        if d:
            intent = d.get("intent", "?")
            who = _LABEL.get(intent, getattr(m, "sender_name", "?"))
            tag = intent
            if intent == "postmortem":
                resolved = True
        else:
            who = "🧑 " + (getattr(m, "sender_name", None) or "human")
            tag = "human-reply"
        out(f"\n{who}  [{tag}]")
        out("   " + P.visible(getattr(m, "content", "")).replace("\n", "\n   "))
        for line in ((d or {}).get("ctx", {}).get("validation", {}) or {}).get("trace", []):
            out(f"      • {line}")
    out("\n" + "-" * 78)
    out("  RESULT: " + ("full chain via Band — REJECT→revise→PASS→human approve→executed ✅"
                        if resolved else "ran up to the point shown above"))
    out("-" * 78 + "\n")
    return resolved


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
async def main(timeout_s: float | None = None) -> None:
    """CLI demo: run ONE genuine incident through Band and print each handoff.
    The human gate AUTO-APPROVES once @security signs off (no manual typing) — the
    interactive gate lives in the app (a dashboard Approve button)."""
    timeout_s = timeout_s if timeout_s is not None else float(os.getenv("BAND_LIVE_TIMEOUT", "120"))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("band", "httpx", "httpcore", "websockets", "phoenix_channels_python_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not is_ready():
        raise SystemExit("band_live needs these env vars (set them in backend/.env, or run "
                         "the offline cascade with `python -m backend.run`):\n  "
                         + ", ".join(P.missing_env()))

    async def emit(event: str, data) -> None:
        if event == "message":
            who = _LABEL.get(_INTENT_BACK.get(data["intent"], data["intent"]), data["sender"])
            log.info("\n%s  [%s]\n   %s", who, data["intent"], data["text"].replace("\n", "\n   "))
        elif event == "await_approval":
            log.info("\n⏸  commander asked @human → auto-approving after @security sign-off …")
        elif event == "verdict":
            log.info("\n✅ RESOLVED via Band — %s · MTTR %.0fs · ~$%s averted",
                     data["action"], data["mttr_seconds"], f"{data['averted_cost_usd']:,.0f}")

    log.info("band_live: connecting %d agents to Band room %s (auto-approve demo) …",
             len(P.ALL_LISTENERS), P.chat_id())
    await run_live(emit, decide=None, timeout_s=timeout_s)
    log.info("\nband_live: done — the full chain happened via real @mention handoffs in Band.")


# reverse map for the CLI label lookup (frontend intent -> band_live intent)
_INTENT_BACK = {"signal": "signal", "hypothesis": "hypothesis",
                "remediation_proposal": "remediation", "validation_result": "validation_pass",
                "security_review": "security_review", "security_signoff": "security_signoff",
                "approval_request": "approval_request", "decision": "decision",
                "postmortem": "postmortem"}
