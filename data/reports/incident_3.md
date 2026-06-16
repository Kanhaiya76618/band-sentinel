# Incident report — incident-3

- **Service:** checkout-api / us-east-1
- **Severity:** SEV1
- **Status:** ESCALATED TO HUMAN
- **When:** 2026-06-16 08:41 UTC
- **Source:** demo

## Diagnosis
n/a

## Resolution
- **Action:** n/a
- **Approved by:** None

## Cost & MTTR
- **MTTR:** 0.0 min (0s)
- **Agent latency:** 0.0 ms
- **Downtime cost:** $0
- **Remediation cost:** $0
- **Cost averted:** $0

## War-room transcript
- **@observer** [signal]: SEV1 on checkout-api/us-east-1. p99_ms z=578.5 (=4110.0 vs baseline 229.0), error_rate z=487.0 (=0.2038 vs baseline 0.0), mem_util z=17.6 (=0.695 vs baseline 0.4). Anomaly began right after deploy v2.3.1. Opening the room — @diagnostician, root cause?
- **@diagnostician** [hypothesis]: Root cause: Memory leak introduced by deploy v2.3.1 (conf 86%). p99 tracks memory, not traffic — classic leak. @remediator, propose a fix.
- **@remediator** [remediation_proposal]: First pass: scale 6 -> 12 pods to absorb the load. @validator, replay it before we touch prod.
- **@validator** [validation_result]: REJECTED. Replay shows p99 8000.0ms / errors 12.78% — still breaching. Leak is unbounded: memory keeps climbing, GC pauses recur regardless of pod count. @remediator, this won't hold.
- **@remediator** [remediation_proposal]: Revised: roll back v2.3.1 AND fail traffic to us-west-2. Kills the leak at source. @validator, re-run.
- **@validator** [validation_result]: Chaos replay PASSED: p99 307.7ms, errors 0.00%, within SLO. @commander, safe to execute with approval.
- **@commander** [approval_request]: Validator cleared `rollback_and_failover`, but it's irreversible (failover). @human approve? [y/N]