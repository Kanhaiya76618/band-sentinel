"""
Discord channel.

Outbound is fully supported via either an incoming webhook
(DISCORD_WEBHOOK_URL) or a bot posting to a channel (DISCORD_BOT_TOKEN +
DISCORD_CHANNEL_ID) — used for incident/job alerts and posts.

Interactive Approve/Reject buttons require a Discord *gateway* websocket or a
public interactions endpoint with signature verification — neither is available
in this httpx-only/local runtime — so we DON'T claim the `approve` capability.
Approval requests still go out, with a deep link back to the app (base default).
"""
from __future__ import annotations

import os

from .base import Channel


class DiscordChannel(Channel):
    name, label = "discord", "Discord"
    CAPS = {"notify": True, "approve": False, "converse": False,
            "job_search": False, "job_apply": False, "post": True}

    def __init__(self) -> None:
        super().__init__()
        self._webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
        self._token = os.getenv("DISCORD_BOT_TOKEN", "")
        self._channel = os.getenv("DISCORD_CHANNEL_ID", "")

    @property
    def enabled(self) -> bool:
        return bool(self._webhook or (self._token and self._channel))

    def _config_detail(self) -> str:
        if self._webhook:
            return "Webhook configured (notify + post; approval via deep link)."
        if self._token and self._channel:
            return "Bot token + channel id configured (notify + post)."
        return "Set DISCORD_WEBHOOK_URL, or DISCORD_BOT_TOKEN + DISCORD_CHANNEL_ID."

    async def send(self, text: str, **kw) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            if self._webhook:
                r = await c.post(self._webhook, json={"content": text})
            else:
                r = await c.post(
                    f"https://discord.com/api/v10/channels/{self._channel}/messages",
                    headers={"Authorization": f"Bot {self._token}"}, json={"content": text})
        ok = r.status_code < 400
        return {"ok": ok, "detail": "sent" if ok else f"Discord {r.status_code}: {r.text[:120]}"}
