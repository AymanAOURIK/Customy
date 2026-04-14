from __future__ import annotations

import unittest

from app.candidate_context import build_candidate_context_from_profile_data
from app.profile_enrichment import build_profile_enrichment_plan
from app.profile_quality import build_profile_quality_report
from app.source_coverage_report import build_source_coverage_report_from_parsed_text


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
        "source_resume_text": "",
    }
    profile.update(overrides)
    return profile


def _source_report_for(profile: dict, parsed_text: str) -> dict[str, object] | None:
    return build_source_coverage_report_from_parsed_text(
        parsed_text,
        profile,
        candidate_source="postgres",
    )


def _plan_for(
    profile: dict,
    *,
    source_coverage_report: dict[str, object] | None = None,
) -> dict[str, object]:
    candidate_context = build_candidate_context_from_profile_data(
        profile,
        candidate_source="postgres",
    )
    report = build_profile_quality_report(candidate_context)
    return build_profile_enrichment_plan(
        report,
        profile,
        source_coverage_report=source_coverage_report,
        candidate_source="postgres",
    )


class ProfileEnrichmentPlanTests(unittest.TestCase):
    def test_ready_profile_has_no_targets(self):
        plan = _plan_for(_saved_profile())

        self.assertEqual(plan["overall_status"], "ready")
        self.assertEqual(plan["summary"]["total_targets"], 0)
        self.assertEqual(plan["targets"], [])

    def test_missing_positioning_and_keywords_create_auto_derive_targets(self):
        plan = _plan_for(
            _saved_profile(
                headline="",
                summary="",
                scoring_keywords=[],
            )
        )

        targets = {target["target_key"]: target for target in plan["targets"]}

        self.assertEqual(plan["summary"]["classification_counts"]["auto_derive"], 3)
        self.assertEqual(targets["scoring_keywords"]["classification"], "auto_derive")
        self.assertEqual(targets["summary"]["classification"], "auto_derive")
        self.assertEqual(targets["headline"]["classification"], "auto_derive")
        self.assertEqual(targets["scoring_keywords"]["priority_rank"], 1)
        self.assertEqual(targets["summary"]["priority_rank"], 2)
        self.assertEqual(targets["headline"]["priority_rank"], 3)

    def test_recent_evidence_gaps_with_source_resume_become_recovery_targets(self):
        profile = _saved_profile(
            experiences=[
                {
                    "role": "AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": ["Built internal automation for operations."],
                },
                {
                    "role": "Data Engineer",
                    "company": "Beta Systems",
                    "start": "2022-01",
                    "end": "2023-12",
                    "bullets": ["Maintained reporting pipelines for the finance team."],
                },
            ],
            source_resume_text=(
                "AI Engineer at Acme Labs. Built FastAPI services and Docker pipelines "
                "supporting 2M requests per month. Data Engineer at Beta Systems. "
                "Used Airflow and PostgreSQL for 18M rows per day."
            ),
        )

        plan = _plan_for(profile)
        targets = {target["target_key"]: target for target in plan["targets"]}

        self.assertEqual(
            targets["recent_role_depth"]["classification"],
            "recover_from_source_with_confirmation",
        )
        self.assertEqual(
            targets["recent_quantified_proof"]["classification"],
            "recover_from_source_with_confirmation",
        )
        self.assertEqual(
            targets["recent_named_system_proof"]["classification"],
            "recover_from_source_with_confirmation",
        )

    def test_recent_evidence_gaps_without_source_resume_fall_back_to_user_questions(self):
        profile = _saved_profile(
            skills={"languages": [], "frameworks": [], "tools": [], "soft": []},
            scoring_keywords=[],
            experiences=[
                {
                    "role": "AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": ["Worked on internal platform improvements."],
                },
                {
                    "role": "Data Engineer",
                    "company": "Beta Systems",
                    "start": "2022-01",
                    "end": "2023-12",
                    "bullets": ["Supported finance reporting workflows."],
                },
            ],
            source_resume_text="",
        )

        plan = _plan_for(profile)
        targets = {target["target_key"]: target for target in plan["targets"]}

        self.assertEqual(targets["recent_role_depth"]["classification"], "ask_user")
        self.assertEqual(targets["recent_quantified_proof"]["classification"], "ask_user")
        self.assertEqual(targets["recent_named_system_proof"]["classification"], "ask_user")
        self.assertEqual(targets["scoring_keywords"]["classification"], "ask_user")

    def test_source_coverage_keyword_gap_prefers_recovery_over_auto_derive(self):
        profile = _saved_profile(
            scoring_keywords=[],
            skills={
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
                "soft": ["Ownership"],
            },
            experiences=[
                {
                    "role": "Senior AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": [
                        "Built FastAPI and Docker services that improved operational reliability.",
                    ],
                },
                {
                    "role": "Data Engineer",
                    "company": "Beta Systems",
                    "start": "2022-01",
                    "end": "2023-12",
                    "bullets": [
                        "Maintained reporting pipelines for the finance team.",
                    ],
                },
            ],
            source_resume_text="",
        )
        source_report = _source_report_for(
            profile,
            """
PROFESSIONAL EXPERIENCE
Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.
- Deployed Airflow and Kubernetes pipelines handling 4M events per month with 99.9% uptime.

Data Engineer | Beta Systems | 2022 - 2023
- Maintained PostgreSQL jobs processing 18M rows per day for finance reporting.
            """.strip(),
        )

        plan = _plan_for(profile, source_coverage_report=source_report)
        targets = {target["target_key"]: target for target in plan["targets"]}

        self.assertTrue(plan["source_awareness"]["enabled"])
        self.assertGreater(plan["source_awareness"]["gap_counts"]["missing_tool_terms"], 0)
        self.assertEqual(
            targets["scoring_keywords"]["classification"],
            "recover_from_source_with_confirmation",
        )
        self.assertEqual(
            targets["hard_skill_inventory"]["classification"],
            "recover_from_source_with_confirmation",
        )

    def test_source_coverage_without_recent_gaps_switches_recent_targets_to_user_questions(self):
        profile = _saved_profile(
            skills={"languages": [], "frameworks": [], "tools": [], "soft": []},
            scoring_keywords=[],
            experiences=[
                {
                    "role": "AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": ["Built internal automation for operations."],
                },
                {
                    "role": "Data Engineer",
                    "company": "Beta Systems",
                    "start": "2022-01",
                    "end": "2023-12",
                    "bullets": ["Maintained reporting pipelines for the finance team."],
                },
            ],
            source_resume_text=(
                "AI Engineer at Acme Labs. Built internal automation for operations. "
                "Data Engineer at Beta Systems. Maintained reporting pipelines for the finance team."
            ),
        )
        source_report = _source_report_for(
            profile,
            """
PROFESSIONAL EXPERIENCE
AI Engineer | Acme Labs | Jan 2024 - Present
- Built internal automation for operations.

Data Engineer | Beta Systems | 2022 - 2023
- Maintained reporting pipelines for the finance team.
            """.strip(),
        )

        plan_without_report = _plan_for(profile)
        plan_with_report = _plan_for(profile, source_coverage_report=source_report)
        targets_without_report = {target["target_key"]: target for target in plan_without_report["targets"]}
        targets_with_report = {target["target_key"]: target for target in plan_with_report["targets"]}

        self.assertEqual(
            targets_without_report["recent_role_depth"]["classification"],
            "recover_from_source_with_confirmation",
        )
        self.assertEqual(
            targets_with_report["recent_role_depth"]["classification"],
            "ask_user",
        )
        self.assertEqual(
            targets_with_report["recent_quantified_proof"]["classification"],
            "ask_user",
        )
        self.assertEqual(
            targets_with_report["recent_named_system_proof"]["classification"],
            "ask_user",
        )

    def test_source_coverage_positioning_gap_switches_summary_and_headline_to_recovery(self):
        profile = _saved_profile(
            headline="",
            summary="",
            source_resume_text="",
        )
        source_report = _source_report_for(
            profile,
            """
PROFESSIONAL EXPERIENCE
Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built Python and FastAPI services that reduced triage time by 35% across 14 workflows.

Data Engineer | Beta Systems | 2022 - 2023
- Maintained PostgreSQL and Airflow jobs processing 18M rows per day for finance reporting.

Software Engineer | Gamma Tech | 2020 - 2021
- Delivered TypeScript tooling that reduced manual QA effort by 25% on customer releases.

Platform Engineer | Delta Ops | 2018 - 2019
- Built Kubernetes migration tooling for 6 production services.
            """.strip(),
        )

        plan_without_report = _plan_for(profile)
        plan_with_report = _plan_for(profile, source_coverage_report=source_report)
        targets_without_report = {target["target_key"]: target for target in plan_without_report["targets"]}
        targets_with_report = {target["target_key"]: target for target in plan_with_report["targets"]}

        self.assertEqual(targets_without_report["summary"]["classification"], "auto_derive")
        self.assertEqual(targets_without_report["headline"]["classification"], "auto_derive")
        self.assertEqual(
            targets_with_report["summary"]["classification"],
            "recover_from_source_with_confirmation",
        )
        self.assertEqual(
            targets_with_report["headline"]["classification"],
            "recover_from_source_with_confirmation",
        )


if __name__ == "__main__":
    unittest.main()
