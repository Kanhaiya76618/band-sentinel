"""
Aegis — telemetry ingest (Phase 2).

Parse a real uploaded observability artifact into the timeline shape
``detector.detect`` expects: a list of points, each with at least

    {"t": int, "p99_ms": float, "error_rate": float, "mem_util": float,
     "deploy": str | None}

Three formats are auto-detected from the bytes/extension:

    * JSON  — a list of points, or {"timeline": [...]}, with flexible field names
    * CSV   — header row mapped via the same field aliases
    * log   — plain lines containing key=value / key: value metric pairs

Field names are normalised from common aliases (p99 / latency_ms / errors /
memory …). Percentages (error_rate / mem_util given as 0–100) are scaled to
0–1. If the artifact can't be parsed into any usable points we raise
``IngestError`` with a clear message — we never fabricate telemetry.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from .detector import WATCHED  # ("p99_ms", "error_rate", "mem_util")


class IngestError(ValueError):
    """Raised when an upload can't be parsed into usable telemetry."""


# alias -> canonical metric name
_ALIASES: dict[str, str] = {
    "t": "t", "time": "t", "ts": "t", "timestamp": "t", "index": "t", "idx": "t",
    "orderdate": "t", "order_date": "t",
    "p99_ms": "p99_ms", "p99": "p99_ms", "latency_p99": "p99_ms",
    "latency_ms": "p99_ms", "latency": "p99_ms", "p99_latency": "p99_ms",
    "totalamount": "p99_ms", "total_amount": "p99_ms", "unitprice": "p99_ms", "unit_price": "p99_ms",
    "error_rate": "error_rate", "errors": "error_rate", "err": "error_rate",
    "error_pct": "error_rate", "errorrate": "error_rate", "error": "error_rate",
    "discount": "error_rate", "quantity": "error_rate",
    "mem_util": "mem_util", "mem": "mem_util", "memory": "mem_util",
    "memory_util": "mem_util", "mem_pct": "mem_util", "memory_pct": "mem_util",
    "tax": "mem_util", "shippingcost": "mem_util", "shipping_cost": "mem_util",
    "deploy": "deploy", "deploy_marker": "deploy", "version": "deploy",
    "release": "deploy", "build": "deploy",
    "orderstatus": "deploy", "order_status": "deploy",
}


def _canon(key: str) -> str | None:
    return _ALIASES.get(key.strip().lower().replace(" ", "_"))


def _num(v: Any) -> float | None:
    try:
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _normalise_point(raw: dict, t_index: int) -> dict | None:
    """Map one raw record's keys onto canonical metrics. Returns None if empty."""
    point: dict[str, Any] = {}
    for k, v in raw.items():
        canon = _canon(str(k))
        if not canon:
            continue
        if canon == "deploy":
            point["deploy"] = str(v).strip() or None if v not in (None, "") else None
        else:
            n = _num(v)
            if n is not None:
                point[canon] = n
    if not any(m in point for m in WATCHED):
        return None
    # Percent-scale: error_rate / mem_util given as 0..100 -> 0..1
    for m in ("error_rate", "mem_util"):
        if m in point and point[m] > 1.0:
            point[m] = point[m] / 100.0
    # Fill required metrics with benign defaults so detection has full rows.
    point.setdefault("p99_ms", 0.0)
    point.setdefault("error_rate", 0.0)
    point.setdefault("mem_util", 0.0)
    point.setdefault("deploy", None)
    point["t"] = int(point.get("t", t_index))
    return point


def _from_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("timeline", "points", "data", "metrics", "series"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        raise IngestError("JSON must be a list of points or {'timeline': [...]}.")
    out = []
    for i, raw in enumerate(data):
        if isinstance(raw, dict):
            p = _normalise_point(raw, i)
            if p:
                out.append(p)
    return out


def _from_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestError("CSV has no header row.")
    out = []
    for i, row in enumerate(reader):
        p = _normalise_point(row, i)
        if p:
            out.append(p)
    return out


_KV = re.compile(r"([A-Za-z_][\w ]*?)\s*[=:]\s*\"?([\w.%\-/]+)\"?")


def _from_log(text: str) -> list[dict]:
    out = []
    for i, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        pairs = {k: v for k, v in _KV.findall(line)}
        if pairs:
            p = _normalise_point(pairs, i)
            if p:
                out.append(p)
    return out


def parse_telemetry(content: str | bytes, filename: str = "") -> list[dict]:
    """Parse an uploaded artifact into a detector-ready telemetry timeline."""
    text = content.decode("utf-8", "replace") if isinstance(content, bytes) else content
    if not text.strip():
        raise IngestError("Upload is empty.")

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    stripped = text.lstrip()

    attempts: list = []
    if ext == "json" or stripped[:1] in "[{":
        attempts = [_from_json, _from_csv, _from_log]
    elif ext == "csv" or "," in text.splitlines()[0]:
        attempts = [_from_csv, _from_json, _from_log]
    else:
        attempts = [_from_log, _from_json, _from_csv]

    points: list[dict] = []
    last_err: Exception | None = None
    for fn in attempts:
        try:
            points = fn(text)
        except Exception as e:  # try the next parser
            last_err = e
            continue
        if points:
            break

    if not points:
        raise IngestError(
            "Couldn't find any p99/error_rate/mem_util metrics in the upload. "
            "Provide JSON/CSV/log rows with at least one of those fields"
            + (f" (last parser error: {last_err})" if last_err else "") + "."
        )

    # Re-index t sequentially so the rolling-window detector is well-formed.
    for i, p in enumerate(points):
        p["t"] = i
    return points
