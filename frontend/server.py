"""
Aegis — platform server.

Phase 1 expands the original war-room server into the platform API without
touching the incident logic. It still builds the same LocalBus the agents post
to, subscribes a relay handler, runs run_incident(), and streams each
RoomMessage to the browser over SSE. New in the platform:

    * GET /                 single-page app shell (Dashboard / Resolve / Jobs /
                            History / Integrations / Settings)
    * GET /stream           live incident war-room (unchanged contract) — now
                            also PERSISTS the finished run to SQLite
    * GET /api/dashboard     summary cards + activity feed + service health

Run from the repo root (never cd into a subdir):

    python -m frontend.server        # then open http://127.0.0.1:8000

Stays offline-first: React + htm are vendored under static/vendor, so the UI
needs zero network. LLM_MODE defaults to offline, so the demo needs zero keys.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import email as emailer
from backend import health, ingest, reporting, store
from backend.bus import LocalBus
from backend.mockservice import Scenario
from backend.orchestrator import run_incident
from jobs import resume as resume_parser
from jobs.orchestrator import run_job_search
from jobs.providers import ProviderError, ProviderNotConfigured, make_provider

# In-memory sessions: run_id -> prepared inputs + the HITL gate (resolve + jobs).
_SESSIONS: dict[str, dict] = {}
_JOB_SESSIONS: dict[str, dict] = {}

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Aegis Platform")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
async def _startup() -> None:
    store.init_db()


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --------------------------------------------------------------------------- #
# App shell
# --------------------------------------------------------------------------- #
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


# --------------------------------------------------------------------------- #
# Platform API
# --------------------------------------------------------------------------- #
@app.get("/api/dashboard")
async def api_dashboard() -> JSONResponse:
    return JSONResponse({
        "cards": store.dashboard_stats(),
        "activity": store.recent_activity(),
        "services": health.service_status(),
    })


# --------------------------------------------------------------------------- #
# Incident war-room (live SSE) — now persists the finished run
# --------------------------------------------------------------------------- #
def _persist_incident(transcript: list[dict], verdict: dict, source: str) -> int:
    """Pull the service/region/severity off the opening signal and store the run."""
    service = region = severity = None
    postmortem = None
    for m in transcript:
        p = m.get("payload") or {}
        if m.get("intent") == "signal":
            service = p.get("service"); region = p.get("region"); severity = p.get("severity")
        if m.get("intent") == "postmortem":
            postmortem = p
    return store.save_incident_run(
        transcript=transcript, verdict=verdict,
        service=service or "checkout-api", region=region or "us-east-1",
        severity=severity or "SEV1", source=source,
        incident_id=(postmortem or {}).get("incident_id"), postmortem=postmortem,
    )


# --------------------------------------------------------------------------- #
# Phase 2 — REAL incident resolution on uploaded telemetry, with a UI HITL gate
# --------------------------------------------------------------------------- #
@app.post("/api/resolve/start")
async def resolve_start(request: Request) -> JSONResponse:
    """Prepare a resolve session from an upload, a pasted artifact, or a description."""
    body = await request.json()
    mode = body.get("mode", "demo")
    scenario = Scenario()
    if body.get("service"):
        scenario.service = str(body["service"])
    if body.get("region"):
        scenario.region = str(body["region"])
    if body.get("revenue_per_min"):
        try:
            scenario.revenue_per_min_usd = float(body["revenue_per_min"])
        except (TypeError, ValueError):
            pass

    telemetry = None
    note = "Generated incident from the offline scenario."
    if mode in ("upload", "paste"):
        raw = body.get("content") or ""
        try:
            telemetry = ingest.parse_telemetry(raw, body.get("filename", "upload.log"))
        except ingest.IngestError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        note = f"Parsed {len(telemetry)} telemetry points from {body.get('filename', 'upload')}."
    elif mode == "describe":
        note = f"Generated telemetry for {scenario.service}/{scenario.region}."

    run_id = uuid4().hex
    _SESSIONS[run_id] = {
        "telemetry": telemetry, "scenario": scenario,
        "source": "demo" if mode == "demo" else "upload",
        "event": None, "approved": False,
    }
    return JSONResponse({"run_id": run_id, "note": note,
                         "points": len(telemetry) if telemetry else 0})


@app.post("/api/resolve/decision")
async def resolve_decision(request: Request) -> JSONResponse:
    """The UI human-approval gate: Approve/Reject the irreversible action."""
    body = await request.json()
    sess = _SESSIONS.get(body.get("run_id", ""))
    if not sess or not sess.get("event"):
        return JSONResponse({"error": "no pending approval for this run"}, status_code=404)
    sess["approved"] = bool(body.get("approve"))
    sess["event"].set()
    return JSONResponse({"ok": True, "approved": sess["approved"]})


@app.get("/api/resolve/stream")
async def resolve_stream(request: Request) -> StreamingResponse:
    """Drive the real pipeline; pause at the irreversible action for the UI gate."""
    run_id = request.query_params.get("run_id", "")
    pace = float(request.query_params.get("pace", "0.5"))
    sess = _SESSIONS.get(run_id)
    queue: asyncio.Queue = asyncio.Queue()

    if not sess:
        async def gone():
            yield _sse("error", {"detail": "Unknown or expired run_id. Start a run first."})
            yield _sse("done", {})
        return StreamingResponse(gone(), media_type="text/event-stream")

    bus = LocalBus()
    transcript: list[dict] = []

    async def relay(msg) -> None:
        dumped = msg.model_dump(mode="json")
        transcript.append(dumped)
        await queue.put(("message", dumped))

    bus.subscribe(relay)

    async def approve() -> bool:
        ev = asyncio.Event()
        sess["event"] = ev
        await queue.put(("await_approval", {"run_id": run_id}))
        await ev.wait()
        return bool(sess.get("approved"))

    async def drive() -> None:
        try:
            _, verdict = await run_incident(
                bus, telemetry=sess["telemetry"], scenario=sess["scenario"], approve=approve,
            )
            if not verdict:
                await queue.put(("verdict", {"resolved": False, "no_incident": True}))
                return
            run_db_id = None
            email_status = {"status": "skipped", "detail": "Email sent only on resolution."}
            if verdict.get("resolved") or verdict.get("rejected_by"):
                run_db_id = _persist_incident(transcript, verdict, source=sess["source"])
            if verdict.get("resolved"):
                try:
                    run = store.get_incident_run(run_db_id)
                    email_status = emailer.send_incident_report(run, to=store.email_recipients())
                except emailer.EmailNotConfigured as e:
                    email_status = {"status": "not_configured", "detail": str(e)}
                except emailer.EmailError as e:
                    email_status = {"status": "error", "detail": str(e)}
            await queue.put(("verdict", {**verdict, "run_db_id": run_db_id}))
            await queue.put(("email", email_status))
        except Exception as exc:
            await queue.put(("error", {"detail": str(exc)}))
        finally:
            await queue.put(("done", None))
            _SESSIONS.pop(run_id, None)

    async def events():
        task = asyncio.create_task(drive())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "done":
                    yield _sse("done", {})
                    break
                yield _sse(kind, data)
                if kind == "message" and pace > 0 and not await request.is_disconnected():
                    await asyncio.sleep(pace)
        finally:
            task.cancel()

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Run one incident and relay every room message live, then the verdict."""
    pace = float(request.query_params.get("pace", os.getenv("AEGIS_PACE", "0.7")))
    queue: asyncio.Queue = asyncio.Queue()
    bus = LocalBus()
    transcript: list[dict] = []

    async def relay(msg) -> None:
        dumped = msg.model_dump(mode="json")
        transcript.append(dumped)
        await queue.put(("message", dumped))

    bus.subscribe(relay)

    async def drive() -> None:
        try:
            _, verdict = await run_incident(bus)
            # Persist the finished run so the dashboard reflects reality.
            try:
                _persist_incident(transcript, verdict, source="demo")
            except Exception:  # persistence must never break the live stream
                pass
            await queue.put(("verdict", verdict))
        except Exception as exc:  # surface failures to the UI instead of hanging
            await queue.put(("error", {"detail": str(exc)}))
        finally:
            await queue.put(("done", None))

    async def events():
        task = asyncio.create_task(drive())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "done":
                    yield _sse("done", {})
                    break
                yield _sse(kind, data)
                # pace only the room chatter so the cascade reads "live"; the
                # verdict lands immediately after the last message.
                if kind == "message" and pace > 0 and not await request.is_disconnected():
                    await asyncio.sleep(pace)
        finally:
            task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
# Phase 5 — Integrations (test buttons), Settings, Analytics
# --------------------------------------------------------------------------- #
@app.post("/api/integrations/test/{key}")
async def api_integration_test(key: str) -> JSONResponse:
    return JSONResponse({"key": key, **health.test_service(key)})


@app.get("/api/settings")
async def api_settings_get() -> JSONResponse:
    return JSONResponse({
        "services": health.service_status(),          # config status only, never values
        "email_recipients": store.get_setting("email_recipients", os.getenv("EMAIL_TO", "")),
        "default_field": store.get_setting("default_field", "Software Engineer"),
    })


@app.post("/api/settings")
async def api_settings_set(request: Request) -> JSONResponse:
    body = await request.json()
    if "email_recipients" in body:
        store.set_setting("email_recipients", str(body["email_recipients"]).strip())
    if "default_field" in body:
        store.set_setting("default_field", str(body["default_field"]).strip())
    return JSONResponse({"ok": True})


@app.get("/api/analytics")
async def api_analytics() -> JSONResponse:
    return JSONResponse(store.analytics())


# --------------------------------------------------------------------------- #
# Phase 4 — History + downloadable reports
# --------------------------------------------------------------------------- #
@app.get("/api/history")
async def api_history(type: str = "all") -> JSONResponse:
    """Unified, newest-first list of past runs, optionally filtered by type."""
    items: list[dict] = []
    if type in ("all", "incident"):
        for r in store.list_incident_runs(200):
            v = r.get("verdict") or {}
            items.append({
                "kind": "incident", "id": r["id"], "created_at": r["created_at"],
                "title": f"{r.get('service')} / {r.get('region')}",
                "subtitle": (f"Resolved via {v.get('action')}" if r.get("resolved")
                             else "Escalated to human"),
                "status": "resolved" if r.get("resolved") else "escalated",
                "metric": f"${(r.get('averted_cost_usd') or 0):,.0f} averted",
            })
    if type in ("all", "job"):
        for r in store.list_job_runs(200):
            items.append({
                "kind": "job", "id": r["id"], "created_at": r["created_at"],
                "title": f"{r.get('query') or r.get('entry_mode')}",
                "subtitle": f"{r.get('match_count')} matches · {r.get('entry_mode')} search",
                "status": "submitted" if r.get("applied_count") else "queued" if r.get("queued_count") else "searched",
                "metric": f"{r.get('tailored_count')} tailored",
            })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return JSONResponse({"items": items})


@app.get("/api/history/{kind}/{run_id}")
async def api_history_detail(kind: str, run_id: int) -> JSONResponse:
    run = store.get_incident_run(run_id) if kind == "incident" else store.get_job_run(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"kind": kind, "run": run})


@app.get("/api/report/{kind}/{run_id}")
async def api_report(kind: str, run_id: int, fmt: str = "md"):
    run = store.get_incident_run(run_id) if kind == "incident" else store.get_job_run(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        path = reporting.build_report(kind, run, fmt)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    media = "text/markdown" if fmt == "md" else "application/pdf"
    return FileResponse(path, filename=Path(path).name, media_type=media)


@app.get("/api/download")
async def download(path: str):
    """Serve a generated artifact (tailored resume / report) from under data/."""
    target = Path(path).resolve()
    if not str(target).startswith(str(store.DATA_DIR.resolve())) or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(target, filename=target.name)


# --------------------------------------------------------------------------- #
# Phase 3 — Jobs: second multi-agent workflow over the same bus
# --------------------------------------------------------------------------- #
@app.post("/api/jobs/start")
async def jobs_start(request: Request) -> JSONResponse:
    """Prepare a job-search session. Fails loud if the provider isn't configured."""
    body = await request.json()
    entry_mode = body.get("entry_mode", "field")
    query = (body.get("query") or "").strip()
    location = (body.get("location") or "").strip() or None

    # Provider must be real — surface a clear message if keys are missing.
    try:
        provider = make_provider()
    except ProviderNotConfigured as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    resume_profile = None
    if entry_mode == "resume":
        b64 = body.get("resume_b64")
        if not b64:
            return JSONResponse({"error": "Resume upload required for resume mode."}, status_code=400)
        try:
            raw = base64.b64decode(b64.split(",")[-1])
            from backend.llm import make_llm
            resume_profile = resume_parser.parse_profile(
                raw, body.get("resume_name", "resume.pdf"), make_llm("aiml"))
        except resume_parser.ResumeError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        query = query or (resume_profile.get("titles") or ["resume profile"])[0]

    if entry_mode != "resume" and not query:
        return JSONResponse({"error": "A company name or field is required."}, status_code=400)

    run_id = uuid4().hex
    _JOB_SESSIONS[run_id] = {
        "entry_mode": entry_mode, "query": query, "location": location,
        "resume": resume_profile, "provider": provider,
        "event": None, "choice": None,
    }
    preview = None
    if resume_profile:
        preview = {"titles": resume_profile.get("titles"), "skills": resume_profile.get("skills"),
                   "seniority": resume_profile.get("seniority")}
    return JSONResponse({"run_id": run_id, "provider": provider.name, "profile": preview})


@app.post("/api/jobs/decision")
async def jobs_decision(request: Request) -> JSONResponse:
    """The job-run human gate: proceed with a chosen match (+ tailor) or cancel."""
    body = await request.json()
    sess = _JOB_SESSIONS.get(body.get("run_id", ""))
    if not sess or not sess.get("event"):
        return JSONResponse({"error": "no pending decision for this run"}, status_code=404)
    sess["choice"] = {
        "proceed": bool(body.get("proceed")),
        "match_id": body.get("match_id"),
        "tailor": bool(body.get("tailor")),
    }
    sess["event"].set()
    return JSONResponse({"ok": True, "choice": sess["choice"]})


@app.get("/api/jobs/stream")
async def jobs_stream(request: Request) -> StreamingResponse:
    """Drive the job pipeline; pause for the human to pick a match + tailoring."""
    run_id = request.query_params.get("run_id", "")
    pace = float(request.query_params.get("pace", "0.5"))
    sess = _JOB_SESSIONS.get(run_id)
    queue: asyncio.Queue = asyncio.Queue()

    if not sess:
        async def gone():
            yield _sse("error", {"detail": "Unknown or expired run_id. Start a run first."})
            yield _sse("done", {})
        return StreamingResponse(gone(), media_type="text/event-stream")

    bus = LocalBus()
    transcript: list[dict] = []

    async def relay(msg) -> None:
        dumped = msg.model_dump(mode="json")
        transcript.append(dumped)
        await queue.put(("message", dumped))

    bus.subscribe(relay)

    async def decide() -> dict:
        ev = asyncio.Event()
        sess["event"] = ev
        await queue.put(("await_decision", {"run_id": run_id}))
        await ev.wait()
        return sess.get("choice") or {"proceed": False}

    async def drive() -> None:
        try:
            _, result = await run_job_search(
                bus, entry_mode=sess["entry_mode"], query=sess["query"],
                location=sess["location"], resume=sess["resume"],
                provider=sess["provider"], run_id=run_id, decide=decide,
            )
            run_db_id = store.save_job_run(
                entry_mode=sess["entry_mode"], query=sess["query"],
                profile=result["profile"], matches=result["matches"],
                applications=result["applications"], transcript=transcript,
                verdict=result.get("decision"), tailored_count=result["tailored_count"],
            )
            await queue.put(("result", {**result, "run_db_id": run_db_id}))
        except ProviderError as e:
            await queue.put(("error", {"detail": f"Job provider error: {e}"}))
        except Exception as exc:
            await queue.put(("error", {"detail": str(exc)}))
        finally:
            await queue.put(("done", None))
            _JOB_SESSIONS.pop(run_id, None)

    async def events():
        task = asyncio.create_task(drive())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "done":
                    yield _sse("done", {})
                    break
                yield _sse(kind, data)
                if kind == "message" and pace > 0 and not await request.is_disconnected():
                    await asyncio.sleep(pace)
        finally:
            task.cancel()

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    import uvicorn

    host = os.getenv("AEGIS_HOST", "127.0.0.1")
    port = int(os.getenv("AEGIS_PORT", "8000"))
    print(f"  AEGIS platform → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
