"""
Aegis — connected-services health.

Reports whether each external integration is *configured* (a key/host is
present in the environment). It deliberately reveals only booleans and provider
names — never the secret values themselves. Phase 5's Integrations section adds
live "test" buttons on top of this; the dashboard health row uses the cheap
config check so it never blocks on a network round-trip.
"""
from __future__ import annotations

import os


def _email_status() -> dict:
    if os.getenv("RESEND_API_KEY"):
        return {"ok": True, "mode": "resend", "detail": "Resend API configured"}
    if os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"):
        return {"ok": True, "mode": "smtp", "detail": f"SMTP via {os.getenv('SMTP_HOST')}"}
    return {"ok": False, "mode": "none", "detail": "No RESEND_API_KEY or SMTP_* set"}


def _job_api_status() -> dict:
    if os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"):
        return {"ok": True, "mode": "adzuna", "detail": "Adzuna app id + key configured"}
    return {"ok": False, "mode": "none", "detail": "ADZUNA_APP_ID / ADZUNA_APP_KEY not set"}


def _key_status(env_var: str, label: str) -> dict:
    if os.getenv(env_var):
        return {"ok": True, "mode": "configured", "detail": f"{label} key configured"}
    return {"ok": False, "mode": "none", "detail": f"{env_var} not set"}


def _band_status() -> dict:
    bus = os.getenv("BUS", "local").lower()
    if bus == "band" and os.getenv("BAND_API_KEY"):
        return {"ok": True, "mode": "band", "detail": "BandBus selected (wire at kickoff)"}
    return {"ok": True, "mode": "local", "detail": "LocalBus (in-process room)"}


def service_status() -> list[dict]:
    """One row per connected service for the dashboard health strip."""
    return [
        {"key": "email",       "label": "Email",        **_email_status()},
        {"key": "job_api",     "label": "Job API",      **_job_api_status()},
        {"key": "featherless", "label": "Featherless",  **_key_status("FEATHERLESS_API_KEY", "Featherless")},
        {"key": "aiml",        "label": "AI/ML API",    **_key_status("AIML_API_KEY", "AI/ML API")},
        {"key": "band",        "label": "Band",         **_band_status()},
    ]


# --------------------------------------------------------------------------- #
# Live "test" checks (Phase 5 Integrations buttons). Reachability, not config.
# --------------------------------------------------------------------------- #
def _test_openai_compatible(base_env: str, key_env: str, default_base: str) -> dict:
    if not os.getenv(key_env):
        return {"ok": False, "detail": f"{key_env} not set."}
    import httpx
    base = os.getenv(base_env, default_base).rstrip("/")
    try:
        r = httpx.get(f"{base}/models",
                      headers={"Authorization": f"Bearer {os.environ[key_env]}"}, timeout=15.0)
        if r.status_code < 400:
            return {"ok": True, "detail": f"{base}/models reachable ({r.status_code})."}
        return {"ok": False, "detail": f"{base} returned {r.status_code}."}
    except Exception as e:
        return {"ok": False, "detail": f"request failed: {e}"}


def test_service(key: str) -> dict:
    """Run a live reachability check for one service. Never echoes secrets."""
    if key == "email":
        if os.getenv("RESEND_API_KEY"):
            import httpx
            try:
                r = httpx.get("https://api.resend.com/domains",
                              headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"}, timeout=15.0)
                return {"ok": r.status_code < 400, "detail": f"Resend API responded {r.status_code}."}
            except Exception as e:
                return {"ok": False, "detail": f"Resend request failed: {e}"}
        if os.getenv("SMTP_HOST"):
            import smtplib, ssl
            try:
                with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=15) as s:
                    s.starttls(context=ssl.create_default_context())
                    s.login(os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASS", ""))
                return {"ok": True, "detail": f"SMTP login to {os.environ['SMTP_HOST']} OK."}
            except Exception as e:
                return {"ok": False, "detail": f"SMTP failed: {e}"}
        return {"ok": False, "detail": "Email not configured."}

    if key == "job_api":
        from jobs.providers import ProviderError, ProviderNotConfigured, make_provider
        try:
            n = len(make_provider().search(what="engineer", limit=1))
            return {"ok": True, "detail": f"Adzuna reachable — sample query returned {n} result(s)."}
        except ProviderNotConfigured as e:
            return {"ok": False, "detail": str(e)}
        except ProviderError as e:
            return {"ok": False, "detail": str(e)}

    if key == "featherless":
        return _test_openai_compatible("FEATHERLESS_BASE_URL", "FEATHERLESS_API_KEY", "https://api.featherless.ai/v1")
    if key == "aiml":
        return _test_openai_compatible("AIML_BASE_URL", "AIML_API_KEY", "https://api.aimlapi.com/v1")
    if key == "band":
        return {"ok": True, "detail": _band_status()["detail"]}
    return {"ok": False, "detail": f"Unknown service '{key}'."}
