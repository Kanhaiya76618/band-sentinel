"""
Aegis — job-workflow typed payloads.

Mirrors backend/contracts.py: these pydantic models are dumped into
``RoomMessage.payload`` so the transport only ever carries plain JSON, exactly
like the incident side. The RoomMessage envelope + Intent enum are reused from
backend.contracts (the job intents live there).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# The 15 canonical fields offered in the UI dropdown (+ "Other" free text).
FIELDS = [
    "Software Engineer", "Data Scientist", "Product Manager", "Consultant",
    "DevOps Engineer", "ML Engineer", "Frontend Engineer", "Backend Engineer",
    "Full-Stack Engineer", "Cybersecurity Analyst", "Cloud Architect",
    "Business Analyst", "UX Designer", "QA Engineer", "Site Reliability Engineer",
]


class SearchProfile(BaseModel):
    """What @observer distilled from the resume / criteria into a search."""
    entry_mode: str                       # "company" | "field" | "resume"
    query: str                            # the search term shown to the user
    titles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    location: Optional[str] = None
    company: Optional[str] = None
    summary: Optional[str] = None         # short profile blurb
    resume_text: Optional[str] = None     # raw resume text (for tailoring)
    source: str = "criteria"              # "resume" | "criteria"


class JobMatch(BaseModel):
    """One ranked real posting from a JobSearchProvider."""
    id: str
    title: str
    company: str
    location: Optional[str] = None
    salary: Optional[str] = None
    url: str                              # apply / detail URL (the honest apply link)
    description: str = ""
    posted: Optional[str] = None
    provider: str = ""
    apply_email: Optional[str] = None     # set only if a real email-apply exists
    fit_score: float = 0.0                # 0..1 vs the profile
    fit_reasons: list[str] = Field(default_factory=list)


class JobMatches(BaseModel):
    profile_query: str
    provider: str
    count: int
    matches: list[JobMatch]


class TailorResult(BaseModel):
    """The tailored resume @tailor produced for a chosen posting."""
    match_id: str
    tailored: bool                        # False if the user declined
    keywords_added: list[str] = Field(default_factory=list)  # REAL overlapping skills emphasized
    gaps: list[str] = Field(default_factory=list)            # posting wants these; NOT on the resume
    markdown: Optional[str] = None
    files: dict[str, str] = Field(default_factory=dict)  # ext -> path under data/
    note: Optional[str] = None


class Application(BaseModel):
    """One application package — honest about submitted vs queued."""
    match_id: str
    title: str
    company: str
    status: str                           # "submitted" | "queued"
    method: str                           # "email" | "apply_link"
    apply_url: Optional[str] = None
    apply_email: Optional[str] = None
    cover_letter: str = ""
    resume_files: dict[str, str] = Field(default_factory=dict)
    detail: str = ""                      # human-readable what-happened


class JobDecision(BaseModel):
    """@commander's outcome for the run."""
    approved_by: str
    proceeded: bool
    chosen_match_id: Optional[str] = None
    submitted: int = 0
    queued: int = 0
