"""
Aegis — resume parsing (Phase 3).

Turn a real uploaded resume (PDF via pdfplumber, DOCX via python-docx) into a
structured profile: titles, skills, seniority, a short summary, plus the raw
text for downstream tailoring. The LLM enriches the extraction when a live
provider is configured; a deterministic keyword/heuristic pass is the offline
fallback so the workflow runs with zero keys.

Unsupported formats or unreadable files raise ``ResumeError`` — we never invent
a profile.
"""
from __future__ import annotations

import json
import re
from io import BytesIO

# A compact, practical skills vocabulary for the heuristic pass.
SKILL_VOCAB = [
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++",
    "c#", "ruby", "php", "scala", "kotlin", "swift", "sql", "nosql",
    "react", "vue", "angular", "node", "django", "flask", "fastapi", "spring",
    "aws", "gcp", "azure", "kubernetes", "docker", "terraform", "ansible",
    "ci/cd", "jenkins", "github actions", "linux", "bash",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "kafka", "spark",
    "hadoop", "airflow", "snowflake", "dbt", "tableau", "power bi", "excel",
    "machine learning", "deep learning", "pytorch", "tensorflow", "scikit-learn",
    "nlp", "llm", "pandas", "numpy", "data analysis", "statistics",
    "product management", "agile", "scrum", "jira", "roadmap", "stakeholder",
    "figma", "ux", "ui", "user research", "wireframe", "prototyping",
    "security", "penetration testing", "siem", "incident response", "soc",
    "rest", "graphql", "microservices", "distributed systems", "observability",
]

SENIORITY = ["intern", "junior", "associate", "mid", "senior", "staff", "principal", "lead", "manager", "director"]


class ResumeError(ValueError):
    """The upload couldn't be read into resume text."""


def extract_text(content: bytes, filename: str = "") -> str:
    """Extract plain text from a PDF or DOCX upload."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf" or content[:5] == b"%PDF-":
        try:
            import pdfplumber
            with pdfplumber.open(BytesIO(content)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception as e:
            raise ResumeError(f"Could not read PDF: {e}") from e
    elif ext in ("docx", "doc") or content[:2] == b"PK":
        try:
            import docx
            d = docx.Document(BytesIO(content))
            text = "\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            raise ResumeError(f"Could not read DOCX: {e}") from e
    else:
        # Plain text resume is acceptable too.
        try:
            text = content.decode("utf-8", "replace")
        except Exception as e:
            raise ResumeError(f"Unsupported resume format '{ext or 'unknown'}': {e}") from e
    if not text.strip():
        raise ResumeError("Resume parsed to empty text — is the file a scanned image?")
    return text


def heuristic_profile(text: str) -> dict:
    low = text.lower()
    skills = sorted({s for s in SKILL_VOCAB if re.search(r"\b" + re.escape(s) + r"\b", low)})
    seniority = next((s for s in reversed(SENIORITY) if s in low), None)

    # Titles: lines that look like role headings.
    titles: list[str] = []
    role_re = re.compile(
        r"\b(engineer|developer|scientist|manager|analyst|consultant|architect|designer|"
        r"administrator|specialist|lead|director|sre|devops)\b", re.I)
    for line in text.splitlines():
        s = line.strip()
        if 3 <= len(s) <= 60 and role_re.search(s) and not s.endswith("."):
            titles.append(s)
        if len(titles) >= 5:
            break

    summary = re.sub(r"\s+", " ", text.strip())[:400]
    return {
        "titles": titles[:5],
        "skills": skills[:25],
        "seniority": seniority,
        "summary": summary,
    }


def _llm_profile(text: str, llm) -> dict | None:
    """Ask the LLM to extract a structured profile as JSON. None on failure."""
    if llm is None:
        return None
    try:
        out = llm.complete(
            system=("You extract a structured profile from a resume. Reply ONLY with "
                    "JSON: {\"titles\":[...],\"skills\":[...],\"seniority\":\"...\","
                    "\"summary\":\"one sentence\"}."),
            user=text[:6000], role="@observer", tag="resume",
        )
        # OfflineLLM echoes the prompt back; only accept real JSON objects.
        start, end = out.find("{"), out.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(out[start:end + 1])
        if not isinstance(data, dict) or "skills" not in data:
            return None
        return {
            "titles": [str(t) for t in data.get("titles", [])][:5],
            "skills": [str(s).lower() for s in data.get("skills", [])][:25],
            "seniority": data.get("seniority"),
            "summary": (data.get("summary") or "")[:400],
        }
    except Exception:
        return None


def parse_profile(content: bytes, filename: str, llm=None) -> dict:
    """Full pipeline: bytes -> text -> structured profile (LLM, else heuristic)."""
    text = extract_text(content, filename)
    profile = _llm_profile(text, llm) or heuristic_profile(text)
    profile["resume_text"] = text
    if not profile.get("skills") and not profile.get("titles"):
        raise ResumeError(
            "Parsed the resume but found no recognizable skills or titles. "
            "Provide a text-based (not scanned) PDF/DOCX."
        )
    return profile
