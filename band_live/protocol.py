"""
band_live — the tiny structured protocol the five live agents speak, plus env
helpers. Identity/credentials are per-agent, exactly like BandBus.

A handoff message is a normal Band chat message: a human-readable sentence (which
shows in the chat) followed by a fenced ```aegis-neg JSON block carrying the
``intent`` (what just happened) and an accumulating ``ctx`` (the typed payloads —
signal, hypothesis, remediation, validation — so each agent can rebuild exactly
what it needs). We use a DISTINCT fence (``aegis-neg``) from BandBus's ``aegis``
block so the two paths never confuse each other if they ever share a room.
"""
from __future__ import annotations

import json
import os
import re

_FENCE = "aegis-neg"
# Band renders an @mention in stored content as a chip token like @[[<uuid>]].
_CHIP = re.compile(r"@\[\[[0-9a-fA-F-]+\]\]\s*")
_OPEN = f"\n\n```{_FENCE}\n"
_CLOSE = "\n```"

# The five core agent handles, in cascade order.
AGENTS = ("observer", "diagnostician", "remediator", "validator", "commander")
# The 6th agent — a security specialist that is NOT pre-added to the chat; the
# commander RECRUITS it at runtime via Band's participant tools.
SECURITY = "security"
# Everyone the runner launches as a live listener (security included — it connects
# but only joins the room once recruited).
ALL_LISTENERS = AGENTS + (SECURITY,)


# --------------------------------------------------------------------------- #
# Message marker
# --------------------------------------------------------------------------- #
def encode(text: str, payload: dict) -> str:
    """Human sentence first (what shows in Band), structured marker appended."""
    return f"{text}{_OPEN}{json.dumps(payload)}{_CLOSE}"


def decode(content: str | None) -> dict | None:
    """Pull the structured payload back out of a message, or None if absent."""
    marker = f"```{_FENCE}"
    if not content or marker not in content:
        return None
    try:
        after = content.split(marker, 1)[1]
        body = after.split("```", 1)[0].strip()
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except (ValueError, IndexError, json.JSONDecodeError):
        return None


def visible(content: str | None) -> str:
    """Just the human-readable line (structured marker + mention chips stripped)."""
    marker = f"```{_FENCE}"
    text = (content or "").split(marker, 1)[0]
    return _CHIP.sub("", text).strip()


# --------------------------------------------------------------------------- #
# Env (per-agent identity) — mirrors backend/bus.BandBus
# --------------------------------------------------------------------------- #
def _req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"band_live: env {name} is required (set it in backend/.env).")
    return val


def chat_id() -> str:
    return _req("BAND_CHAT_ID")


def rest_url() -> str:
    # BandLink/Agent default to app.band.ai (RestClient alone defaults to the dev host).
    return os.getenv("BAND_REST_URL", "https://app.band.ai")


def ws_url() -> str:
    return os.getenv("BAND_WS_URL", "wss://app.band.ai/api/v1/socket/websocket")


def agent_id(handle: str) -> str:
    return _req(f"BAND_{handle.upper()}_ID")


def agent_key(handle: str) -> str:
    return _req(f"BAND_{handle.upper()}_KEY")


def human_id() -> str | None:
    """Band id of the human participant (so @commander can ping them). Optional."""
    return os.getenv("BAND_HUMAN_ID")


def human_key() -> str | None:
    """API key for the human participant. If set, the runner can post the trigger
    and the 'approve' AS the human; if not, a real person types them in Band."""
    return os.getenv("BAND_HUMAN_KEY")


def missing_env() -> list[str]:
    """Which required vars are unset (so the runner can fail loud, never fake)."""
    need = ["BAND_CHAT_ID"]
    for h in ALL_LISTENERS:          # includes BAND_SECURITY_ID / BAND_SECURITY_KEY
        need += [f"BAND_{h.upper()}_ID", f"BAND_{h.upper()}_KEY"]
    return [n for n in need if not os.getenv(n)]
