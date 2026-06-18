"""
Aegis — band_live: all 5 agents as REAL Band remote agents that collaborate
THROUGH Band, reacting to each other's @mentions over the Phoenix-Channels
WebSocket — no orchestrator scripting the order.

This is the strongest answer to "is Band actually the coordination layer?"
The reliable `BandBus` path (`backend/bus.py`) has our orchestrator drive a
scripted cascade and post each step into Band — kept as-is, the fallback. Here
instead, each of the five agents is an **independent Band listener** with its own
identity; the whole incident — including reject→revise→PASS and the human
approval gate — emerges purely from real @mention handoffs.

    reactive  -> ReactiveAgent base: band.Agent + a dispatch SimpleAdapter whose
                 on_message fires only on this agent's @mentions (over the WS)
    cascade   -> the deterministic handlers, reusing backend roster + chaos replay
                 + cost/postmortem (no LLM). Includes DYNAMIC RECRUITMENT: when the
                 validated fix is irreversible, the commander discovers + adds a 6th
                 agent (@security, not pre-added) to the room via Band's participant
                 tools (lookup_peers + add_participant) for a risk sign-off.
    protocol  -> the structured @mention marker (intent + accumulating ctx) + env
    runner    -> launches all 6 concurrently, seeds ONE trigger @observer, shows it

Run:  python -m band_live      (needs BAND_* creds in backend/.env)
Set BAND_HUMAN_KEY to auto-post the human 'approve'; otherwise a real person types
`approve @commander` in the Band chat.

The offline/orchestrator/BandBus paths are untouched and remain the fallback.
"""
