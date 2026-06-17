"""
Aegis — incident-report email (Phase 2).

Two real send paths, chosen by what's configured (never a fake "sent"):

    1. Resend API   — used when RESEND_API_KEY is set (the primary path).
    2. SMTP         — fallback when SMTP_HOST + SMTP_USER + SMTP_PASS are set.

If NEITHER is configured we raise ``EmailNotConfigured`` with a clear message
listing exactly which env vars to set. Callers surface that honestly rather
than pretending the report went out.

Recipients: ``EMAIL_TO`` (comma-separated) unless an explicit list is passed.
Sender: ``EMAIL_FROM``. Nothing here ever prints a key.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Optional


class EmailNotConfigured(RuntimeError):
    """No Resend key and no SMTP credentials present."""


class EmailError(RuntimeError):
    """A configured provider was reached but the send failed."""


class EmailRecipientNotAllowed(EmailError):
    """Recipient rejected by the only available provider (Resend free tier)."""


def _recipients(to: Optional[list[str]]) -> list[str]:
    if to:
        return to
    raw = os.getenv("EMAIL_TO", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def _resend_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY"))


def is_configured() -> bool:
    return _resend_configured() or _smtp_configured()


def _addr(value: str) -> str:
    """Bare lowercase address from a 'Name <a@b>' or 'a@b' string."""
    return parseaddr(value or "")[1].strip().lower()


def resend_verified_addresses() -> set[str]:
    """
    Addresses Resend's FREE tier (no verified domain) is allowed to send to:
    the account's own verified email. We read it from RESEND_VERIFIED_EMAIL and
    also treat EMAIL_FROM's address as verified (you must verify it to send from
    it). Empty => we don't know, so we don't block.
    """
    out = {_addr(os.getenv("RESEND_VERIFIED_EMAIL", "")), _addr(os.getenv("EMAIL_FROM", ""))}
    return {a for a in out if a}


def recipient_block_reason(recipients: list[str]) -> Optional[str]:
    """
    If the ONLY way out is Resend free-tier, return a clear message when a
    recipient isn't the verified address; else None. SMTP (Gmail) or a Resend
    verified domain can reach anyone, so this only fires when SMTP is absent.
    """
    if _smtp_configured() or not _resend_configured():
        return None
    verified = resend_verified_addresses()
    if not verified:
        return None  # unknown verified address (likely a verified domain) — allow
    blocked = [r for r in recipients if _addr(r) not in verified]
    if not blocked:
        return None
    vlist = ", ".join(sorted(verified))
    return (f"Resend free tier only sends to your verified email ({vlist}) — "
            f"can't reach {', '.join(blocked)}. Use SMTP or verify a domain to send elsewhere.")


def _normalize_attachments(attachments: Optional[list[dict]]) -> list[tuple[str, bytes, str, str]]:
    """Each item: {'filename', 'path'} or {'filename', 'data': bytes}.
    Returns (filename, data_bytes, maintype, subtype)."""
    out: list[tuple[str, bytes, str, str]] = []
    for a in attachments or []:
        data = a.get("data")
        if data is None and a.get("path"):
            data = Path(a["path"]).read_bytes()
        if data is None:
            continue
        name = a.get("filename") or (Path(a["path"]).name if a.get("path") else "attachment")
        ctype, _ = mimetypes.guess_type(name)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        out.append((name, data, maintype, subtype or "octet-stream"))
    return out


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def build_incident_report(run: dict) -> tuple[str, str, str]:
    """Return (subject, plain_text, html) for a persisted/finished incident run."""
    v = run.get("verdict") or {}
    pm = run.get("postmortem") or {}
    service = run.get("service") or "service"
    region = run.get("region") or "—"
    resolved = bool(v.get("resolved"))
    inc_id = pm.get("incident_id") or run.get("incident_id") or "INCIDENT"

    subject = f"[Aegis] {inc_id} — {service}/{region} {'RESOLVED' if resolved else 'ESCALATED'}"

    mttr = v.get("mttr_seconds") or pm.get("mttr_seconds") or 0
    lines = [
        f"Incident: {inc_id} — {pm.get('title', service)}",
        f"Severity: {run.get('severity', 'SEV1')}",
        f"Status:   {'RESOLVED' if resolved else 'ESCALATED TO HUMAN'}",
        "",
        f"Root cause: {pm.get('root_cause', 'n/a')}",
        f"Resolution: {pm.get('resolution', v.get('action', 'n/a'))}",
        f"Approved by: {v.get('approved_by', 'n/a')}",
        "",
        f"MTTR: {mttr/60:.1f} min ({mttr:.0f}s)",
        f"Downtime cost: ${v.get('downtime_cost_usd', 0):,.0f}",
        f"Remediation cost: ${v.get('remediation_cost_usd', 0):,.0f}",
        f"Cost averted vs manual: ${v.get('averted_cost_usd', 0):,.0f}",
        "",
        "Cost summary: " + (pm.get("cost_summary", "n/a")),
        "",
        "Follow-ups:",
    ]
    for f in pm.get("follow_ups", []) or ["(none recorded)"]:
        lines.append(f"  - {f}")
    if pm.get("timeline"):
        lines += ["", "Timeline:"]
        lines += [f"  {t}" for t in pm["timeline"]]
    text = "\n".join(lines)

    fu_html = "".join(f"<li>{f}</li>" for f in (pm.get("follow_ups") or []))
    tl_html = "".join(f"<li>{t}</li>" for t in (pm.get("timeline") or []))
    html = f"""\
<div style="font-family:ui-monospace,Menlo,monospace;max-width:640px;color:#0a0e17">
  <h2 style="margin:0 0 4px">{inc_id} — {service}/{region}</h2>
  <p style="color:{'#0a8a4f' if resolved else '#b4232a'};font-weight:700;margin:0 0 12px">
    {'RESOLVED' if resolved else 'ESCALATED TO HUMAN'}</p>
  <p><b>Root cause:</b> {pm.get('root_cause', 'n/a')}<br>
     <b>Resolution:</b> {pm.get('resolution', v.get('action', 'n/a'))}<br>
     <b>Approved by:</b> {v.get('approved_by', 'n/a')}</p>
  <table cellpadding="6" style="border-collapse:collapse;background:#f4f6fb">
    <tr><td><b>MTTR</b></td><td>{mttr/60:.1f} min</td></tr>
    <tr><td><b>Downtime cost</b></td><td>${v.get('downtime_cost_usd', 0):,.0f}</td></tr>
    <tr><td><b>Remediation cost</b></td><td>${v.get('remediation_cost_usd', 0):,.0f}</td></tr>
    <tr><td><b>Cost averted</b></td><td>${v.get('averted_cost_usd', 0):,.0f}</td></tr>
  </table>
  <h3>Follow-ups</h3><ul>{fu_html or '<li>(none)</li>'}</ul>
  {'<h3>Timeline</h3><ul>' + tl_html + '</ul>' if tl_html else ''}
  <p style="color:#8092ad;font-size:12px">Generated by Aegis.</p>
</div>"""
    return subject, text, html


# --------------------------------------------------------------------------- #
# Send
# --------------------------------------------------------------------------- #
def send_email(
    subject: str,
    text: str,
    html: str,
    to: Optional[list[str]] = None,
    *,
    reply_to: Optional[str] = None,
    sent_by: Optional[str] = None,
    attachments: Optional[list[dict]] = None,
) -> dict:
    """
    Send via SMTP (if configured — can reach anyone) else Resend. Raises if
    nothing is configured, or EmailRecipientNotAllowed when only Resend free-tier
    is available and the recipient isn't the verified address.

    Envelope From is always the configured EMAIL_FROM — we never send *as* the
    user's mailbox. ``sent_by`` sets Reply-To (unless ``reply_to`` overrides) and
    stamps a "Sent by <email> via Aegis" line into the body.
    """
    recipients = _recipients(to)
    sender = os.getenv("EMAIL_FROM")
    if not is_configured():
        raise EmailNotConfigured(
            "Email not configured. Set RESEND_API_KEY (+ EMAIL_FROM/EMAIL_TO) for "
            "the Resend path, or SMTP_HOST/SMTP_USER/SMTP_PASS (+ EMAIL_FROM/EMAIL_TO)."
        )
    if not sender:
        raise EmailNotConfigured("EMAIL_FROM is not set.")
    if not recipients:
        raise EmailNotConfigured("No recipients: set EMAIL_TO or pass an explicit list.")

    reply_to = reply_to or sent_by
    if sent_by:
        text = f"{text}\n\n— Sent by {sent_by} via Aegis."
        html = f"{html}\n<p style=\"color:#8092ad;font-size:12px\">Sent by {sent_by} via Aegis.</p>"

    block = recipient_block_reason(recipients)
    if block:
        raise EmailRecipientNotAllowed(block)

    files = _normalize_attachments(attachments)
    # SMTP can deliver to any recipient; prefer it when present. Otherwise Resend.
    if _smtp_configured():
        return _send_smtp(sender, recipients, subject, text, html, reply_to, files)
    return _send_resend(sender, recipients, subject, text, html, reply_to, files)


def _send_resend(sender, to, subject, text, html, reply_to, files) -> dict:
    import httpx
    payload: dict = {"from": sender, "to": to, "subject": subject, "text": text, "html": html}
    if reply_to:
        payload["reply_to"] = reply_to
    if files:
        payload["attachments"] = [
            {"filename": name, "content": base64.b64encode(data).decode("ascii")}
            for (name, data, _mt, _st) in files
        ]
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
            json=payload, timeout=30.0,
        )
        resp.raise_for_status()
        return {"provider": "resend", "status": "sent", "to": to,
                "attached": [f[0] for f in files], "id": resp.json().get("id")}
    except httpx.HTTPStatusError as e:
        detail = e.response.text or ""
        # Resend free tier rejects non-verified recipients with a 403 — surface it clearly.
        if e.response.status_code == 403 and "verif" in detail.lower():
            raise EmailRecipientNotAllowed(
                "Resend free tier only sends to your verified email — use SMTP or "
                f"verify a domain to send to {', '.join(to)}.") from e
        raise EmailError(f"Resend rejected the send: {e.response.status_code} {detail}") from e
    except httpx.HTTPError as e:
        raise EmailError(f"Resend request failed: {e}") from e


def _send_smtp(sender, to, subject, text, html, reply_to, files) -> dict:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, ", ".join(to), subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for (name, data, maintype, subtype) in files:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            smtp.send_message(msg)
        return {"provider": "smtp", "status": "sent", "to": to, "attached": [f[0] for f in files]}
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"SMTP send failed via {host}:{port}: {e}") from e


def send_incident_report(run: dict, to: Optional[list[str]] = None, **kw) -> dict:
    subject, text, html = build_incident_report(run)
    return send_email(subject, text, html, to, **kw)
