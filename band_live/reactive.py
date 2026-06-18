"""
band_live — a small reactive agent base on the band-sdk receive API.

Each agent is one `band.Agent` (its own agent_id + key) whose adapter's
``on_message`` fires only for messages that @mention it (the band-sdk runtime
subscribes to the chat over Phoenix-Channels and routes per-agent via the
server-side ``/next`` queue, skipping the agent's own messages so there is no
self-loop). We wrap that in a thin ``ReactiveAgent`` whose adapter just forwards
each inbound @mention to a deterministic ``handler(msg, tools, room_id)`` — the
handler does the work (reusing backend logic) and posts the reply with
``tools.send_message`` (the same ``create_agent_chat_message`` REST call
BandBus.post uses), @mentioning whoever is next.

Receive-API note (introspected, not guessed): the layers are
  raw   `phoenix_channels_python_client.PHXChannelsClient.set_message_handler(topic, handler)`
  band  `band.BandLink.connect()/subscribe_room()/get_next_message()/mark_processed()`
  sdk   `band.Agent.create(adapter=SimpleAdapter)` → `on_message(...)`  ← used here
We use the `Agent`/`SimpleAdapter` layer because it reliably handles the `/next`
ack lifecycle, dedup, reconnect, and @mention-gating for us.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from band import Agent
from band.core.simple_adapter import SimpleAdapter

from . import protocol as P

# handler(msg: PlatformMessage, tools: AgentTools, room_id: str) -> None
Handler = Callable[[object, object, str], Awaitable[None]]


class _DispatchAdapter(SimpleAdapter):
    """Forwards every inbound @mention to a handler (skips pre-existing backlog)."""

    def __init__(self, handler: Handler, ignore_ids: set[str] | None = None):
        super().__init__()
        self._handler = handler
        self._ignore = set(ignore_ids or ())

    async def on_message(self, msg, tools, history, participants_msg, contacts_msg,
                         *, is_session_bootstrap, room_id) -> None:
        if msg.id in self._ignore:
            return  # stale backlog from before this run — only react to fresh messages
        await self._handler(msg, tools, room_id)


class ReactiveAgent:
    """One Band remote agent (handle -> its BAND_<HANDLE>_ID/_KEY) that reacts."""

    def __init__(self, handle: str, handler: Handler, ignore_ids: set[str] | None = None):
        self.handle = handle
        self.agent = Agent.create(
            adapter=_DispatchAdapter(handler, ignore_ids),
            agent_id=P.agent_id(handle), api_key=P.agent_key(handle),
            rest_url=P.rest_url(), ws_url=P.ws_url(),
        )

    async def start(self) -> None:
        await self.agent.start()

    async def run_forever(self) -> None:
        await self.agent.run_forever()

    async def stop(self) -> None:
        await self.agent.stop()
