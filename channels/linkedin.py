"""
LinkedIn channel — strictly within what LinkedIn's API permits.

PERMITTED: authenticate, share a post, and generate a tailored post/application
DRAFT for the user to approve and share. NOT PERMITTED (and therefore never
attempted): programmatic job search or auto-apply — LinkedIn's API forbids it,
so those capabilities are hard-False. For jobs we instead hand the user the
ready package + the posting's apply URL (handled by the jobs @applier).

Env: LINKEDIN_ACCESS_TOKEN (a member token from the OAuth flow; LINKEDIN_CLIENT_ID
/ LINKEDIN_CLIENT_SECRET drive that sign-in). Optional LINKEDIN_AUTHOR_URN.
"""
from __future__ import annotations

import os

from .base import Channel


class LinkedInChannel(Channel):
    name, label = "linkedin", "LinkedIn"
    CAPS = {"notify": False, "approve": False, "converse": False,
            "job_search": False, "job_apply": False, "post": True}

    def __init__(self) -> None:
        super().__init__()
        self._token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
        self._author = os.getenv("LINKEDIN_AUTHOR_URN", "")
        self._client = os.getenv("LINKEDIN_CLIENT_ID", "")

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    def _config_detail(self) -> str:
        if self._token:
            return "Member token configured (share/draft only — search/apply forbidden by API)."
        if self._client:
            return "LINKEDIN_CLIENT_ID set; complete OAuth to obtain LINKEDIN_ACCESS_TOKEN."
        return "Set LINKEDIN_ACCESS_TOKEN (via OAuth) to enable share. Search/apply not permitted."

    async def _resolve_author(self, c) -> str | None:
        if self._author:
            return self._author
        r = await c.get("https://api.linkedin.com/v2/me",
                        headers={"Authorization": f"Bearer {self._token}"})
        if r.status_code < 400:
            return f"urn:li:person:{r.json().get('id')}"
        return None

    async def send(self, text: str, **kw) -> dict:
        """Share a post (the user has already approved the draft)."""
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            author = await self._resolve_author(c)
            if not author:
                return {"ok": False, "detail": "Could not resolve LinkedIn author URN."}
            body = {
                "author": author, "lifecycleState": "PUBLISHED",
                "specificContent": {"com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"}},
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }
            r = await c.post("https://api.linkedin.com/v2/ugcPosts",
                             headers={"Authorization": f"Bearer {self._token}",
                                      "X-Restli-Protocol-Version": "2.0.0"}, json=body)
        ok = r.status_code < 400
        return {"ok": ok, "detail": "shared" if ok else f"LinkedIn {r.status_code}: {r.text[:140]}"}

    async def send_test(self) -> dict:
        if not self.enabled:
            return {"ok": False, "detail": self._config_detail()}
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get("https://api.linkedin.com/v2/me",
                                headers={"Authorization": f"Bearer {self._token}"})
            if r.status_code < 400:
                return {"ok": True, "detail": "token valid (no post made)."}
            return {"ok": False, "detail": f"LinkedIn {r.status_code}: {r.text[:140]}"}
        except Exception as e:
            return {"ok": False, "detail": f"verify failed: {e}"}
