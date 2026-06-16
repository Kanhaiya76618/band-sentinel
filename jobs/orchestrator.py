"""
Aegis — job-search orchestrator.

Drives the second workflow by posting every step through the SAME bus the
incident side uses. The shape mirrors backend/orchestrator.run_incident:

    observer -> validator -> commander (human gate) -> tailor -> applier -> commander

`decide` is the human-in-the-loop gate (async, returns
{proceed, match_id, tailor}). None => auto-proceed with the top match (used by
tests / the offline path). The provider is injected so the orchestrator stays
backend-agnostic; the server passes a live AdzunaProvider.
"""
from __future__ import annotations

from backend.bus import AgentBus, make_bus
from backend.contracts import RoomMessage
from backend.llm import make_llm

from .agents import Applier, Commander, Observer, Tailor, Validator
from .contracts import JobMatch, JobMatches, SearchProfile, TailorResult
from .providers import JobSearchProvider, make_provider


async def run_job_search(
    bus: AgentBus | None = None,
    *,
    entry_mode: str,
    query: str,
    location: str | None = None,
    resume: dict | None = None,
    provider: JobSearchProvider | None = None,
    run_id: str = "cli",
    limit: int = 10,
    decide=None,
) -> tuple[list[RoomMessage], dict]:
    bus = bus or make_bus()
    provider = provider or make_provider()

    observer = Observer("@observer", make_llm("aiml"))
    validator = Validator("@validator", make_llm("featherless"))
    commander = Commander("@commander", make_llm("aiml"))
    tailor = Tailor("@tailor", make_llm("aiml"))
    applier = Applier("@applier", make_llm("featherless"))

    # 1) Observer -> profile
    prof_msg = await _post(bus, observer.build_profile(
        entry_mode=entry_mode, query=query, location=location, resume=resume))
    prof = SearchProfile(**prof_msg.payload)

    # 2) Validator -> ranked real postings
    matches_msg = await _post(bus, validator.search_and_rank(prof, provider, limit))
    jm = JobMatches(**matches_msg.payload)

    result = {
        "profile": prof.model_dump(mode="json"),
        "matches": [m.model_dump(mode="json") for m in jm.matches],
        "applications": [], "tailored_count": 0, "provider": provider.name,
    }
    if not jm.matches:
        await _post(bus, commander.decide("auto:policy", False, None, 0, 0))
        result["decision"] = {"proceeded": False, "reason": "no matches"}
        return await bus.history(), result

    # 3) Commander -> human gate
    await _post(bus, commander.request_approval(jm))
    if decide is not None:
        choice = await decide()
    else:
        choice = {"proceed": True, "match_id": jm.matches[0].id, "tailor": True}

    if not choice.get("proceed"):
        await _post(bus, commander.decide("human:user", False, None, 0, 0))
        result["decision"] = {"proceeded": False, "reason": "rejected by human"}
        return await bus.history(), result

    chosen = next((m for m in jm.matches if m.id == choice.get("match_id")), jm.matches[0])

    # 4) Tailor -> rewritten resume (or skip)
    tailor_msg = await _post(bus, tailor.tailor(prof, chosen, bool(choice.get("tailor")), run_id))
    tr = TailorResult(**tailor_msg.payload)
    if tr.tailored:
        result["tailored_count"] = 1

    # 5) Applier -> submit or queue (honest)
    app_msg = await _post(bus, applier.apply(prof, chosen, tr, run_id))
    from .contracts import Application
    app = Application(**app_msg.payload)
    result["applications"] = [app.model_dump(mode="json")]

    submitted = 1 if app.status == "submitted" else 0
    queued = 1 if app.status == "queued" else 0
    dec_msg = await _post(bus, commander.decide("human:user", True, chosen.id, submitted, queued))
    result["decision"] = dec_msg.payload
    return await bus.history(), result


async def _post(bus: AgentBus, msg: RoomMessage) -> RoomMessage:
    await bus.post(msg)
    return msg
