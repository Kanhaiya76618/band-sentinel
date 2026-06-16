"""
WhatsApp channel via the Twilio WhatsApp sandbox.

Outbound notify is fully supported (Twilio Messages API). Inbound replies for
approval require Twilio to POST to a *public* webhook
(/api/channels/whatsapp/inbound) — not available on a local-only run — so we
don't claim the `approve` capability; approvals go out with a deep link.

Env: TWILIO_SID, TWILIO_AUTH, TWILIO_WHATSAPP_FROM (sandbox number, digits only
or with +), TWILIO_WHATSAPP_TO (your verified number).
"""
from __future__ import annotations

import os

from .base import Channel


def _wa(n: str) -> str:
    n = n.strip()
    return n if n.startswith("whatsapp:") else f"whatsapp:{n}"


class WhatsAppChannel(Channel):
    name, label = "whatsapp", "WhatsApp"
    CAPS = {"notify": True, "approve": False, "converse": False,
            "job_search": False, "job_apply": False, "post": False}

    def __init__(self) -> None:
        super().__init__()
        self._sid = os.getenv("TWILIO_SID", "")
        self._auth = os.getenv("TWILIO_AUTH", "")
        self._from = os.getenv("TWILIO_WHATSAPP_FROM", "")
        self._to = os.getenv("TWILIO_WHATSAPP_TO", "")

    @property
    def enabled(self) -> bool:
        return bool(self._sid and self._auth and self._from and self._to)

    def _config_detail(self) -> str:
        if self.enabled:
            return "Twilio WhatsApp configured (notify; reply-approval needs a public webhook)."
        return "Set TWILIO_SID, TWILIO_AUTH, TWILIO_WHATSAPP_FROM, TWILIO_WHATSAPP_TO."

    async def send(self, text: str, **kw) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self._sid}/Messages.json",
                auth=(self._sid, self._auth),
                data={"From": _wa(self._from), "To": _wa(self._to), "Body": text})
        ok = r.status_code < 400
        return {"ok": ok, "detail": "sent" if ok else f"Twilio {r.status_code}: {r.text[:120]}"}
