"""
Aegis — report rendering (Phase 4).

Turn a persisted run (incident or job) into a Markdown report, and render that
Markdown to PDF (reportlab). Used by the History section's download buttons.
Reports are written under data/reports/ and served via /api/download.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .store import DATA_DIR

REPORTS = DATA_DIR / "reports"


def _ts(epoch: float | None) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def incident_markdown(run: dict) -> str:
    v = run.get("verdict") or {}
    pm = run.get("postmortem") or {}
    resolved = bool(run.get("resolved"))
    inc = pm.get("incident_id") or run.get("incident_id") or f"incident-{run.get('id')}"
    L = [
        f"# Incident report — {inc}",
        "",
        f"- **Service:** {run.get('service')} / {run.get('region')}",
        f"- **Severity:** {run.get('severity')}",
        f"- **Status:** {'RESOLVED' if resolved else 'ESCALATED TO HUMAN'}",
        f"- **When:** {_ts(run.get('created_at'))}",
        f"- **Source:** {run.get('source')}",
        "",
        "## Diagnosis",
        f"{pm.get('root_cause', 'n/a')}",
        "",
        "## Resolution",
        f"- **Action:** {v.get('action', pm.get('resolution', 'n/a'))}",
        f"- **Approved by:** {v.get('approved_by', run.get('approved_by', 'n/a'))}",
        "",
        "## Cost & MTTR",
        f"- **MTTR:** {(run.get('mttr_seconds') or 0)/60:.1f} min ({run.get('mttr_seconds') or 0:.0f}s)",
        f"- **Agent latency:** {run.get('decision_latency_ms') or 0:.1f} ms",
        f"- **Downtime cost:** ${run.get('downtime_cost_usd') or 0:,.0f}",
        f"- **Remediation cost:** ${run.get('remediation_cost_usd') or 0:,.0f}",
        f"- **Cost averted:** ${run.get('averted_cost_usd') or 0:,.0f}",
    ]
    if pm.get("follow_ups"):
        L += ["", "## Follow-ups"] + [f"- {f}" for f in pm["follow_ups"]]
    if run.get("transcript"):
        L += ["", "## War-room transcript"]
        for m in run["transcript"]:
            L.append(f"- **{m.get('sender')}** [{m.get('intent')}]: {m.get('text')}")
    return "\n".join(L)


def job_markdown(run: dict) -> str:
    prof = run.get("profile") or {}
    matches = run.get("matches") or []
    apps = run.get("applications") or []
    L = [
        f"# Job-search report — {run.get('query')}",
        "",
        f"- **Entry mode:** {run.get('entry_mode')}",
        f"- **When:** {_ts(run.get('created_at'))}",
        f"- **Matches:** {run.get('match_count')} · **Tailored:** {run.get('tailored_count')} · "
        f"**Submitted:** {run.get('applied_count')} · **Queued:** {run.get('queued_count')}",
        "",
        "## Search profile",
        f"- **Titles:** {', '.join(prof.get('titles') or []) or '—'}",
        f"- **Skills:** {', '.join(prof.get('skills') or []) or '—'}",
        f"- **Seniority:** {prof.get('seniority') or '—'}",
        "",
        "## Ranked matches",
    ]
    for m in matches:
        L.append(f"- **{m.get('title')}** @ {m.get('company')} — {round((m.get('fit_score') or 0)*100)}% fit "
                 f"({', '.join(m.get('fit_reasons') or [])}) — {m.get('url')}")
    if apps:
        L += ["", "## Applications"]
        for a in apps:
            L.append(f"- **{a.get('title')}** @ {a.get('company')} — **{a.get('status')}** "
                     f"via {a.get('method')}: {a.get('detail')}")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# PDF (simple Markdown -> flowables)
# --------------------------------------------------------------------------- #
def markdown_to_pdf(md: str, path: Path) -> str:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    flow = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            flow.append(Spacer(1, 5)); continue
        if line.startswith("# "):
            flow.append(Paragraph(line[2:], styles["Title"]))
        elif line.startswith("## "):
            flow.append(Paragraph(line[3:], styles["Heading2"]))
        else:
            safe = (line.lstrip("- ").replace("&", "&amp;").replace("<", "&lt;")
                    .replace("**", ""))
            flow.append(Paragraph(("• " if line.lstrip().startswith("-") else "") + safe, styles["BodyText"]))
    doc.build(flow)
    return str(path)


def build_report(kind: str, run: dict, fmt: str) -> str:
    """Render a run to md|pdf under data/reports/ and return the file path."""
    REPORTS.mkdir(parents=True, exist_ok=True)
    md = incident_markdown(run) if kind == "incident" else job_markdown(run)
    stem = f"{kind}_{run.get('id')}"
    if fmt == "md":
        p = REPORTS / f"{stem}.md"
        p.write_text(md, encoding="utf-8")
        return str(p)
    if fmt == "pdf":
        return markdown_to_pdf(md, REPORTS / f"{stem}.pdf")
    raise ValueError(f"Unsupported format '{fmt}' (use md|pdf).")
