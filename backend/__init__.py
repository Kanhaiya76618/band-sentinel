"""Aegis backend package. Auto-loads .env from the project root on import."""
import os
from pathlib import Path


def _load_dotenv() -> None:
    """
    Load the first .env found walking up from this file.

    Robust against the footguns that silently shadow a real value:
      * strip BOM / CR / surrounding whitespace and quotes off keys and values;
      * a NON-EMPTY value always beats an empty one for the same key, and among
        non-empty assignments the LAST one wins — so an empty placeholder line
        (e.g. `BAND_CHAT_ID=`) above a filled line can't win;
      * empty values are NEVER written to the environment, so a blank line leaves
        the var genuinely unset (callers can detect "missing" instead of "");
      * a genuinely-set (non-empty) SHELL var still wins; an EMPTY shell var does
        not block the file's real value.
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        env_path = parent / ".env"
        if not env_path.exists():
            continue

        # Resolve the file's assignments first (non-empty wins; last non-empty wins).
        file_vals: dict[str, str] = {}
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip().lstrip("﻿").strip()  # surrounding ws + CR + BOM
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#", 1)[0].strip().strip('"').strip("'").strip()
            if not key:
                continue
            if val:
                file_vals[key] = val            # non-empty -> wins (last non-empty wins)
            else:
                file_vals.setdefault(key, "")   # remember it exists, lowest priority

        # Apply: non-empty shell value wins; otherwise a non-empty file value wins
        # (including over an empty shell var). Never write empties.
        for key, val in file_vals.items():
            if os.environ.get(key):             # genuinely-set shell var wins
                continue
            if val:
                os.environ[key] = val
        return


_load_dotenv()
