"""
X (Twitter) channel — API v2.

Posting a tweet requires user-context auth, so we sign requests with OAuth 1.0a
(stdlib hmac/hashlib — no extra deps) using the app + access key/secret pairs.
Read/search are best-effort with the app bearer token and degrade clearly
(free tier is very limited).

Honest scope: `post` only. No notify/approve/job_* — X is a publish surface, and
any post still goes through human approval in the app first.

Env (post): X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET.
Env (read, optional): X_BEARER_TOKEN.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import urllib.parse
import uuid

from .base import Channel


class TwitterChannel(Channel):
    name, label = "twitter", "X (Twitter)"
    CAPS = {"notify": False, "approve": False, "converse": False,
            "job_search": False, "job_apply": False, "post": True}

    def __init__(self) -> None:
        super().__init__()
        self._ck = os.getenv("X_API_KEY", "")
        self._cs = os.getenv("X_API_SECRET", "")
        self._at = os.getenv("X_ACCESS_TOKEN", "")
        self._as = os.getenv("X_ACCESS_SECRET", "")
        self._bearer = os.getenv("X_BEARER_TOKEN", "")

    @property
    def enabled(self) -> bool:
        return bool(self._ck and self._cs and self._at and self._as)

    def _config_detail(self) -> str:
        if self.enabled:
            return "OAuth1 app+access keys configured (post enabled, approve-then-share)."
        return "Set X_API_KEY/X_API_SECRET/X_ACCESS_TOKEN/X_ACCESS_SECRET to post."

    def _oauth1_header(self, method: str, url: str) -> str:
        params = {
            "oauth_consumer_key": self._ck,
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self._at,
            "oauth_version": "1.0",
        }
        enc = lambda s: urllib.parse.quote(str(s), safe="")
        base_str = "&".join([
            method.upper(), enc(url),
            enc("&".join(f"{enc(k)}={enc(params[k])}" for k in sorted(params))),
        ])
        signing_key = f"{enc(self._cs)}&{enc(self._as)}"
        sig = base64.b64encode(
            hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()).decode()
        params["oauth_signature"] = sig
        return "OAuth " + ", ".join(f'{enc(k)}="{enc(v)}"' for k, v in sorted(params.items()))

    async def send(self, text: str, **kw) -> dict:
        """Post a tweet (the 'post' capability). Caller must have approval."""
        import httpx
        url = "https://api.twitter.com/2/tweets"
        headers = {"Authorization": self._oauth1_header("POST", url), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, headers=headers, json={"text": text[:280]})
        ok = r.status_code < 400
        tid = r.json().get("data", {}).get("id") if ok else None
        return {"ok": ok, "detail": (f"posted (id {tid})" if ok else f"X {r.status_code}: {r.text[:140]}"),
                "url": f"https://x.com/i/web/status/{tid}" if tid else None}

    async def send_test(self) -> dict:
        if not self.enabled:
            return {"ok": False, "detail": self._config_detail()}
        # Verify credentials WITHOUT making a public post.
        import httpx
        url = "https://api.twitter.com/2/users/me"
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get(url, headers={"Authorization": self._oauth1_header("GET", url)})
            if r.status_code < 400:
                return {"ok": True, "detail": f"authenticated as @{r.json().get('data', {}).get('username', '?')} (no post made)."}
            return {"ok": False, "detail": f"X {r.status_code}: {r.text[:140]}"}
        except Exception as e:
            return {"ok": False, "detail": f"verify failed: {e}"}
