"""
Telegram channel — the full loop.

Outbound: Bot API sendMessage. Approvals attach an inline keyboard
(Approve/Reject) whose callback_data carries the run id. Inbound: a background
getUpdates long-poll (no public URL needed) receives the button press and
resolves the commander's HITL gate, then edits the message to show the outcome.

Env: TELEGRAM_BOT_TOKEN (from @BotFather) + TELEGRAM_CHAT_ID (your chat/user id).
"""
from __future__ import annotations

import asyncio
import os

from .base import Channel


class TelegramChannel(Channel):
    name, label = "telegram", "Telegram"
    CAPS = {"notify": True, "approve": True, "converse": True,
            "job_search": False, "job_apply": False, "post": False}

    def __init__(self) -> None:
        super().__init__()
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat = os.getenv("TELEGRAM_CHAT_ID", "")
        self._base = f"https://api.telegram.org/bot{self._token}"
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat)

    def _config_detail(self) -> str:
        if self._token and self._chat:
            return "Bot token + chat id configured (full send/approve loop)."
        if self._token and not self._chat:
            return "TELEGRAM_BOT_TOKEN set; missing TELEGRAM_CHAT_ID."
        return "Set TELEGRAM_BOT_TOKEN (@BotFather) + TELEGRAM_CHAT_ID."

    async def send(self, text: str, **kw) -> dict:
        import httpx
        payload = {"chat_id": self._chat, "text": text}
        if kw.get("reply_markup"):
            payload["reply_markup"] = kw["reply_markup"]
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{self._base}/sendMessage", json=payload)
        ok = r.status_code < 400 and r.json().get("ok")
        return {"ok": bool(ok), "detail": "sent" if ok else f"Telegram {r.status_code}: {r.text[:120]}"}

    async def send_approval(self, *, kind: str, run_id: str, title: str, body: str) -> dict:
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{kind}:{run_id}"},
            {"text": "✕ Reject", "callback_data": f"reject:{kind}:{run_id}"},
        ]]}
        return await self.send(f"{title}\n\n{body}", reply_markup=keyboard)

    async def start(self) -> None:
        if self.enabled and self._task is None:
            self._task = asyncio.create_task(self._poll())

    async def _poll(self) -> None:
        import httpx
        offset: int | None = None
        async with httpx.AsyncClient(base_url=self._base, timeout=40) as c:
            while True:
                try:
                    params = {"timeout": 30}
                    if offset is not None:
                        params["offset"] = offset
                    r = await c.get("/getUpdates", params=params)
                    for upd in r.json().get("result", []):
                        offset = upd["update_id"] + 1
                        cq = upd.get("callback_query")
                        if cq:
                            await self._on_callback(cq, c)
                except Exception:
                    await asyncio.sleep(3)

    async def _on_callback(self, cq: dict, c) -> None:
        data = cq.get("data", "")
        parts = data.split(":")
        if len(parts) != 3:
            return
        action, kind, run_id = parts
        granted = await self._dispatch({"action": action, "kind": kind, "run_id": run_id})
        verdict = ("✅ Approved" if action == "approve" else "✕ Rejected") if granted \
            else "⚠ This request already closed."
        # acknowledge the tap + reflect the outcome in the thread
        await c.post("/answerCallbackQuery", json={"callback_query_id": cq["id"], "text": verdict})
        msg = cq.get("message", {})
        if msg.get("chat") and msg.get("message_id"):
            await c.post("/editMessageText", json={
                "chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                "text": (msg.get("text", "") + f"\n\n— {verdict}"),
            })
