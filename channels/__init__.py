"""
Aegis — channels: the multi-platform interface layer (Phase 6).

A Channel delivers incidents/jobs OUT to an external platform and (where the
platform allows) accepts commands/approvals back IN. Every channel declares its
real ``capabilities`` so the agents/UI only ever offer what actually works in
this runtime — and we never report an action that didn't happen.

    base.py      the Channel abstraction (send / on_command / capabilities)
    registry.py  loads enabled channels from .env, exposes status
    telegram.py  Bot API — FULL loop (send + inline Approve/Reject via long-poll)
    discord.py   webhook/bot — notify + post (inbound buttons need a gateway)
    whatsapp.py  Twilio sandbox — notify (+ inbound approval via webhook)
    linkedin.py  OAuth — share a post / draft only (NO search/apply: API forbids)
"""
