"""
Aegis — jobs workflow.

A SECOND multi-agent workflow that mirrors the incident side exactly: typed
contracts (jobs/contracts.py), role agents (jobs/agents.py), and an orchestrator
(jobs/orchestrator.py) that posts every step through the SAME AgentBus
(backend.bus) using the SAME RoomMessage envelope (backend.contracts). The only
new vocabulary is the job intents added to backend.contracts.Intent.

    observer  -> parse criteria/resume into a search profile
    validator -> find CURRENT real postings (Adzuna) + score fit vs the resume
    commander -> present ranked matches, gate on a human
    tailor    -> rewrite the resume to a chosen posting (md + PDF + DOCX)
    applier   -> submit where a real apply method exists, else queue — honestly
"""
