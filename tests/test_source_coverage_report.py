from __future__ import annotations

import unittest

from app.source_coverage_report import (
    build_source_coverage_report,
    build_source_coverage_report_from_profile_data,
)
from app.source_signal_index import build_source_signal_index


def _source_resume_text() -> str:
    return """
SUMMARY
AI Engineer focused on reliable automation and data systems.

PROFESSIONAL EXPERIENCE
Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.
- Deployed Airflow pipelines handling 4M events per month with 99.9% uptime.

Data Engineer | Beta Systems | 2022 - 2023
- Maintained PostgreSQL jobs processing 18M rows per day for finance reporting.

PROJECTS
RAG Assistant
- Built with LangChain, OpenAI, and ChromaDB for 3 internal teams.

CERTIFICATIONS
AWS Certified Cloud Practitioner
""".strip()


def _candidate_context() -> dict[str, object]:
    return {
        "personal": {
            "name": "Ayman Aourik",
            "email": "ayman@example.com",
            "phone": "",
            "location": "",
            "linkedin": "",
            "github": "",
        },
        "headline": "Data Engineer",
        "summary": "Maintains reliable data workflows.",
        "skills": {
            "languages": ["SQL"],
            "frameworks": [],
            "tools": ["Airflow"],
            "soft": [],
        },
        "experiences": [
            {
                "role": "Data Engineer",
                "company": "Beta Systems",
                "start": "2022-01",
                "end": "2023-12",
                "bullets": [
                    "Maintained postgres and Airflow jobs processing 18 million rows per day for finance reporting.",
                ],
            }
        ],
        "education": [],
        "spoken_languages": [],
        "scoring_keywords": [],
        "source_resume_text": "",
        "candidate_source": "postgres",
    }


class SourceCoverageReportTests(unittest.TestCase):
    def test_report_detects_missing_experience_optional_sections_tools_and_metrics(self):
        source_index = build_source_signal_index(_source_resume_text())
        draft_data = {
            "full_name": "Ayman Aourik",
            "email": "ayman@example.com",
            "headline": "AI Engineer",
            "summary": "Builds reliable automation systems.",
            "skills": {
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
                "soft": [],
            },
            "experiences": [
                {
                    "role": "Senior AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": [
                        "Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.",
                    ],
                }
            ],
            "education": [],
            "spoken_languages": [],
            "scoring_keywords": [],
        }

        report = build_source_coverage_report_from_profile_data(
            source_index,
            draft_data,
            candidate_source="onboarding_draft",
        )

        self.assertEqual(report["report_version"], "source_coverage_report.v1")
        self.assertEqual(report["candidate_source"], "onboarding_draft")
        self.assertEqual(report["overall_status"], "review")
        self.assertEqual(report["counts"]["source_experience_entries"], 2)
        self.assertEqual(report["counts"]["matched_source_experience_entries"], 1)
        self.assertEqual(report["counts"]["missing_source_experience_entries"], 1)
        self.assertEqual(report["counts"]["missing_optional_sections"], 2)
        self.assertEqual(report["counts"]["missing_metric_lines"], 2)

        self.assertEqual(
            report["missing_source_experiences"],
            [
                {
                    "source_experience_position": 1,
                    "label": "Data Engineer @ Beta Systems",
                    "role": "Data Engineer",
                    "organization": "Beta Systems",
                    "date_text": "2022 - 2023",
                    "line_start": 9,
                    "line_end": 10,
                    "metric_line_count": 1,
                    "tool_terms": ["PostgreSQL"],
                    "reason": "no_confident_structured_experience_match",
                }
            ],
        )
        self.assertEqual(
            [item["section_key"] for item in report["missing_optional_sections"]],
            ["projects", "certifications"],
        )

        missing_terms = {item["term"] for item in report["missing_tool_terms"]}
        self.assertTrue(
            {"Airflow", "PostgreSQL", "LangChain", "OpenAI", "ChromaDB", "AWS"}.issubset(missing_terms)
        )

        missing_metric_texts = {item["text"] for item in report["missing_metric_evidence"]}
        self.assertEqual(
            missing_metric_texts,
            {
                "- Deployed Airflow pipelines handling 4M events per month with 99.9% uptime.",
                "- Maintained PostgreSQL jobs processing 18M rows per day for finance reporting.",
            },
        )

        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertIn("optional_section_fields_not_modeled", warning_codes)

    def test_report_accepts_canonical_candidate_context_and_alias_metric_matches(self):
        source_text = """
PROFESSIONAL EXPERIENCE
Data Engineer | Beta Systems | 2022 - 2023
- Maintained PostgreSQL and Airflow jobs processing 18 million rows per day for finance reporting.
""".strip()
        source_index = build_source_signal_index(source_text)

        report = build_source_coverage_report(source_index, _candidate_context())

        self.assertEqual(report["candidate_source"], "postgres")
        self.assertEqual(report["overall_status"], "covered")
        self.assertEqual(report["missing_source_experiences"], [])
        self.assertEqual(report["missing_optional_sections"], [])
        self.assertEqual(report["missing_tool_terms"], [])
        self.assertEqual(report["missing_metric_evidence"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["blockers"], [])

    def test_optional_sections_are_not_flagged_when_profile_provides_supported_fields(self):
        source_index = build_source_signal_index(_source_resume_text())
        profile_data = {
            "full_name": "Ayman Aourik",
            "headline": "AI Engineer",
            "summary": "Builds reliable automation systems.",
            "skills": {
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
                "soft": [],
            },
            "experiences": [
                {
                    "role": "Senior AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": [
                        "Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.",
                    ],
                }
            ],
            "projects": [
                {
                    "name": "RAG Assistant",
                    "bullets": [
                        "Built with LangChain, OpenAI, and ChromaDB for 3 internal teams.",
                    ],
                }
            ],
            "certifications": ["AWS Certified Cloud Practitioner"],
            "education": [],
            "spoken_languages": [],
            "scoring_keywords": [],
        }

        report = build_source_coverage_report_from_profile_data(source_index, profile_data)

        self.assertEqual(report["missing_optional_sections"], [])
        self.assertNotIn(
            "optional_section_fields_not_modeled",
            {item["code"] for item in report["warnings"]},
        )

    def test_report_is_deterministic_for_same_inputs(self):
        source_index = build_source_signal_index(_source_resume_text())
        profile_data = {
            "full_name": "Ayman Aourik",
            "headline": "AI Engineer",
            "summary": "Builds reliable automation systems.",
            "skills": {
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "tools": ["Docker"],
                "soft": [],
            },
            "experiences": [
                {
                    "role": "Senior AI Engineer",
                    "company": "Acme Labs",
                    "start": "2024-01",
                    "end": "Present",
                    "bullets": [
                        "Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.",
                    ],
                }
            ],
            "education": [],
            "spoken_languages": [],
            "scoring_keywords": [],
        }

        self.assertEqual(
            build_source_coverage_report_from_profile_data(source_index, profile_data),
            build_source_coverage_report_from_profile_data(source_index, profile_data),
        )


if __name__ == "__main__":
    unittest.main()
