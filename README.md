# Aegis — the autonomous on-call engineer that never sleeps

A multi-agent incident-response war room on **Band**. When production breaks, five
specialist agents converge in one Band room, find the root cause, **prove** a fix
against a chaos replay, take one human approval, fail over, and auto-write the
postmortem — collapsing MTTR from ~42 minutes to ~1.5.

**The problem.** On-call is the worst seat in engineering: a 3am page, a scramble
to assemble a war room, ~42 minutes of mean-time-to-resolve while revenue bleeds
and one person guesses under pressure. Aegis runs that war room autonomously —
five agents that argue from evidence — and asks a human for exactly one thing: the
go/no-go on the single irreversible action.

📺 **Landing page + demo video:** open `frontend/static/landing.html` directly, or
hit **`GET /landing`** on the running server (`python -m frontend.server`).

Built for the **Band of Agents Hackathon** (lablab.ai). Fuses four of the "23
projects that get you hired": log/metric **anomaly detection** (#13),
**chaos testing** (#14), **multi-region failover** (#15), and **cloud cost**
quantification (#16) — plus text-to-SQL telemetry (#08) and tool-use + memory (#06).

## Run it now (zero keys, deterministic)

```bash
pip install pydantic
python -m backend.run        # from the aegis/ directory
```

You'll see the Band-room transcript:

```
@observer      detects a SEV1, correlates it to deploy v2.3.1, opens the room
@diagnostician root cause: memory leak from the deploy (text-to-SQL evidence)
@remediator    fix #1: "scale 6 -> 12 pods"
@validator     chaos replay -> REJECTED (leak is unbounded, still breaches SLO)
@remediator    fix #2: "rollback v2.3.1 + failover to us-west-2"
@validator     chaos replay -> PASSED (p99 308ms, 0% errors, within SLO)
@commander     irreversible -> asks @human -> approved -> executes -> RESOLVED
@commander     auto-postmortem: MTTR 89s, ~$38k downtime averted
```

## Why this shape wins

- **The reject-then-fix beat is the money shot.** `@validator` *disproves*
  `@remediator`'s first fix with evidence it generated itself (a chaos replay),
  forcing a revision. One agent challenging another's claim mid-incident is the
  thing a Slack webhook physically cannot do — it's the proof Band is the real
  coordination layer, not a notification channel.
- **Adversarial across roles, not a linear pipeline.** Most teams ship
  planner→executor. The skeptical validator with a veto is rarer and harder to fake.
- **The reject is computed, not scripted.** `scale_pods` fails because the chaos
  model shows the leak saturates regardless of pod count; `rollback_and_failover`
  passes because the model shows it doesn't. Change the scenario and the verdict changes.
- **Business value in one number:** ~$38k downtime averted, MTTR 42 min -> 1.5 min.

## Architecture

```
            ┌──────────────────────  BAND ROOM  ──────────────────────┐
 telemetry  │  @observer ─signal→ @diagnostician ─hypothesis→          │
 ──────────►│        @remediator ⇄ @validator   (reject / pass loop)   │
            │                         │ pass                           │
            │                    @commander ─approval→ @human          │
            │                         │ execute → RESOLVED → postmortem │
            └─────────────────────────────────────────────────────────┘

every arrow is a RoomMessage on the AgentBus  →  LocalBus offline, BandBus live (BUS=band)
```

Provider split (scores "collaborate across frameworks" + targets BOTH partner prizes):

| agent          | framework    | provider     |
|----------------|--------------|--------------|
| @observer      | LangGraph    | AI/ML API    |
| @diagnostician | CrewAI       | Featherless  |
| @remediator    | LangGraph    | AI/ML API    |
| @validator     | CrewAI       | Featherless  |
| @commander     | orchestrator | AI/ML API    |

## Files

```
backend/
  contracts.py      typed message schema (the room's shared language)
  bus.py            AgentBus + LocalBus (offline) + BandBus (live Band room)
  llm.py            OfflineLLM (zero keys) + AI/ML API + Featherless clients
  mockservice.py    fault-injectable service + the chaos-replay simulator
  detector.py       z-score anomaly detection over a rolling baseline (#13)
  agents/roster.py  the five agents
  orchestrator.py   drives the reject-then-fix cascade through the bus
  run.py            colored transcript + verdict
```

## The Aegis Platform (web dashboard + a second workflow)

The CLI demo above is one slice. The full platform wraps the **same** AgentBus
pattern in a web app with two agent workflows and real integrations.

```bash
pip install -r backend/requirements.txt   # pydantic, fastapi, uvicorn, httpx,
                                           # pdfplumber, python-docx, reportlab
python -m frontend.server                  # → http://127.0.0.1:8000
```

Zero keys still boots: the incident **demo** mode and the whole UI run offline.
Real integrations (email send, Adzuna job search, resume parsing) activate when
their keys are set — and **fail with a clear message if a key is missing**,
never a fake success. Copy `backend/.env.example` → `backend/.env` to enable them.

### Dashboard
Landing page: summary cards (open incidents, avg MTTR, total cost averted,
incidents resolved 7d, jobs found, applications sent, resumes tailored), a
newest-first activity feed across both workflows, a connected-services health
row (email · job API · Featherless · AI/ML · Band), and quick actions.

### Resolve — incidents, made real
Upload a metrics/log file (JSON/CSV/plain log), paste an artifact, or describe a
service — `backend/ingest.py` parses it into the telemetry shape the detector
expects, and the **same** observer→diagnostician→remediator→validator→commander
pipeline runs on your real data. The commander **pauses in the UI** for human
Approve/Reject before any irreversible action. On resolution an incident report
is **emailed** (`backend/email.py`: Resend primary, SMTP fallback). Every run is
persisted to SQLite.

### Jobs — a second multi-agent workflow (`jobs/`)
Mirrors the incident package (`contracts.py` · `agents.py` · `orchestrator.py`),
posting over the same bus. Three entry modes: **by company**, **by field** (15
roles + free text), or **resume upload** (PDF/DOCX → structured profile via
pdfplumber/python-docx + LLM). Agents: `@observer` builds a search profile,
`@validator` pulls **current real postings** (Adzuna, `jobs/providers.py`) and
scores fit vs the resume, `@commander` gates on your pick, `@tailor` rewrites the
resume to the posting (downloadable **md + PDF + DOCX**), `@applier` **submits**
where a real apply method exists or **queues** with a one-click link otherwise —
and is honest about which (never reports "applied" without a real action).

### History + downloads
Every incident and job run, filterable by type, newest first. Each opens a
detailed report (incidents: timeline, diagnosis, validation, fix, cost; jobs:
profile, ranked matches, tailoring, applications). Download any report as
**Markdown or PDF** (`backend/reporting.py`).

### Analytics · Integrations · Settings
**Analytics:** MTTR trend, cumulative cost averted, incident outcomes, and the
application funnel. **Integrations:** per-service config status + a live **Test**
button each. **Settings:** key status (values never echoed), incident-report
recipients, and a default job field. Persistence is stdlib `sqlite3` at
`data/aegis.db`.

### Channels — multi-platform interface (`channels/`)
Deliver incidents/jobs to, and act on them from, external platforms. Every
channel declares its **real** capabilities (`notify · approve · converse · post ·
job_search · job_apply`) so the UI/agents only offer what actually works — and we
never report an action that didn't happen.

- **Telegram** — full loop: send + inline **Approve/Reject** buttons; a
  `getUpdates` long-poll (no public URL needed) feeds the press straight into the
  commander's HITL gate.
- **Discord** — notify + post (webhook or bot); interactive buttons need a
  gateway, so approval degrades honestly to a deep link.
- **WhatsApp** (Twilio) — notify; reply-approval via a public webhook
  (`/api/channels/whatsapp/inbound`).
- **LinkedIn** — share/draft **only**; job search & auto-apply are intentionally
  unsupported (LinkedIn's API forbids them) — we hand you the package + apply URL.

Incident approvals fan out to enabled channels and resolve from whichever
responds first (browser **or** channel). Job runs push an alert + an
approve-then-share post draft. Each channel shows status + a **Send test** button
on the Integrations page. Any channel without a token stays disabled with a clear
message — never faked. Keys: see the "Channels" block in `.env.example`.

### Accounts & per-user behavior (Phase 7)
Sign in / sign up lives on the landing page (email + password). Auth is
**demo-grade, not production-hardened** — but it's honest: passwords are
**pbkdf2-hashed** in SQLite (stdlib, never plaintext), sessions are random tokens
in an **httpOnly cookie** with an expiry, signup rejects duplicates ("account
exists — sign in") and passwords under 8 chars. Unauthenticated requests are
redirected to the landing page (app routes) or get `401` (API). Incidents, jobs,
and history are **scoped to the signed-in user**. *(No rate-limiting, email
verification, password reset, or CSRF tokens — add those before any real use.)*

Email is **per-user and never silent**:
- We never send **as** your mailbox. Envelope From stays the verified `EMAIL_FROM`;
  **Reply-To** = your account email, with a "sent by &lt;you&gt;" line in the body.
- Sending an incident report **prompts for a recipient** (prefilled with your
  email, editable, remembers recent ones) and requires a **confirm click**.
- **Rebuild resume for a company** (Jobs → *Rebuild → email*): upload or reuse your
  parsed resume + a target company/role; the tailor agent rewrites it (**md + PDF +
  DOCX**) and **emails it to you** with the files **attached**. The tailor **never
  fabricates** — it reorders/re-emphasizes your *real* experience and surfaces
  missing posting keywords as a separate **"gaps to consider"** note.
- If email isn't configured you still get the files to **download** — no crash. On
  Resend's free tier (no verified domain) non-verified recipients are flagged
  clearly ("use SMTP or verify a domain"), never failed silently.

### New platform files
```
backend/auth.py        demo-grade auth — pbkdf2 hashing + session tokens (stdlib)
backend/store.py       SQLite persistence (incidents, jobs, settings, users, sessions)
backend/ingest.py      parse uploaded telemetry → detector timeline
backend/email.py       incident-report email (Resend + SMTP), fail-loud
backend/reporting.py   run → Markdown/PDF reports
backend/health.py      connected-service status + live test checks
jobs/contracts.py      job-workflow typed payloads
jobs/providers.py      JobSearchProvider interface + Adzuna implementation
jobs/resume.py         PDF/DOCX resume → structured profile
jobs/agents.py         observer · validator · commander · tailor · applier
jobs/orchestrator.py   drives the job workflow over the bus
channels/base.py       Channel abstraction (send / on_command / capabilities)
channels/registry.py   loads channels from .env, status + fan-out helpers
channels/{telegram,discord,whatsapp,linkedin}.py   the 4 channels
frontend/server.py     platform API (dashboard, resolve, jobs, history, channels, …)
frontend/static/       offline-first React+htm SPA (vendored, no CDN)
```

## Live agents on Band — `band_live` (the strongest "Band is the coordination layer" proof)

`BandBus` (above) has our deterministic orchestrator post each step into Band.
**`band_live/` goes further**: all **five** agents become *independent Band remote
agents* — built on the band-sdk **adapter model** (`band.Agent.create` +
`SimpleAdapter`) — that each run their own listener loop, subscribe to the shared
chat over Phoenix-Channels, and **react only to their own @mentions through Band**.
Nothing scripts the order: each agent decides its next move from the message it
receives and hands off with `tools.send_message(..., mentions=[…])`.

```bash
python -m band_live          # needs the BAND_* creds in backend/.env
```

The runner launches all five, seeds ONE monitoring trigger (@observer), then the
entire incident — including the reject-then-fix loop **and the human approval
gate** — emerges purely from real @mention handoffs **inside Band**:

```
🚨 monitoring     SEV1 alert fired on checkout-api/us-east-1            → @observer
🛰  observer       SEV1 signal (z-score anomaly, post-deploy v2.3.1)     → @diagnostician
🩺 diagnostician  hypothesis: memory leak from deploy v2.3.1            → @remediator
🛠  remediator    proposal #1: scale 6 → 12 pods                        → @validator
🚫 validator      REJECT — chaos replay p99 8000ms, still breaches SLO  → @remediator
🛠  remediator    proposal #2: roll back v2.3.1 + failover us-west-2    → @validator
✅ validator      PASS — chaos replay p99 308ms, within SLO            → @commander
🛡  commander      irreversible → RECRUITS @security into the room       → @security
🛡  security       risk sign-off: LOW (rollback removes root cause)      → @commander
⏸  commander      approval request (citing @security sign-off)          → @human
🧑 human          approve @commander                                    → @commander
⚡ commander      executed · MTTR 89s · ~$38k averted                   → postmortem
```

**Dynamic recruitment (Originality):** `@security` is **not** a participant of the
chat. When the validated fix is irreversible, the commander **discovers and pulls
it in mid-incident** through Band's real participant tools — `tools.lookup_peers()`
(find addable peers, server-filtered to those not in the room) then
`tools.add_participant(<security id>)`. The band-sdk runtime delivers a `room_added`
event to the security agent, which subscribes, runs a deterministic risk check, and
posts its sign-off `@commander` — a new collaborator joining a live incident, which
a fixed pipeline can't do. Register it via `BAND_SECURITY_ID`/`BAND_SECURITY_KEY`.

Every decision is **real, not faked**: each agent reuses the backend roster
(`backend/agents/roster.py`) for its content/cost, and the validator runs
`backend/mockservice.simulate_remediation` (the same chaos replay the offline
cascade uses) — deterministic, **no LLM required**. The band-sdk runtime handles
subscription, per-agent `/next` message routing, and skipping each agent's own
messages (no self-loop). The **human approve** is a genuine gate: set
`BAND_HUMAN_KEY` to auto-post it as the human, or a real person types
`approve @commander` in the chat. The offline/orchestrator/`BandBus` paths are
untouched and remain the reliable fallback.

```
band_live/protocol.py  structured @mention marker (intent + accumulating ctx) + env
band_live/reactive.py  ReactiveAgent base (band.Agent + dispatch SimpleAdapter)
band_live/cascade.py   the 6 deterministic handlers + dynamic @security recruitment
band_live/runner.py    launch all 5, seed the trigger, drive approve, show transcript
```

## Going live (point it at your own Band + providers)

The offline run needs zero keys. To run the **same code** live, copy
`backend/.env.example` → `backend/.env` and fill in:

1. **Band** (already implemented) — register 5 remote agents, add all 5 to ONE
   shared chat, set each `BAND_<AGENT>_ID`/`_KEY` + `BAND_CHAT_ID`, then `BUS=band`.
   `BandBus.post`/`history` drive and read back the cascade in a real Band room
   (BandBus's own inbound `subscribe` is stubbed — the orchestrator drives the room
   deterministically; the genuine Phoenix-Channels *receive* path is exercised by
   the live agents in [`band_live`](#live-agents-on-band--band_live-the-strongest-band-is-the-coordination-layer-proof)).
2. **Featherless / AI/ML API** — paste keys, confirm each `BASE_URL`/`MODEL`
   against the provider setup guide, set `LLM_MODE=aiml`. OfflineLLM phrasing is
   replaced by real model output; the logic is unchanged.
3. Run `LLM_MODE=aiml BUS=band python -m backend.run` — same code, now live in Band.

## 3-minute demo script

1. (0:00) "It's 3am. checkout-api in us-east just started failing." Run it.
2. (0:30) Point at the **rejection**: "Watch — the first fix gets shot down by a
   peer agent's chaos replay. That argument is happening *inside Band*."
3. (1:30) The revised fix passes, the commander gates on a human, executes.
4. (2:15) The verdict: MTTR 42min → 1.5min, $38k averted, auto-postmortem filed.
5. (2:45) "Five agents, two frameworks, two model providers, one Band room."
```
