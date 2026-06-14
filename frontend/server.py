"""
Aegis — live war-room frontend.

A thin FastAPI layer over the existing orchestrator. It re-implements NO incident
logic: it builds the same LocalBus the agents post to, subscribes a relay handler,
runs run_incident(), and streams each RoomMessage to the browser over SSE exactly
as it lands in the room. The single-page React UI drops each message into its
agent's color lane and lights up the validator's REJECT -> PASS beat.

Run from the repo root (never cd into a subdir):

    python -m frontend.server        # then open http://127.0.0.1:8000

Stays offline-first: React + htm are vendored under static/vendor, so the UI
needs zero network. LLM_MODE defaults to offline, so the demo needs zero keys.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.bus import LocalBus
from backend.orchestrator import run_incident

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Aegis War Room")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Run one incident and relay every room message live, then the verdict."""
    pace = float(request.query_params.get("pace", os.getenv("AEGIS_PACE", "0.7")))
    queue: asyncio.Queue = asyncio.Queue()
    bus = LocalBus()

    async def relay(msg) -> None:
        await queue.put(("message", msg.model_dump(mode="json")))

    bus.subscribe(relay)

    async def drive() -> None:
        try:
            _, verdict = await run_incident(bus)
            await queue.put(("verdict", verdict))
        except Exception as exc:  # surface failures to the UI instead of hanging
            await queue.put(("error", {"detail": str(exc)}))
        finally:
            await queue.put(("done", None))

    async def events():
        task = asyncio.create_task(drive())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "done":
                    yield _sse("done", {})
                    break
                yield _sse(kind, data)
                # pace only the room chatter so the cascade reads "live"; the
                # verdict lands immediately after the last message.
                if kind == "message" and pace > 0 and not await request.is_disconnected():
                    await asyncio.sleep(pace)
        finally:
            task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def main() -> None:
    import uvicorn

    host = os.getenv("AEGIS_HOST", "127.0.0.1")
    port = int(os.getenv("AEGIS_PORT", "8000"))
    print(f"  AEGIS war room → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
