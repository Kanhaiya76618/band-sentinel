"""
Aegis — run the war room.

    python -m backend.run        # offline, zero keys, deterministic demo

At kickoff, flip to live:
    LLM_MODE=aiml BUS=band python -m backend.run   (after wiring BandBus)
"""
from __future__ import annotations

import asyncio

from .orchestrator import run_incident

LANE = {
    "@observer": "\033[96m",       # cyan
    "@diagnostician": "\033[94m",  # blue
    "@remediator": "\033[93m",     # yellow
    "@validator": "\033[91m",      # red
    "@commander": "\033[92m",      # green
}
RESET = "\033[0m"
DIM = "\033[2m"


def main() -> None:
    log, verdict = asyncio.run(run_incident())

    print("\n" + "=" * 74)
    print("  AEGIS // BAND WAR ROOM — INCIDENT INC-2041: checkout-api / us-east-1")
    print("=" * 74 + "\n")

    for m in log:
        c = LANE.get(m.sender, "")
        ment = (" -> " + " ".join(m.mentions)) if m.mentions else ""
        print(f"{c}{m.sender:<15}{RESET}{DIM}[{m.intent.value}]{ment}{RESET}")
        print(f"   {m.text}")
        # surface the most demo-relevant payload lines
        if m.intent.value == "validation_result":
            for line in m.payload.get("trace", []):
                print(f"      {DIM}• {line}{RESET}")
        if m.intent.value == "postmortem":
            print(f"      {DIM}• root cause: {m.payload.get('root_cause')}{RESET}")
            print(f"      {DIM}• {m.payload.get('cost_summary')}{RESET}")
            for f in m.payload.get("follow_ups", []):
                print(f"      {DIM}• follow-up: {f}{RESET}")
        print()

    print("-" * 74)
    print("  VERDICT")
    print("-" * 74)
    if not verdict.get("resolved"):
        print("  Incident NOT auto-resolved — escalated to human.")
        return
    print(f"  Resolved by      : {verdict['action']}")
    print(f"  Approved by      : {verdict['approved_by']}")
    print(f"  Attempts         : {verdict['attempts']} (1 rejected, 1 passed)")
    print(f"  MTTR (modeled)   : {verdict['mttr_seconds']:.0f}s  (~{verdict['mttr_seconds']/60:.1f} min)")
    print(f"  Agent latency    : {verdict['decision_latency_ms']:.1f} ms (real wall-clock)")
    print(f"  Downtime cost    : ${verdict['downtime_cost_usd']:,.0f}")
    print(f"  Remediation cost : ${verdict['remediation_cost_usd']:,.0f}")
    print(f"  Cost AVERTED     : ${verdict['averted_cost_usd']:,.0f}  (vs ~42 min manual MTTR)")
    print()


if __name__ == "__main__":
    main()
