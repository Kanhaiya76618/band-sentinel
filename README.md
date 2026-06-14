# Aegis — the autonomous on-call engineer that never sleeps

A multi-agent incident-response war room on **Band**. When production breaks, five
specialist agents converge in one Band room, find the root cause, **prove** a fix
against a chaos replay, take one human approval, fail over, and auto-write the
postmortem — collapsing MTTR from ~42 minutes to ~1.5.

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

every arrow is a RoomMessage on the AgentBus  →  LocalBus now, BandBus at kickoff
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
  bus.py            AgentBus + LocalBus (now) + BandBus stub (kickoff swap)
  llm.py            OfflineLLM (zero keys) + AI/ML API + Featherless clients
  mockservice.py    fault-injectable service + the chaos-replay simulator
  detector.py       z-score anomaly detection over a rolling baseline (#13)
  agents/roster.py  the five agents
  orchestrator.py   drives the reject-then-fix cascade through the bus
  run.py            colored transcript + verdict
```

## Going live at kickoff (3 swaps)

1. **Featherless / AI/ML API** — copy `.env.example` to `.env`, paste keys,
   confirm each `BASE_URL`/`MODEL` against the provider setup guide, set
   `LLM_MODE=aiml`. The OfflineLLM phrasing is replaced by real model output;
   logic is unchanged.
2. **Band** — fill the three `TODO`s in `BandBus` (post / subscribe / history)
   from the Band Agent API docs, set `BUS=band` and `BAND_*` env vars.
3. Run `LLM_MODE=aiml BUS=band python -m backend.run`. Same code, now live in Band.

## 3-minute demo script

1. (0:00) "It's 3am. checkout-api in us-east just started failing." Run it.
2. (0:30) Point at the **rejection**: "Watch — the first fix gets shot down by a
   peer agent's chaos replay. That argument is happening *inside Band*."
3. (1:30) The revised fix passes, the commander gates on a human, executes.
4. (2:15) The verdict: MTTR 42min → 1.5min, $38k averted, auto-postmortem filed.
5. (2:45) "Five agents, two frameworks, two model providers, one Band room."
```
