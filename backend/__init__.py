"""Aegis backend package. Auto-loads .env from the project root on import."""
import os
from pathlib import Path


def _load_dotenv() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        env_path = parent / ".env"
        if env_path.exists():
            for raw in env_path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.split("#")[0].strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, val)
            return


_load_dotenv()
