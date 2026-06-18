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
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse, JSONResponse, RedirectResponse, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from backend import auth
from backend import email as emailer
from backend import health, ingest, reporting, store
from backend.bus import LocalBus
from backend.mockservice import Scenario
from backend.orchestrator import run_incident
from jobs import resume as resume_parser
from jobs.orchestrator import run_job_search
from jobs.providers import ProviderError, ProviderNotConfigured, make_provider
from channels import registry as channels

# In-memory sessions: run_id -> prepared inputs + the HITL gate (resolve + jobs).
_SESSIONS: dict[str, dict] = {}
_JOB_SESSIONS: dict[str, dict] = {}


def _resolve_gate(kind: str, run_id: str, approve: bool) -> bool:
    """Resolve a pending commander gate from ANY source (browser or channel)."""
    if kind == "incident":
        sess = _SESSIONS.get(run_id)
        if sess and sess.get("event") and not sess["event"].is_set():
            sess["approved"] = approve
            sess["event"].set()
            return True
    elif kind == "job":
        sess = _JOB_SESSIONS.get(run_id)
        if sess and sess.get("event") and not sess["event"].is_set():
            sess["choice"] = {"proceed": approve, "match_id": None, "tailor": True}
            sess["event"].set()
            return True
    return False


async def _channel_command(cmd: dict) -> bool:
    """Inbound channel command (Telegram button, etc.) -> resolve the gate."""
    return _resolve_gate(cmd.get("kind", ""), cmd.get("run_id", ""), cmd.get("action") == "approve")


def _incident_approval_text(transcript: list[dict]) -> tuple[str, str]:
    """Assemble request → reasoning → response for the channel thread."""
    svc = diag = action = val = None
    for m in transcript:
        p = m.get("payload") or {}
        if m.get("intent") == "signal":
            svc = f"{p.get('service')}/{p.get('region')}"
        elif m.get("intent") == "hypothesis":
            diag = p.get("root_cause")
        elif m.get("intent") == "remediation_proposal":
            action = p.get("action")
        elif m.get("intent") == "validation_result" and p.get("passed"):
            val = f"p99 {round(p.get('projected_p99_ms', 0))}ms, err {p.get('projected_error_rate', 0) * 100:.2f}%"
    title = f"⚠ Aegis — approval needed for {svc or 'incident'}"
    body = (f"Diagnosis: {diag or 'n/a'}\n"
            f"Proposed fix: {action or 'n/a'} (irreversible)\n"
            f"Validator: PASSED ({val or 'within SLO'})\nApprove to execute.")
    return title, body


STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Aegis Platform")

# CORS for the split deploy (Vercel frontend -> Railway backend). Set
# AEGIS_CORS_ORIGINS to a comma-separated list of allowed origins (the Vercel
# URL); "*" by default for local/dev. Credentials need explicit origins, so when
# "*" we disable credentials (the public demo needs no cookies).
_CORS = [o.strip() for o in os.getenv("AEGIS_CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_credentials=_CORS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
async def _startup() -> None:
    store.init_db()
    store.purge_expired_sessions()
    await channels.start_all(_channel_command)  # registers handler + starts listeners


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --------------------------------------------------------------------------- #
# Auth (Phase 7) — demo-grade: pbkdf2-hashed passwords, httpOnly session cookie.
# A single middleware gates the whole app: public = landing, static, /api/auth/*,
# and "/" (which itself redirects to the landing/sign-in when unauthenticated).
# --------------------------------------------------------------------------- #
# The incident DEMO (Simulate incident + its SSE) is PUBLIC so judges can watch
# the war room without signing up; the personal workspace stays gated.
_PUBLIC_EXACT = {"/landing", "/favicon.ico", "/", "/app"}
_PUBLIC_PREFIX = ("/static/", "/api/auth/", "/api/simulate")


def _uid(request: Request):
    u = getattr(request.state, "user", None)
    return u["id"] if u else None


def _set_session_cookie(resp, token: str) -> None:
    # httpOnly + expiry. (Secure omitted so it works over http://localhost; set it
    # behind HTTPS in production.)
    resp.set_cookie(auth.COOKIE_NAME, token, max_age=auth.SESSION_SECONDS,
                    httponly=True, samesite="lax", path="/")


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    token = request.cookies.get(auth.COOKIE_NAME)
    request.state.user = store.get_session_user(token) if token else None
    path = request.url.path
    public = path in _PUBLIC_EXACT or any(path.startswith(p) for p in _PUBLIC_PREFIX)
    if not public and not request.state.user:
        if path.startswith("/api/") or path == "/stream":
            return JSONResponse({"error": "Authentication required.", "auth": False}, status_code=401)
        return RedirectResponse("/landing", status_code=302)
    return await call_next(request)


def _login_response(user_id: int, email: str) -> JSONResponse:
    token = auth.new_session_token()
    store.create_session(token, user_id, time.time() + auth.SESSION_SECONDS)
    resp = JSONResponse({"ok": True, "email": email})
    _set_session_cookie(resp, token)
    return resp


@app.post("/api/auth/signup")
async def auth_signup(request: Request) -> JSONResponse:
    body = await request.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    if not auth.valid_email(email):
        return JSONResponse({"error": "Enter a valid email address."}, status_code=400)
    problem = auth.password_problem(password)
    if problem:
        return JSONResponse({"error": problem}, status_code=400)
    if store.get_user_by_email(email):
        return JSONResponse({"error": "Account exists — sign in instead.", "exists": True}, status_code=409)
    uid = store.create_user(email, auth.hash_password(password))
    if uid is None:  # lost a race between the check and the insert
        return JSONResponse({"error": "Account exists — sign in instead.", "exists": True}, status_code=409)
    return _login_response(uid, email)


@app.post("/api/auth/login")
async def auth_login(request: Request) -> JSONResponse:
    body = await request.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    user = store.get_user_by_email(email)
    if not user or not auth.verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "Invalid email or password."}, status_code=401)
    return _login_response(user["id"], user["email"])


@app.post("/api/auth/logout")
async def auth_logout(request: Request) -> JSONResponse:
    token = request.cookies.get(auth.COOKIE_NAME)
    if token:
        store.delete_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@app.get("/api/auth/me")
async def auth_me(request: Request) -> JSONResponse:
    u = getattr(request.state, "user", None)
    if not u:
        return JSONResponse({"auth": False}, status_code=401)
    return JSONResponse({
        "auth": True, "email": u["email"],
        "recent_recipients": store.get_recent_recipients(u["id"]),
        "email_configured": emailer.is_configured(),
        "has_resume": store.get_user_resume(u["id"]) is not None,
    })


# --------------------------------------------------------------------------- #
# App shell
# --------------------------------------------------------------------------- #
@app.get("/")
async def index(request: Request):
    if not getattr(request.state, "user", None):
        return RedirectResponse("/landing", status_code=302)
    return FileResponse(STATIC / "index.html")


@app.get("/app")
async def app_shell() -> FileResponse:
    """Public SPA entry (matches the Vercel /app rewrite). The SPA itself checks
    auth via /api/auth/me and redirects to /landing when anonymous."""
    return FileResponse(STATIC / "index.html")


@app.get("/landing")
async def landing() -> FileResponse:
    """Public marketing/submission + sign-in page."""
    return FileResponse(STATIC / "landing.html")


# --------------------------------------------------------------------------- #
# Platform API
# --------------------------------------------------------------------------- #
@app.get("/api/dashboard")
async def api_dashboard(request: Request) -> JSONResponse:
    uid = _uid(request)
    return JSONResponse({
        "cards": store.dashboard_stats(user_id=uid),
        "activity": store.recent_activity(user_id=uid),
        "services": health.service_status(),
    })


# --------------------------------------------------------------------------- #
# Incident war-room (live SSE) — now persists the finished run
# --------------------------------------------------------------------------- #
def _persist_incident(transcript: list[dict], verdict: dict, source: str,
                      user_id: int | None = None) -> int:
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
        user_id=user_id,
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
        
        # Calculate a stable hash of the telemetry content + filename
        import hashlib
        h_seed = int(hashlib.md5((body.get("filename", "") + raw).encode("utf-8")).hexdigest(), 16)
        
        # Dynamic cost and incident metrics per uploaded file
        scenario.revenue_per_min_usd = float(500 + (h_seed % 2001))
        scenario.human_baseline_mttr_s = float((30 + (h_seed % 36)) * 60)
        scenario.incident_id = f"INC-{2000 + (h_seed % 8000)}"
        
        # Extract deploy version if present in the telemetry data
        deploy_version = next((p["deploy"] for p in telemetry if p.get("deploy")), None)
        if deploy_version:
            scenario.deploy = deploy_version
            
    elif mode == "describe":
        note = f"Generated telemetry for {scenario.service}/{scenario.region}."

    user = request.state.user
    run_id = uuid4().hex
    _SESSIONS[run_id] = {
        "telemetry": telemetry, "scenario": scenario,
        "source": "demo" if mode == "demo" else "upload",
        "event": None, "approved": False,
        "user_id": user["id"] if user else None,
        "user_email": user["email"] if user else None,
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
        # Fan the approval request out to any enabled channels (Telegram resolves
        # the gate natively; others carry a deep link). Non-blocking.
        title, body = _incident_approval_text(transcript)
        asyncio.create_task(channels.broadcast_approval(
            kind="incident", run_id=run_id, title=title, body=body))
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
            if verdict.get("resolved") or verdict.get("rejected_by"):
                run_db_id = _persist_incident(transcript, verdict, source=sess["source"],
                                              user_id=sess.get("user_id"))
            await queue.put(("verdict", {**verdict, "run_db_id": run_db_id}))
            # No silent sends: on resolution we PROMPT the UI for a recipient
            # (prefilled with the signed-in user's email) and a confirm click.
            if verdict.get("resolved") and run_db_id:
                await queue.put(("email", {
                    "status": "prompt", "run_db_id": run_db_id,
                    "default": sess.get("user_email"),
                    "recent": store.get_recent_recipients(sess["user_id"]) if sess.get("user_id") else [],
                    "configured": emailer.is_configured(),
                }))
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


@app.post("/api/resolve/email")
async def resolve_email(request: Request) -> JSONResponse:
    """Send the incident report to a user-confirmed recipient list (no silent send).
    Envelope From stays EMAIL_FROM; Reply-To + a 'sent by' line carry the user."""
    u = request.state.user
    body = await request.json()
    recipients = [r.strip() for r in (body.get("recipients") or []) if r and r.strip()]
    if not recipients:
        return JSONResponse({"error": "Enter at least one recipient."}, status_code=400)
    run = store.get_incident_run(int(body.get("run_db_id") or 0), user_id=u["id"])
    if not run:
        return JSONResponse({"error": "Incident run not found."}, status_code=404)
    try:
        res = emailer.send_incident_report(run, to=recipients, sent_by=u["email"])
        store.remember_recipients(u["id"], recipients)
        return JSONResponse({"status": "sent", **res})
    except emailer.EmailNotConfigured as e:
        return JSONResponse({"status": "not_configured", "detail": str(e)})
    except emailer.EmailRecipientNotAllowed as e:
        return JSONResponse({"status": "recipient_not_allowed", "detail": str(e)})
    except emailer.EmailError as e:
        return JSONResponse({"status": "error", "detail": str(e)})


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
# Simulate incident — PUBLIC trigger. Genuine reactive coordination through Band
# when keys are present (reuses band_live's handlers), deterministic OFFLINE run
# otherwise. Either way the war-room transcript streams over SSE; the human gate
# is a dashboard Approve button with auto-approve fallback so it never hangs.
# --------------------------------------------------------------------------- #
_SIM: dict[str, dict] = {}


def _band_live_ready() -> bool:
    """All BAND_* set (incl. @security)? Checked WITHOUT importing the band SDK."""
    try:
        from band_live import protocol as blp
        return not blp.missing_env()
    except Exception:
        return False


@app.post("/api/simulate/start")
async def simulate_start(request: Request) -> JSONResponse:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    want = (body.get("mode") or "auto").lower()
    genuine = want == "genuine" or (want == "auto" and _band_live_ready())
    if want == "offline":
        genuine = False
    run_id = uuid4().hex
    _SIM[run_id] = {"mode": "genuine" if genuine else "offline",
                    "event": asyncio.Event(), "approved": True}
    return JSONResponse({"run_id": run_id, "mode": _SIM[run_id]["mode"],
                         "band_ready": _band_live_ready()})


@app.post("/api/simulate/decision")
async def simulate_decision(request: Request) -> JSONResponse:
    body = await request.json()
    sess = _SIM.get(body.get("run_id", ""))
    if not sess:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    sess["approved"] = bool(body.get("approve", True))
    sess["event"].set()
    return JSONResponse({"ok": True, "approved": sess["approved"]})


@app.get("/api/simulate/stream")
async def simulate_stream(request: Request) -> StreamingResponse:
    run_id = request.query_params.get("run_id", "")
    sess = _SIM.get(run_id)
    queue: asyncio.Queue = asyncio.Queue()
    if not sess:
        async def gone():
            yield _sse("error", {"detail": "Start a run first."})
            yield _sse("done", {})
        return StreamingResponse(gone(), media_type="text/event-stream")

    pace = float(request.query_params.get("pace", "0.5"))

    async def emit(event: str, data) -> None:
        await queue.put((event, data))

    async def decide():
        # Dashboard Approve button (or auto-approve after the gate).
        if sess["event"].is_set():
            return "approve" if sess["approved"] else "reject"
        return None

    async def run_offline() -> None:
        bus = LocalBus()
        transcript: list[dict] = []

        async def relay(msg) -> None:
            d = msg.model_dump(mode="json")
            transcript.append(d)
            await emit("message", d)

        bus.subscribe(relay)

        async def approve_cb() -> bool:
            await emit("await_approval", {})
            try:
                await asyncio.wait_for(sess["event"].wait(), timeout=12.0)
                return sess["approved"]
            except asyncio.TimeoutError:
                return True   # auto-approve fallback — never hang

        _, verdict = await run_incident(bus, approve=approve_cb)
        try:
            _persist_incident(transcript, verdict, source="demo")
        except Exception:
            pass
        if verdict:
            await emit("verdict", verdict)

    async def drive() -> None:
        try:
            if sess["mode"] == "genuine":
                try:
                    from band_live.runner import run_live
                    await emit("notice", {"mode": "genuine",
                              "detail": "Genuine reactive coordination running through Band."})
                    await run_live(emit, decide, timeout_s=120.0, auto_after_s=10.0)
                    return
                except Exception as exc:
                    # Any Band hiccup → seamless offline fallback, never an error.
                    sess["mode"] = "offline"
                    await emit("notice", {"mode": "offline",
                              "detail": "Showing the deterministic cascade (Band unavailable)."})
            await run_offline()
        except Exception as exc:
            await emit("notice", {"mode": "offline", "detail": "Deterministic cascade."})
            try:
                await run_offline()
            except Exception:
                pass
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
                # Pace only offline chatter so it reads "live"; genuine is already
                # paced by Band round-trips.
                if (kind == "message" and sess["mode"] == "offline" and pace > 0
                        and not await request.is_disconnected()):
                    await asyncio.sleep(pace)
        finally:
            task.cancel()
            _SIM.pop(run_id, None)

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- #
# Phase 6 — Channels: multi-platform interface layer
# --------------------------------------------------------------------------- #
@app.get("/api/channels")
async def api_channels() -> JSONResponse:
    return JSONResponse({"channels": channels.all_status()})


@app.post("/api/channels/{name}/test")
async def api_channel_test(name: str) -> JSONResponse:
    ch = channels.get(name)
    if not ch:
        return JSONResponse({"error": f"unknown channel '{name}'"}, status_code=404)
    return JSONResponse({"channel": name, **(await ch.send_test())})


@app.post("/api/channels/draft")
async def api_channel_draft(request: Request) -> JSONResponse:
    """Generate an approve-then-share post draft for a job match (no posting)."""
    body = await request.json()
    title = body.get("title", "a new role")
    company = body.get("company", "a company")
    skills = ", ".join((body.get("skills") or [])[:5]) or "my background"
    from backend.llm import make_llm
    fallback = (f"Excited to be exploring {title} opportunities at {company}! "
                f"Bringing experience in {skills}. Open to connecting. #opentowork #hiring")
    draft = ""
    if os.getenv("LLM_MODE", "offline").lower() != "offline":  # offline echoes the prompt
        draft = make_llm("aiml").complete(
            system="Write a concise, professional LinkedIn/X post (<280 chars). 1-2 sentences + 2 hashtags.",
            user=f"Role: {title} at {company}. Skills: {skills}.", role="@applier", tag="post",
        )
    text = draft.strip() if draft and len(draft.strip()) > 40 else fallback
    return JSONResponse({"draft": text[:280],
                         "post_targets": [c.name for c in channels.with_capability("post")]})


@app.post("/api/channels/{name}/post")
async def api_channel_post(name: str, request: Request) -> JSONResponse:
    """Publish an already-approved draft. Requires the post capability + a token."""
    ch = channels.get(name)
    if not ch:
        return JSONResponse({"error": f"unknown channel '{name}'"}, status_code=404)
    if not ch.capabilities.get("post"):
        return JSONResponse({"error": f"{name} cannot post in this runtime: {ch.status()['detail']}"},
                            status_code=400)
    text = (await request.json()).get("text", "").strip()
    if not text:
        return JSONResponse({"error": "empty post text"}, status_code=400)
    return JSONResponse({"channel": name, **(await ch.send(text))})


@app.post("/api/channels/whatsapp/inbound")
async def api_whatsapp_inbound(request: Request) -> JSONResponse:
    """Twilio webhook for WhatsApp replies (needs a public URL). 'approve'/'reject'
    resolves the single pending incident gate. Honest: only works once deployed."""
    import urllib.parse
    raw = (await request.body()).decode("utf-8", "replace")
    form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
    bodytext = (form.get("Body") or "").strip().lower()
    if bodytext not in ("approve", "reject", "yes", "no"):
        return JSONResponse({"ok": False, "detail": "reply 'approve' or 'reject'"})
    approve = bodytext in ("approve", "yes")
    pending = [rid for rid, s in _SESSIONS.items() if s.get("event") and not s["event"].is_set()]
    if not pending:
        return JSONResponse({"ok": False, "detail": "no pending approval"})
    _resolve_gate("incident", pending[-1], approve)
    return JSONResponse({"ok": True, "detail": f"{'approved' if approve else 'rejected'}"})


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
async def api_analytics(request: Request) -> JSONResponse:
    return JSONResponse(store.analytics(user_id=_uid(request)))


# --------------------------------------------------------------------------- #
# Phase 4 — History + downloadable reports
# --------------------------------------------------------------------------- #
@app.get("/api/history")
async def api_history(request: Request, type: str = "all") -> JSONResponse:
    """Unified, newest-first list of THIS user's past runs, optionally filtered."""
    uid = _uid(request)
    items: list[dict] = []
    if type in ("all", "incident"):
        for r in store.list_incident_runs(200, user_id=uid):
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
        for r in store.list_job_runs(200, user_id=uid):
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
async def api_history_detail(request: Request, kind: str, run_id: int) -> JSONResponse:
    uid = _uid(request)
    run = (store.get_incident_run(run_id, user_id=uid) if kind == "incident"
           else store.get_job_run(run_id, user_id=uid))
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"kind": kind, "run": run})


@app.get("/api/report/{kind}/{run_id}")
async def api_report(request: Request, kind: str, run_id: int, fmt: str = "md"):
    uid = _uid(request)
    run = (store.get_incident_run(run_id, user_id=uid) if kind == "incident"
           else store.get_job_run(run_id, user_id=uid))
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

    user = request.state.user
    # Remember the parsed resume so "Rebuild resume for a company" can reuse it.
    if resume_profile and user:
        store.set_user_resume(user["id"], resume_profile)
    run_id = uuid4().hex
    _JOB_SESSIONS[run_id] = {
        "entry_mode": entry_mode, "query": query, "location": location,
        "resume": resume_profile, "provider": provider,
        "event": None, "choice": None,
        "user_id": user["id"] if user else None,
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
                user_id=sess.get("user_id"),
            )
            # Push a job alert to notify-capable channels (Telegram/Discord).
            top = (result["matches"] or [{}])[0]
            if top:
                asyncio.create_task(channels.notify(
                    f"✦ Aegis jobs — {len(result['matches'])} matches for '{sess['query']}'. "
                    f"Top: {top.get('title')} @ {top.get('company')} "
                    f"({round((top.get('fit_score') or 0) * 100)}% fit). {top.get('url', '')}"))
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


def _resume_profile_for(uid: int, body: dict):
    """Resolve the resume profile from an upload, else the user's stored parse.
    Returns (profile, error_response). Read-only: stores only the parsed ORIGINAL."""
    b64 = body.get("resume_b64")
    if b64:
        try:
            raw = base64.b64decode(b64.split(",")[-1])
            from backend.llm import make_llm
            profile = resume_parser.parse_profile(raw, body.get("resume_name", "resume.pdf"),
                                                  make_llm("aiml"))
            store.set_user_resume(uid, profile)   # the parsed original, never a modified one
            return profile, None
        except resume_parser.ResumeError as e:
            return None, JSONResponse({"error": str(e)}, status_code=400)
    profile = store.get_user_resume(uid)
    if not profile:
        return None, JSONResponse(
            {"error": "No resume on file — upload one or run a resume job search first."},
            status_code=400)
    return profile, None


@app.post("/api/jobs/analyze")
async def jobs_analyze(request: Request) -> JSONResponse:
    """
    READ-ONLY resume fit analysis for a selected job. Reads the parsed resume + the
    job and returns structured improvement SUGGESTIONS — it NEVER rewrites, stores,
    or emails a modified resume, and never fabricates. Uses the LLM when a key is
    set (system prompt enforces the rules), else a deterministic rule-based fallback.
    """
    u = request.state.user
    body = await request.json()
    company = (body.get("company") or "").strip()
    title = (body.get("title") or body.get("role") or "").strip()
    job_desc = (body.get("job_description") or body.get("description") or "").strip()
    if not (company or title):
        return JSONResponse({"error": "Select a job (company/title) to analyze against."},
                            status_code=400)

    profile, err = _resume_profile_for(u["id"], body)
    if err:
        return err

    from backend.llm import make_llm
    from jobs.analyze import analyze_fit
    job = {"title": title or f"Role at {company}", "company": company, "description": job_desc}
    # make_llm returns OfflineLLM when no key is set; analyze_fit then uses the
    # rule-based fallback (OfflineLLM yields no JSON), so it always returns suggestions.
    llm = make_llm("aiml")
    from backend.llm import OfflineLLM
    analysis = analyze_fit(profile, job, None if isinstance(llm, OfflineLLM) else llm)
    return JSONResponse({"ok": True, "job": job, "analysis": analysis,
                         "resume_unchanged": True})


@app.post("/api/jobs/analyze/email")
async def jobs_analyze_email(request: Request) -> JSONResponse:
    """Optionally email the SUGGESTIONS summary (no attachment, no resume file) to a
    confirmed recipient. From stays EMAIL_FROM; Reply-To = the user."""
    u = request.state.user
    body = await request.json()
    job = body.get("job") or {}
    analysis = body.get("analysis") or {}
    recipient = (body.get("recipient") or "").strip() or u["email"]
    if not analysis:
        return JSONResponse({"error": "Nothing to email — run the analysis first."}, status_code=400)
    from jobs.analyze import summary_text
    subject, text, html = summary_text(job, analysis)
    try:
        res = emailer.send_email(subject, text, html, to=[recipient], sent_by=u["email"])
        store.remember_recipients(u["id"], [recipient])
        return JSONResponse({"status": "sent", **res})
    except emailer.EmailNotConfigured as e:
        return JSONResponse({"status": "not_configured", "detail": str(e)})
    except emailer.EmailRecipientNotAllowed as e:
        return JSONResponse({"status": "recipient_not_allowed", "detail": str(e)})
    except emailer.EmailError as e:
        return JSONResponse({"status": "error", "detail": str(e)})


def main() -> None:
    import uvicorn

    host = os.getenv("AEGIS_HOST", "127.0.0.1")
    port = int(os.getenv("AEGIS_PORT", "8000"))
    print(f"  AEGIS platform → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
