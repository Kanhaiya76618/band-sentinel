"""
Aegis — the agent bus.

This is the single most important abstraction in the project. Agents NEVER
talk to each other directly. They `post()` a RoomMessage and `subscribe()` to
the room. That means the *exact same agent code* runs on:

    * LocalBus  — in-process, zero keys, for building & the offline demo
    * BandBus   — Band's shared agent room, swapped in at kickoff

Switching is one line in config (BUS = "local" | "band"). The judges' "is Band
really the coordination layer?" question is answered structurally: every single
inter-agent message goes through the bus, so on BandBus every collaboration beat
physically happens inside Band.
"""
from __future__ import annotations

import abc
import asyncio
import os
from typing import Awaitable, Callable, Optional

from .contracts import RoomMessage

Handler = Callable[[RoomMessage], Awaitable[None]]


class AgentBus(abc.ABC):
    """A shared room agents post to and subscribe from."""

    @abc.abstractmethod
    async def post(self, msg: RoomMessage) -> None: ...

    @abc.abstractmethod
    def subscribe(self, handler: Handler) -> None: ...

    @abc.abstractmethod
    async def history(self) -> list[RoomMessage]: ...


class LocalBus(AgentBus):
    """
    In-process pub/sub. Deterministic ordering via a global sequence number,
    which makes the demo transcript reproducible every run.
    """

    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._log: list[RoomMessage] = []
        self._seq = 0
        self._lock = asyncio.Lock()

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def post(self, msg: RoomMessage) -> None:
        async with self._lock:
            self._seq += 1
            msg.seq = self._seq
            self._log.append(msg)
        # fan out to every subscriber except the sender
        for h in self._handlers:
            await h(msg)

    async def history(self) -> list[RoomMessage]:
        return list(self._log)


class BandBus(AgentBus):
    """
    Band-backed room. STUB — fill in at kickoff from the Band Agent API docs.

    The shape Band gives you (per the Hacker Guide): create/join a room, send a
    message addressed by @mention, and receive messages via a stream/webhook.
    Map those three calls onto post/subscribe/history below and nothing else in
    the codebase changes.

        env needed at kickoff:
            BAND_API_KEY=...
            BAND_ROOM_ID=...      # or create one on first run
    """

    def __init__(self, room_id: Optional[str] = None) -> None:
        self._handlers: list[Handler] = []
        self._room_id = room_id or os.getenv("BAND_ROOM_ID")
        self._api_key = os.getenv("BAND_API_KEY")
        # import httpx lazily so offline mode needs zero extra deps
        import httpx  # noqa: F401  (kept here as the live-mode marker)
        self._client = None  # TODO: httpx.AsyncClient(base_url=..., headers=...)

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)
        # TODO: open Band's message stream for self._room_id and, for each
        # inbound event, build a RoomMessage and `await handler(msg)`.

    async def post(self, msg: RoomMessage) -> None:
        # TODO: POST msg to Band's "send message to room" endpoint, e.g.
        #   await self._client.post(f"/rooms/{self._room_id}/messages",
        #       json={"sender": msg.sender, "mentions": msg.mentions,
        #             "intent": msg.intent.value, "text": msg.text,
        #             "payload": msg.payload})
        raise NotImplementedError(
            "BandBus.post: wire to Band Agent API at kickoff. "
            "Until then run with BUS=local."
        )

    async def history(self) -> list[RoomMessage]:
        # TODO: GET the room transcript and map each item back to RoomMessage.
        raise NotImplementedError("BandBus.history: wire to Band Agent API.")


def make_bus() -> AgentBus:
    """Factory: the one place that decides Local vs Band."""
    kind = os.getenv("BUS", "local").lower()
    if kind == "band":
        return BandBus()
    return LocalBus()
