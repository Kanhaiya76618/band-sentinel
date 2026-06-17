"""
Aegis — persistence (stdlib sqlite3, zero heavyweight deps).

One SQLite file at ``data/aegis.db`` holds every run from BOTH agent workflows:

    * incident_runs — one row per incident resolution (full transcript + verdict)
    * job_runs      — one row per job-search run (profile, matches, applications)

The store is the single source of truth the dashboard, history and analytics
sections read from. Phase 2 (incidents) and Phase 3 (jobs) write to it; Phase 1
only reads aggregate stats + the activity feed (which are honestly empty until
the first real run lands).

Connections are opened per call. SQLite handles that fine for this load and it
keeps us free of any async/threading ceremony with FastAPI.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

# data/aegis.db at the repo root (parent of the backend package).
_REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _REPO_ROOT / "data"
DB_PATH = DATA_DIR / "aegis.db"

WEEK_SECONDS = 7 * 24 * 3600


# --------------------------------------------------------------------------- #
# Connection + schema
# --------------------------------------------------------------------------- #
def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if absent. Safe to call on every server start."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incident_runs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at          REAL    NOT NULL,
                incident_id         TEXT,
                service             TEXT,
                region              TEXT,
                severity            TEXT,
                resolved            INTEGER NOT NULL DEFAULT 0,
                action              TEXT,
                approved_by         TEXT,
                mttr_seconds        REAL,
                decision_latency_ms REAL,
                downtime_cost_usd   REAL,
                remediation_cost_usd REAL,
                averted_cost_usd    REAL,
                source              TEXT,            -- 'upload' | 'demo'
                transcript          TEXT,            -- JSON: list[RoomMessage]
                verdict             TEXT,            -- JSON
                postmortem          TEXT             -- JSON
            );

            CREATE TABLE IF NOT EXISTS job_runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    REAL    NOT NULL,
                entry_mode    TEXT,                  -- 'company' | 'field' | 'resume'
                query         TEXT,                  -- company name / field / resume name
                profile       TEXT,                  -- JSON: structured search profile
                matches       TEXT,                  -- JSON: ranked matches
                match_count   INTEGER NOT NULL DEFAULT 0,
                tailored_count INTEGER NOT NULL DEFAULT 0,
                applied_count INTEGER NOT NULL DEFAULT 0,
                queued_count  INTEGER NOT NULL DEFAULT 0,
                applications  TEXT,                  -- JSON: list of application records
                transcript    TEXT,                  -- JSON: list[RoomMessage]
                verdict       TEXT                   -- JSON
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- Demo-grade auth (Phase 7). Passwords are pbkdf2-hashed, never plaintext.
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT    NOT NULL,        -- algorithm$iterations$salt$hash
                created_at    REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                created_at REAL    NOT NULL,
                expires_at REAL    NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        # Scope runs to the signed-in user. Older DBs predate these columns, so add
        # them if absent (NULL user_id = pre-auth demo rows, never shown to a user).
        for table in ("incident_runs", "job_runs"):
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "user_id" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def save_incident_run(
    *,
    transcript: list[dict],
    verdict: dict,
    service: str,
    region: str,
    severity: str,
    source: str,
    incident_id: Optional[str] = None,
    postmortem: Optional[dict] = None,
    user_id: Optional[int] = None,
) -> int:
    """Persist a completed incident run; returns its row id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO incident_runs (
                created_at, incident_id, service, region, severity, resolved,
                action, approved_by, mttr_seconds, decision_latency_ms,
                downtime_cost_usd, remediation_cost_usd, averted_cost_usd,
                source, transcript, verdict, postmortem, user_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                time.time(), incident_id, service, region, severity,
                1 if verdict.get("resolved") else 0,
                verdict.get("action"), verdict.get("approved_by"),
                verdict.get("mttr_seconds"), verdict.get("decision_latency_ms"),
                verdict.get("downtime_cost_usd"), verdict.get("remediation_cost_usd"),
                verdict.get("averted_cost_usd"),
                source, _dumps(transcript), _dumps(verdict),
                _dumps(postmortem) if postmortem is not None else None,
                user_id,
            ),
        )
        return int(cur.lastrowid)


def save_job_run(
    *,
    entry_mode: str,
    query: str,
    profile: dict,
    matches: list[dict],
    applications: Optional[list[dict]] = None,
    transcript: Optional[list[dict]] = None,
    verdict: Optional[dict] = None,
    tailored_count: int = 0,
    user_id: Optional[int] = None,
) -> int:
    """Persist a completed job-search run; returns its row id."""
    applications = applications or []
    applied = sum(1 for a in applications if a.get("status") == "submitted")
    queued = sum(1 for a in applications if a.get("status") == "queued")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO job_runs (
                created_at, entry_mode, query, profile, matches, match_count,
                tailored_count, applied_count, queued_count, applications,
                transcript, verdict, user_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                time.time(), entry_mode, query, _dumps(profile), _dumps(matches),
                len(matches), tailored_count, applied, queued,
                _dumps(applications), _dumps(transcript or []),
                _dumps(verdict) if verdict is not None else None,
                user_id,
            ),
        )
        return int(cur.lastrowid)


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def _loads(row: sqlite3.Row, *fields: str) -> dict:
    out = dict(row)
    for f in fields:
        if out.get(f):
            try:
                out[f] = json.loads(out[f])
            except (json.JSONDecodeError, TypeError):
                out[f] = None
    return out


def _owns(row: sqlite3.Row, user_id: Optional[int]) -> bool:
    """Ownership check: when scoping is on, the row must belong to this user."""
    return user_id is None or row["user_id"] == user_id


def get_incident_run(run_id: int, user_id: Optional[int] = None) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM incident_runs WHERE id=?", (run_id,)).fetchone()
    if not row or not _owns(row, user_id):
        return None
    return _loads(row, "transcript", "verdict", "postmortem")


def get_job_run(run_id: int, user_id: Optional[int] = None) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM job_runs WHERE id=?", (run_id,)).fetchone()
    if not row or not _owns(row, user_id):
        return None
    return _loads(row, "profile", "matches", "applications", "transcript", "verdict")


def list_incident_runs(limit: int = 100, user_id: Optional[int] = None) -> list[dict]:
    where, args = ("WHERE user_id=?", (user_id,)) if user_id is not None else ("", ())
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM incident_runs {where} ORDER BY created_at DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
    return [_loads(r, "verdict", "postmortem") for r in rows]


def list_job_runs(limit: int = 100, user_id: Optional[int] = None) -> list[dict]:
    where, args = ("WHERE user_id=?", (user_id,)) if user_id is not None else ("", ())
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM job_runs {where} ORDER BY created_at DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
    return [_loads(r, "profile", "matches", "applications", "verdict") for r in rows]


# --------------------------------------------------------------------------- #
# Aggregates for the dashboard / analytics
# --------------------------------------------------------------------------- #
def dashboard_stats(user_id: Optional[int] = None) -> dict:
    """Summary-card numbers. All honest aggregates over real persisted runs."""
    cutoff = time.time() - WEEK_SECONDS
    uf, ua = ("AND user_id=?", (user_id,)) if user_id is not None else ("", ())
    with _connect() as conn:
        inc = conn.execute(
            f"""
            SELECT
                COUNT(*)                                        AS total,
                SUM(CASE WHEN resolved=0 THEN 1 ELSE 0 END)     AS open,
                SUM(CASE WHEN resolved=1 THEN 1 ELSE 0 END)     AS resolved,
                AVG(CASE WHEN resolved=1 THEN mttr_seconds END) AS avg_mttr,
                SUM(averted_cost_usd)                           AS averted,
                SUM(CASE WHEN resolved=1 AND created_at>=? THEN 1 ELSE 0 END) AS resolved_7d
            FROM incident_runs WHERE 1=1 {uf}
            """,
            (cutoff, *ua),
        ).fetchone()
        job = conn.execute(
            f"""
            SELECT
                COUNT(*)             AS runs,
                SUM(match_count)     AS jobs_found,
                SUM(applied_count)   AS applications_sent,
                SUM(tailored_count)  AS resumes_tailored
            FROM job_runs WHERE 1=1 {uf}
            """,
            ua,
        ).fetchone()

    return {
        "open_incidents": inc["open"] or 0,
        "mttr_avg_seconds": round(inc["avg_mttr"], 1) if inc["avg_mttr"] else 0.0,
        "cost_averted_usd": round(inc["averted"] or 0.0, 2),
        "incidents_resolved_7d": inc["resolved_7d"] or 0,
        "incidents_total": inc["total"] or 0,
        "jobs_found": job["jobs_found"] or 0,
        "applications_sent": job["applications_sent"] or 0,
        "resumes_tailored": job["resumes_tailored"] or 0,
        "job_runs": job["runs"] or 0,
    }


# --------------------------------------------------------------------------- #
# Settings (platform preferences — never stores secret values)
# --------------------------------------------------------------------------- #
def get_setting(key: str, default: str | None = None) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def all_settings() -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def email_recipients() -> list[str] | None:
    """Recipient override stored via Settings (falls back to env EMAIL_TO if None)."""
    raw = get_setting("email_recipients")
    if not raw:
        return None
    addrs = [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]
    return addrs or None


# --------------------------------------------------------------------------- #
# Users + sessions (demo-grade auth, Phase 7). Hashing lives in backend/auth.py;
# this layer only persists the already-hashed credential.
# --------------------------------------------------------------------------- #
def create_user(email: str, password_hash: str) -> Optional[int]:
    """Insert a new user. Returns the id, or None if the email already exists."""
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users(email, password_hash, created_at) VALUES(?,?,?)",
                (email.strip(), password_hash, time.time()),
            )
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None


def get_user_by_email(email: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email=? COLLATE NOCASE", (email.strip(),)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_session(token: str, user_id: int, expires_at: float) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?,?,?,?)",
            (token, user_id, time.time(), expires_at),
        )


def get_session_user(token: str) -> Optional[dict]:
    """Resolve a session token to its (unexpired) user, else None."""
    if not token:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT u.* , s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token=?", (token,)
        ).fetchone()
    if not row or (row["expires_at"] or 0) < time.time():
        return None
    return dict(row)


def delete_session(token: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


def purge_expired_sessions() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))


# ---- per-user preferences (parsed resume, recent recipients) -------------- #
def _user_key(user_id: int, name: str) -> str:
    return f"u:{user_id}:{name}"


def set_user_resume(user_id: int, profile: dict) -> None:
    set_setting(_user_key(user_id, "resume_profile"), _dumps(profile))


def get_user_resume(user_id: int) -> Optional[dict]:
    raw = get_setting(_user_key(user_id, "resume_profile"))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def get_recent_recipients(user_id: int) -> list[str]:
    raw = get_setting(_user_key(user_id, "recent_recipients"))
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []


def remember_recipients(user_id: int, addrs: list[str], cap: int = 8) -> list[str]:
    """Prepend newly-used recipients to the per-user MRU list (deduped)."""
    seen = get_recent_recipients(user_id)
    for a in reversed([x.strip() for x in addrs if x and x.strip()]):
        seen = [a] + [x for x in seen if x.lower() != a.lower()]
    seen = seen[:cap]
    set_setting(_user_key(user_id, "recent_recipients"), _dumps(seen))
    return seen


# --------------------------------------------------------------------------- #
# Analytics (Phase 5)
# --------------------------------------------------------------------------- #
def analytics(user_id: Optional[int] = None) -> dict:
    """Cheap aggregates: MTTR trend, cumulative cost averted, application funnel."""
    uf, ua = ("WHERE user_id=?", (user_id,)) if user_id is not None else ("", ())
    with _connect() as conn:
        inc = conn.execute(
            "SELECT created_at, mttr_seconds, averted_cost_usd, resolved "
            f"FROM incident_runs {uf} ORDER BY created_at ASC",
            ua,
        ).fetchall()
        job = conn.execute(
            "SELECT COALESCE(SUM(match_count),0) f, COALESCE(SUM(tailored_count),0) t, "
            f"COALESCE(SUM(applied_count),0) s, COALESCE(SUM(queued_count),0) q FROM job_runs {uf}",
            ua,
        ).fetchone()

    mttr_series, cost_series = [], []
    cumulative = 0.0
    resolved = escalated = 0
    for r in inc:
        if r["resolved"]:
            resolved += 1
            if r["mttr_seconds"]:
                mttr_series.append({"t": r["created_at"], "mttr_min": round(r["mttr_seconds"] / 60, 1)})
        else:
            escalated += 1
        cumulative += r["averted_cost_usd"] or 0.0
        cost_series.append({"t": r["created_at"], "cumulative": round(cumulative, 2)})

    return {
        "mttr_series": mttr_series,
        "cost_series": cost_series,
        "incident_status": {"resolved": resolved, "escalated": escalated},
        "job_funnel": {"found": job["f"], "tailored": job["t"], "submitted": job["s"], "queued": job["q"]},
    }


def recent_activity(limit: int = 12, user_id: Optional[int] = None) -> list[dict]:
    """Unified newest-first feed across both workflows for the dashboard."""
    feed: list[dict] = []
    for r in list_incident_runs(limit, user_id=user_id):
        resolved = bool(r["resolved"])
        feed.append({
            "kind": "incident",
            "id": r["id"],
            "created_at": r["created_at"],
            "title": f"{r['service'] or 'incident'} / {r['region'] or '—'}",
            "subtitle": (
                f"Resolved via {r['action']} · MTTR {(r['mttr_seconds'] or 0)/60:.1f} min"
                if resolved else "Escalated to human — not auto-resolved"
            ),
            "status": "resolved" if resolved else "escalated",
        })
    for r in list_job_runs(limit, user_id=user_id):
        feed.append({
            "kind": "job",
            "id": r["id"],
            "created_at": r["created_at"],
            "title": f"Job search · {r['query'] or r['entry_mode']}",
            "subtitle": (
                f"{r['match_count']} matches · {r['applied_count']} applied · "
                f"{r['queued_count']} queued"
            ),
            "status": "submitted" if r["applied_count"] else "queued" if r["queued_count"] else "searched",
        })
    feed.sort(key=lambda x: x["created_at"], reverse=True)
    return feed[:limit]
