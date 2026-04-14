from __future__ import annotations

import unittest

from app.profile_readiness import evaluate_saved_profile_readiness


def _saved_profile(**overrides):
    profile = {
        "full_name": "Ayman Aourik",
        "email": "ayman@example.com",
        "headline": "AI Engineer",
        "summary": "Builds reliable automation and data systems.",
        "skills": {
            "languages": ["Python", "SQL", "TypeScript"],
            "frameworks": ["FastAPI", "Django", "React"],
            "tools": ["Docker", "Kubernetes", "Airflow"],
            "soft": ["Ownership"],
        },
        "experiences": [
            {
                "role": "Senior AI Engineer",
                "company": "Acme Labs",
                "start": "2024-01",
                "end": "Present",
                "bullets": [
                    "Built Python and FastAPI services that reduced triage time by 35% across 14 workflows.",
                    "Deployed Docker and Kubernetes pipelines that handled 4M events per month with 99.9% uptime.",
                    "Automated SQL quality checks in BigQuery, cutting data defects by 42% for 12 teams.",
                    "Implemented Airflow monitoring that reduced failed runs by 55% on 28 pipelines.",
                ],
            },
            {
                "role": "Data Engineer",
                "company": "Beta Systems",
                "start": "2022-01",
                "end": "2023-12",
                "bullets": [
                    "Maintained PostgreSQL and Airflow jobs that processed 18M rows per day for finance reporting.",
                    "Shipped React dashboards backed by FastAPI APIs, reducing analyst wait time by 48%.",
                    "Standardized Docker-based CI pipelines and lowered deployment errors by 60% across 9 services.",
                    "Introduced Grafana alerts for Kubernetes workloads and cut incident response time by 30%.",
                ],
            },
            {
                "role": "Software Engineer",
                "company": "Gamma Tech",
                "start": "2020-01",
                "end": "2021-12",
                "bullets": [
                    "Delivered TypeScript tooling that reduced manual QA effort by 25% on customer releases.",
                    "Built Django admin automations and saved 8 hours per week for operations teams.",
                    "Improved SQL reporting jobs and shortened refresh latency by 33% across 6 datasets.",
                    "Documented Docker runbooks that reduced onboarding time by 40% for new engineers.",
                ],
            },
        ],
        "education": [{"degree": "MSc Computer Science", "institution": "Example University", "year": "2020"}],
        "spoken_languages": ["English (Fluent)", "French (Fluent)"],
        "scoring_keywords": [
            "python",
            "sql",
            "fastapi",
            "docker",
            "kubernetes",
            "airflow",
            "react",
            "analytics",
        ],
    }
    profile.update(overrides)
    return profile


class ProfileReadinessGateTests(unittest.TestCase):
    def test_blocked_profile_returns_blocked_gate_and_report(self):
        result = evaluate_saved_profile_readiness({})

        self.assertEqual(set(result.keys()), {"profile_readiness_gate", "profile_quality_report"})
        self.assertEqual(
            result["profile_readiness_gate"],
            {
                "decision": "blocked",
                "status": "blocked",
                "rule": "profile_quality_report.overall_status",
            },
        )
        self.assertEqual(result["profile_quality_report"]["overall_status"], "blocked")

    def test_review_profile_allows_generation(self):
        review_profile = _saved_profile(
            email="",
            skills={
                "languages": ["Python", "SQL"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
                "soft": [],
            },
            experiences=[
                {
                    "role": "AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": [
                        "Built Python and Docker services that reduced manual processing time by 35%.",
                        "Implemented SQL analytics pipelines in BigQuery for 12 product teams.",
                    ],
                },
                {
                    "role": "Data Engineer",
                    "company": "Beta Systems",
                    "start": "2022-01",
                    "end": "2023-12",
                    "bullets": [
                        "Automated ETL jobs with Airflow and PostgreSQL, cutting failures by 42%.",
                        "Maintained Grafana monitoring for 20 workflows and reduced alert noise by 30%.",
                    ],
                },
            ],
            scoring_keywords=["python", "sql", "airflow"],
        )

        result = evaluate_saved_profile_readiness(review_profile)

        self.assertEqual(result["profile_readiness_gate"]["decision"], "allow")
        self.assertEqual(result["profile_readiness_gate"]["status"], "review")
        self.assertEqual(result["profile_quality_report"]["overall_status"], "review")

    def test_ready_profile_allows_generation(self):
        result = evaluate_saved_profile_readiness(_saved_profile())

        self.assertEqual(result["profile_readiness_gate"]["decision"], "allow")
        self.assertEqual(result["profile_readiness_gate"]["status"], "ready")
        self.assertEqual(result["profile_quality_report"]["overall_status"], "ready")


if __name__ == "__main__":
    unittest.main()
