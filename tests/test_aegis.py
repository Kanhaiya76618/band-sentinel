"""
Aegis — deterministic-logic unit tests (stdlib unittest, no extra deps).

Covers the pieces that must stay exact for the demo + pitch numbers:
  * chaos replay  (backend.mockservice.simulate_remediation)
  * cost + MTTR   (the offline run_incident verdict: ~89s / ~$38k)
  * reject-then-fix (scale_pods REJECT -> rollback_and_failover PASS)
  * security sign-off (band_live.cascade._risk_check)

Run:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import unittest

import backend  # triggers .env autoload (harmless offline)
from backend.contracts import Remediation, ValidationResult
from backend.mockservice import (
    SLO_ERROR_RATE, SLO_P99_MS, Scenario, simulate_remediation,
)
from backend.orchestrator import run_incident


class ChaosReplayTests(unittest.TestCase):
    def test_scale_pods_is_rejected(self):
        r = simulate_remediation(Scenario(), "scale_pods", {"pods": 12})
        self.assertFalse(r["passed"])
        self.assertGreater(r["projected_p99_ms"], SLO_P99_MS)   # still breaches
        self.assertTrue(r["regression"])                         # cost up, no real fix

    def test_rollback_and_failover_passes(self):
        r = simulate_remediation(Scenario(), "rollback_and_failover", {"to_region": "us-west-2"})
        self.assertTrue(r["passed"])
        self.assertLessEqual(r["projected_p99_ms"], SLO_P99_MS)
        self.assertLessEqual(r["projected_error_rate"], SLO_ERROR_RATE)

    def test_unknown_action_fails_safe(self):
        r = simulate_remediation(Scenario(), "delete_prod_db", {})
        self.assertFalse(r["passed"])


class IncidentVerdictTests(unittest.TestCase):
    """The offline cascade must land on the canonical pitch numbers."""

    @classmethod
    def setUpClass(cls):
        cls.posted, cls.verdict = asyncio.run(run_incident())

    def test_resolved_by_rollback_and_failover(self):
        self.assertTrue(self.verdict["resolved"])
        self.assertEqual(self.verdict["action"], "rollback_and_failover")

    def test_mttr_is_canonical_89s(self):
        self.assertAlmostEqual(self.verdict["mttr_seconds"], 89.0, delta=0.01)

    def test_cost_averted_is_about_38k(self):
        self.assertAlmostEqual(self.verdict["averted_cost_usd"], 38456.0, delta=5.0)

    def test_reject_then_fix_two_attempts(self):
        intents = [m.intent.value for m in self.posted]
        # exactly two remediations + two validations: one REJECT, then one PASS
        self.assertEqual(intents.count("remediation_proposal"), 2)
        self.assertEqual(intents.count("validation_result"), 2)
        vals = [m.payload.get("passed") for m in self.posted if m.intent.value == "validation_result"]
        self.assertEqual(vals, [False, True])   # reject first, pass second

    def test_nine_step_cascade(self):
        # signal, hypothesis, rem, val, rem, val, approval_request, decision, postmortem
        self.assertEqual(len(self.posted), 9)


class SecuritySignoffTests(unittest.TestCase):
    """band_live security specialist's deterministic risk check (no band SDK import)."""

    def _vr(self, action, params):
        r = simulate_remediation(Scenario(), action, params)
        return ValidationResult(
            action=action, passed=r["passed"], projected_p99_ms=r["projected_p99_ms"],
            projected_error_rate=r["projected_error_rate"], slo_p99_ms=SLO_P99_MS,
            slo_error_rate=SLO_ERROR_RATE, trace=r["trace"])

    def test_rollback_signs_off_low_risk(self):
        from band_live.cascade import _risk_check
        rem = Remediation(action="rollback_and_failover", rationale="x", reversible=False)
        v = _risk_check(rem, self._vr("rollback_and_failover", {"to_region": "us-west-2"}))
        self.assertTrue(v["signed_off"])
        self.assertEqual(v["risk"], "low")

    def test_non_rollback_is_flagged(self):
        from band_live.cascade import _risk_check
        rem = Remediation(action="scale_pods", rationale="x", reversible=True)
        v = _risk_check(rem, self._vr("scale_pods", {"pods": 12}))
        self.assertFalse(v["signed_off"])
        self.assertEqual(v["risk"], "elevated")


class ResumeAnalysisTests(unittest.TestCase):
    """Read-only resume fit analysis: rule-based fallback, never fabricates."""

    PROFILE = {"skills": ["python", "aws", "docker", "postgresql"],
               "resume_text": "Backend engineer. Python services on AWS, Docker, Postgres.",
               "titles": ["Backend Engineer"]}
    JOB = {"title": "Senior Backend Engineer", "company": "Stripe",
           "description": "Want Python, Go, Kubernetes, Kafka, and PostgreSQL."}

    def _analyze(self):
        from jobs.analyze import analyze_fit
        return analyze_fit(self.PROFILE, self.JOB, None)   # None -> rule-based fallback

    def test_fallback_returns_all_sections(self):
        a = self._analyze()
        self.assertEqual(a["source"], "rule-based")
        for key in ("alignment", "score", "strengths", "gaps", "ats_keywords",
                    "clarity_tips", "actions"):
            self.assertIn(key, a)
        self.assertTrue(0 <= a["score"] <= 100)

    def test_strengths_are_only_real_matched_skills(self):
        a = self._analyze()
        blob = " ".join(a["strengths"]).lower()
        self.assertIn("postgresql", blob)
        self.assertIn("python", blob)
        # NEVER fabricate: skills the resume lacks must not appear as strengths
        for invented in ("go", "kubernetes", "kafka"):
            self.assertNotIn(invented, blob)

    def test_gaps_are_advice_not_invented_content(self):
        a = self._analyze()
        self.assertTrue(a["gaps"])
        self.assertTrue(all("consider" in g.lower() for g in a["gaps"]))

    def test_email_summary_is_read_only(self):
        from jobs.analyze import summary_text
        subject, text, html = summary_text(self.JOB, self._analyze())
        self.assertIn("Stripe", subject)
        self.assertIn("not modified", text)   # read-only promise to the user


if __name__ == "__main__":
    unittest.main(verbosity=2)
