"""
Aegis — channel registry.

Instantiates every channel once, reads enablement from the environment, and
exposes status for the Integrations page. Also provides the fan-out helpers the
server uses: broadcast an approval request to channels that can notify, push
alerts, and route a single inbound command handler to every channel.
"""
from __future__ import annotations

from .base import Channel, CommandHandler
from .discord import DiscordChannel
from .linkedin import LinkedInChannel
from .telegram import TelegramChannel
from .whatsapp import WhatsAppChannel

# Build order matters for display (Telegram first — the full loop).
CHANNELS: dict[str, Channel] = {
    c.name: c for c in (
        TelegramChannel(), DiscordChannel(), WhatsAppChannel(),
        LinkedInChannel(),
    )
}


def get(name: str) -> Channel | None:
    return CHANNELS.get(name)


def all_status() -> list[dict]:
    return [c.status() for c in CHANNELS.values()]


def enabled() -> list[Channel]:
    return [c for c in CHANNELS.values() if c.enabled]


def with_capability(cap: str) -> list[Channel]:
    return [c for c in CHANNELS.values() if c.capabilities.get(cap)]


async def start_all(handler: CommandHandler) -> None:
    """Register the inbound handler everywhere and start listeners (Telegram)."""
    for c in CHANNELS.values():
        c.on_command(handler)
        if c.enabled:
            await c.start()


async def broadcast_approval(*, kind: str, run_id: str, title: str, body: str) -> list[dict]:
    """Send an approval request to every notify-capable channel. Honest results."""
    results = []
    for c in with_capability("notify"):
        try:
            res = await c.send_approval(kind=kind, run_id=run_id, title=title, body=body)
        except Exception as e:
            res = {"ok": False, "detail": f"send failed: {e}"}
        results.append({"channel": c.name, "native_approve": c.capabilities.get("approve"), **res})
    return results


async def notify(text: str) -> list[dict]:
    """Push an alert to every notify-capable channel."""
    out = []
    for c in with_capability("notify"):
        try:
            out.append({"channel": c.name, **(await c.send(text))})
        except Exception as e:
            out.append({"channel": c.name, "ok": False, "detail": str(e)})
    return out
