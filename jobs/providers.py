"""
Aegis — job search providers.

A ``JobSearchProvider`` interface plus ONE real implementation: Adzuna
(https://developer.adzuna.com — free app id + key, no card). The validator
calls ``search()`` to pull CURRENT real postings; everything downstream (ranking,
tailoring, applying) is provider-agnostic.

If the Adzuna keys aren't set we raise ``ProviderNotConfigured`` with a clear
message — we never fabricate postings.
"""
from __future__ import annotations

import abc
import os
from typing import Optional

from .contracts import JobMatch


class ProviderNotConfigured(RuntimeError):
    """Required provider keys are missing from the environment."""


class ProviderError(RuntimeError):
    """The provider was reached but the request failed."""


class JobSearchProvider(abc.ABC):
    name = "provider"

    @abc.abstractmethod
    def search(
        self,
        *,
        what: str,
        where: Optional[str] = None,
        company: Optional[str] = None,
        limit: int = 10,
    ) -> list[JobMatch]:
        ...


class AdzunaProvider(JobSearchProvider):
    name = "adzuna"

    def __init__(self) -> None:
        self.app_id = os.getenv("ADZUNA_APP_ID")
        self.app_key = os.getenv("ADZUNA_APP_KEY")
        self.country = os.getenv("ADZUNA_COUNTRY", "gb").lower()
        if not (self.app_id and self.app_key):
            raise ProviderNotConfigured(
                "Adzuna not configured. Get a free app id + key at "
                "https://developer.adzuna.com and set ADZUNA_APP_ID + "
                "ADZUNA_APP_KEY (optionally ADZUNA_COUNTRY, default gb)."
            )

    def search(self, *, what, where=None, company=None, limit=10) -> list[JobMatch]:
        import httpx

        params = {
            "app_id": self.app_id, "app_key": self.app_key,
            "results_per_page": max(1, min(limit, 50)),
            "what": what, "content-type": "application/json",
        }
        if where:
            params["where"] = where
        if company:
            params["company"] = company  # Adzuna honors this as a filter when present
        url = f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1"
        try:
            resp = httpx.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"Adzuna {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"Adzuna request failed: {e}") from e

        out: list[JobMatch] = []
        for r in data.get("results", []):
            sal = None
            if r.get("salary_min"):
                lo, hi = r.get("salary_min"), r.get("salary_max") or r.get("salary_min")
                sal = f"{lo:,.0f}–{hi:,.0f}" if lo != hi else f"{lo:,.0f}"
            out.append(JobMatch(
                id=str(r.get("id", "")),
                title=r.get("title", "Untitled role"),
                company=(r.get("company") or {}).get("display_name", "Unknown"),
                location=(r.get("location") or {}).get("display_name"),
                salary=sal,
                url=r.get("redirect_url", ""),
                description=(r.get("description") or "")[:1200],
                posted=r.get("created"),
                provider=self.name,
            ))
        return out


def make_provider() -> JobSearchProvider:
    """Factory — the one place that picks the live job-search backend."""
    kind = os.getenv("JOB_PROVIDER", "adzuna").lower()
    if kind == "adzuna":
        return AdzunaProvider()
    raise ProviderNotConfigured(f"Unknown JOB_PROVIDER '{kind}'. Supported: adzuna.")
