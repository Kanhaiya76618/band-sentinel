"""
Aegis — resume FIT ANALYSIS (read-only).

Given a parsed resume profile + a selected job, return structured, job-specific
improvement SUGGESTIONS the candidate can act on themselves. This module NEVER
rewrites, edits, or stores a modified resume, and NEVER fabricates skills, dates,
employers, or experience — gaps are surfaced as advice ("consider adding X if you
have it"), never invented content.

Two paths, same shape:
  * LLM path (AIMLClient / FeatherlessLLM) with a system prompt enforcing the
    read-only / no-fabrication rules.
  * deterministic rule-based fallback (keyword/gap comparison over SKILL_VOCAB) so
    it still returns useful suggestions when no LLM key is configured.
"""
from __future__ import annotations

import json
import re

from .resume import SKILL_VOCAB

_SYSTEM = (
    "You are a resume coach. You are given a candidate's resume text and ONE job "
    "posting. Return ONLY improvement SUGGESTIONS the candidate can act on. "
    "HARD RULES: (1) READ-ONLY — never rewrite, edit, or output a modified resume. "
    "(2) NEVER fabricate skills, employers, titles, dates, degrees, or metrics. "
    "Gaps are advice ('consider adding X if you genuinely have it'), never invented "
    "content. (3) Keyword suggestions must be terms from the posting the candidate "
    "should surface ONLY if they truly have them. "
    "Reply ONLY with compact JSON: {\"alignment\":\"one sentence\",\"score\":0-100,"
    "\"strengths\":[...],\"gaps\":[...],\"ats_keywords\":[...],\"clarity_tips\":[...],"
    "\"actions\":[...]}."
)


def _kw_in(text: str) -> set[str]:
    low = (text or "").lower()
    return {s for s in SKILL_VOCAB if re.search(r"\b" + re.escape(s) + r"\b", low)}


def _rule_based(profile: dict, job: dict) -> dict:
    """Deterministic keyword/gap comparison — no LLM, no fabrication."""
    jd = f"{job.get('title','')} {job.get('description','')}"
    posting_kw = sorted(_kw_in(jd))
    have = {s.lower() for s in (profile.get("skills") or [])}
    matched = [k for k in posting_kw if k in have]
    gaps = [k for k in posting_kw if k not in have]

    denom = max(1, len(posting_kw))
    score = round(100 * len(matched) / denom)
    title = job.get("title") or "this role"
    company = job.get("company") or "the company"

    if score >= 70:
        align = f"Strong fit for {title} at {company} — most listed skills already appear on your resume."
    elif score >= 40:
        align = f"Partial fit for {title} at {company} — several listed skills appear, with some notable gaps to address."
    else:
        align = f"Stretch fit for {title} at {company} — the posting emphasizes skills your resume doesn't yet surface."

    strengths = ([f"Already shows: {', '.join(matched[:8])}"] if matched
                 else ["No direct keyword overlap detected — lead with your closest transferable experience."])
    gap_advice = [f"Consider surfacing '{g}' if you genuinely have it" for g in gaps[:8]]
    ats = gaps[:8]
    clarity = [
        "Quantify impact (numbers, %, $, scale) on your top 3 bullets.",
        "Open bullets with strong action verbs (built, led, shipped, reduced).",
        "Mirror the posting's exact phrasing for tools/skills you already have (ATS match).",
        f"Put the most {title}-relevant experience in the top third of page one.",
    ]
    actions = []
    if gaps:
        actions.append(f"Add any genuine experience with: {', '.join(gaps[:5])}.")
    if matched:
        actions.append(f"Move {matched[0]} higher and quantify a result tied to it.")
    actions.append("Re-order bullets so the most role-relevant ones come first.")
    actions.append("Add a one-line summary naming the target role and top 3 matching skills.")

    return {"alignment": align, "score": score, "strengths": strengths,
            "gaps": gap_advice, "ats_keywords": ats, "clarity_tips": clarity,
            "actions": actions[:6], "source": "rule-based"}


def _llm_based(profile: dict, job: dict, llm) -> dict | None:
    """Ask the LLM for the same structured suggestions. None on any failure."""
    try:
        user = (
            f"JOB: {job.get('title','')} at {job.get('company','')}\n"
            f"POSTING:\n{(job.get('description') or '')[:2500]}\n\n"
            f"RESUME (read-only — do not rewrite):\n{(profile.get('resume_text') or '')[:4000]}"
        )
        out = llm.complete(system=_SYSTEM, user=user, role="@coach", tag="analyze") or ""
        start, end = out.find("{"), out.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(out[start:end + 1])
        if not isinstance(data, dict) or "alignment" not in data:
            return None
        # Coerce to the expected shape; never trust unbounded LLM output.
        def _list(x):
            return [str(i) for i in (x or [])][:10]
        try:
            score = max(0, min(100, int(data.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        return {"alignment": str(data.get("alignment", ""))[:300], "score": score,
                "strengths": _list(data.get("strengths")), "gaps": _list(data.get("gaps")),
                "ats_keywords": _list(data.get("ats_keywords")),
                "clarity_tips": _list(data.get("clarity_tips")),
                "actions": _list(data.get("actions")), "source": "llm"}
    except Exception:
        return None


def analyze_fit(profile: dict, job: dict, llm=None) -> dict:
    """Read-only fit analysis. LLM when available + valid, else rule-based fallback."""
    result = _llm_based(profile, job, llm) if llm is not None else None
    return result or _rule_based(profile, job)


def summary_text(job: dict, analysis: dict) -> tuple[str, str, str]:
    """(subject, plain_text, html) for optionally emailing the SUGGESTIONS (no
    attachment, no resume file). Read-only summary only."""
    title = job.get("title") or "the role"
    company = job.get("company") or "the company"
    subject = f"Resume suggestions — {title} @ {company}"

    def sec(name, items):
        return f"\n{name}:\n" + ("\n".join(f"  - {i}" for i in items) if items else "  (none)")

    text = (f"Resume fit suggestions for {title} at {company}\n"
            f"Alignment: {analysis.get('alignment','')}  (fit {analysis.get('score',0)}/100)\n"
            + sec("Matched strengths", analysis.get("strengths"))
            + sec("Gaps to consider (only add if you genuinely have them)", analysis.get("gaps"))
            + sec("ATS / keyword suggestions", analysis.get("ats_keywords"))
            + sec("Clarity & impact tips", analysis.get("clarity_tips"))
            + sec("Prioritized actions", analysis.get("actions"))
            + "\n\nThese are suggestions only — your resume was not modified.")

    def ul(items):
        return "<ul>" + "".join(f"<li>{i}</li>" for i in (items or ["(none)"])) + "</ul>"
    html = (f"<div style=\"font-family:ui-monospace,Menlo,monospace;color:#0a0e17\">"
            f"<h2>{title} @ {company}</h2>"
            f"<p><b>Alignment:</b> {analysis.get('alignment','')} (fit {analysis.get('score',0)}/100)</p>"
            f"<h3>Matched strengths</h3>{ul(analysis.get('strengths'))}"
            f"<h3>Gaps to consider</h3>{ul(analysis.get('gaps'))}"
            f"<h3>ATS / keyword suggestions</h3>{ul(analysis.get('ats_keywords'))}"
            f"<h3>Clarity &amp; impact tips</h3>{ul(analysis.get('clarity_tips'))}"
            f"<h3>Prioritized actions</h3>{ul(analysis.get('actions'))}"
            f"<p style=\"color:#8092ad;font-size:12px\">Suggestions only — your resume was not modified.</p></div>")
    return subject, text, html
