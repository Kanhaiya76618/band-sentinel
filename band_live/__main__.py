"""Entry point: ``python -m band_live`` (needs BAND_* creds in backend/.env)."""
from __future__ import annotations

import asyncio

from .runner import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
