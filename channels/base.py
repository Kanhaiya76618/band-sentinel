"""
Aegis — the Channel abstraction.

A channel is a thin, HONEST adapter over an external platform. It declares the
capabilities it can actually deliver in THIS runtime (httpx-only, possibly no
public URL), and never advertises a capability it can't back up.

    capabilities keys:
        notify      can send an outbound message to the user
        approve     can capture an inbound Approve/Reject that resolves a gate
                    WITHOUT extra public-URL setup (Telegram long-poll only)
        converse    two-way chat
        job_search  can search jobs (always False — search is Adzuna's job)
        job_apply   can auto-apply (False; LinkedIn/X forbid it by ToS)
        post        can publish public content (X / LinkedIn / Discord channel)

Inbound commands are delivered to a single handler registered via on_command().
The command shape is {"action": "approve"|"reject", "kind": "incident"|"job",
"run_id": "..."} so the server can resolve the matching commander gate.
"""
from __future__ import annotations

import abc
import os
from typing import Awaitable, Callable, Optional

CommandHandler = Callable[[dict], Awaitable[bool]]

CAP_KEYS = ("notify", "approve", "converse", "job_search", "job_apply", "post")


def app_url() -> str:
    return os.getenv("AEGIS_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


class Channel(abc.ABC):
    name = "channel"
    label = "Channel"
    # Declared capability ceiling; the live value is AND-ed with `enabled`.
    CAPS: dict[str, bool] = {k: False for k in CAP_KEYS}

    def __init__(self) -> None:
        self._handler: Optional[CommandHandler] = None

    # ---- configuration -------------------------------------------------- #
    @property
    @abc.abstractmethod
    def enabled(self) -> bool:
        """True only when the channel's required env keys are present."""

    @abc.abstractmethod
    def _config_detail(self) -> str:
        """Human-readable config status (which env var to set), never a secret."""

    @property
    def capabilities(self) -> dict:
        return {k: (self.CAPS.get(k, False) and self.enabled) for k in CAP_KEYS}

    def status(self) -> dict:
        return {
            "name": self.name, "label": self.label,
            "enabled": self.enabled, "ok": self.enabled,
            "detail": self._config_detail(),
            "capabilities": self.capabilities,
        }

    # ---- inbound -------------------------------------------------------- #
    def on_command(self, handler: CommandHandler) -> None:
        self._handler = handler

    async def _dispatch(self, command: dict) -> bool:
        if self._handler is None:
            return False
        return await self._handler(command)

    async def start(self) -> None:
        """Begin inbound listening if the channel supports it (override)."""
        return

    # ---- outbound ------------------------------------------------------- #
    @abc.abstractmethod
    async def send(self, text: str, **kw) -> dict:
        """Send a plain message. Returns {ok, detail, ...}."""

    async def send_test(self) -> dict:
        if not self.enabled:
            return {"ok": False, "detail": self._config_detail()}
        try:
            return await self.send(f"✅ Aegis test — the {self.label} channel is live.")
        except Exception as e:  # surface honestly
            return {"ok": False, "detail": f"send failed: {e}"}

    async def send_approval(self, *, kind: str, run_id: str, title: str, body: str) -> dict:
        """
        Default approval delivery: message + a deep link back into the app.
        Channels with native inbound (Telegram) override to attach buttons that
        resolve the gate directly. We NEVER claim it's approved here.
        """
        section = "resolve" if kind == "incident" else "jobs"
        link = f"{app_url()}/#{section}"
        return await self.send(f"{title}\n\n{body}\n\n👉 Approve/Reject in Aegis: {link}")
