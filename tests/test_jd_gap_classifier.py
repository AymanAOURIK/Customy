from __future__ import annotations

import unittest

from app.jd_gap_classifier import classify_jd_gaps
from app.source_coverage_report import build_source_coverage_report_from_profile_data
from app.source_signal_index import build_source_signal_index


def _candidate_context() -> dict[str, object]:
    return {
        "personal": {
            "name": "Ayman Aourik",
            "email": "ayman@example.com",
            "phone": "",
            "location": "Casablanca, Morocco",
            "linkedin": "",
            "github": "",
        },
        "headline": "Senior AI Engineer",
        "summary": "Builds reliable automation and retrieval systems for internal operations.",
        "skills": {
            "languages": ["Python", "SQL"],
            "frameworks": ["FastAPI"],
            "tools": ["Docker", "OpenAI"],
            "soft": ["Ownership"],
        },
        "experiences": [
            {
                "role": "Senior AI Engineer",
                "company": "Acme Labs",
                "start": "2024-01",
                "end": "Present",
                "bullets": [
                    "Built Python and FastAPI services for internal automation.",
                    "Shipped AI agent workflows with OpenAI and ChromaDB for knowledge retrieval.",
                ],
            },
            {
                "role": "Data Engineer",
                "company": "Beta Systems",
                "start": "2022-01",
                "end": "2023-12",
                "bullets": [
                    "Maintained SQL reporting pipelines for finance stakeholders.",
                ],
            },
        ],
        "education": [],
        "spoken_languages": ["English (Fluent)", "French (Fluent)"],
        "scoring_keywords": ["python", "docker", "rag"],
        "source_resume_text": "",
        "candidate_source": "postgres",
    }


def _source_text_with_langchain() -> str:
    return """
PROFESSIONAL EXPERIENCE
Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built Python and FastAPI services for internal automation.

PROJECTS
Assistant search
- Built LangChain workflows with OpenAI and ChromaDB for knowledge retrieval.
""".strip()


class JdGapClassifierTests(unittest.TestCase):
    def test_classifier_returns_explicit_and_derived_matches_from_structured_profile(self):
        jd_analysis = {
            "role": "Senior AI Engineer",
            "keyword_signals": ["Python", "vector databases", "AI agents"],
            "top_requirements": [
                "Hands-on Python experience building internal automation.",
                "Experience with vector databases and AI agents.",
            ],
        }

        result = classify_jd_gaps(jd_analysis, _candidate_context())
        per_term = {item["term"]: item for item in result["per_term_classifications"]}

        self.assertEqual(per_term["Senior AI Engineer"]["classification"], "explicit_match")
        self.assertEqual(per_term["Python"]["classification"], "explicit_match")
        self.assertEqual(per_term["vector databases"]["classification"], "derived_match")
        self.assertEqual(per_term["AI agents"]["classification"], "derived_match")
        self.assertEqual(
            per_term["Experience with vector databases and AI agents."]["classification"],
            "derived_match",
        )
        self.assertEqual(result["summary"]["counts"]["explicit_match"], 3)
        self.assertEqual(result["summary"]["counts"]["derived_match"], 3)
        self.assertEqual(result["recommended_generation_status"], "ready")

    def test_classifier_marks_source_only_tool_evidence_as_recoverable(self):
        candidate_context = _candidate_context()
        candidate_context["experiences"] = [
            {
                "role": "Senior AI Engineer",
                "company": "Acme Labs",
                "start": "2024-01",
                "end": "Present",
                "bullets": [
                    "Built Python and FastAPI services for internal automation.",
                    "Shipped OpenAI retrieval workflows for knowledge search.",
                ],
            }
        ]

        source_index = build_source_signal_index(_source_text_with_langchain())
        source_report = build_source_coverage_report_from_profile_data(source_index, candidate_context)

        result = classify_jd_gaps(
            {"keyword_signals": ["LangChain"], "top_requirements": ["Experience with LangChain and OpenAI."]},
            candidate_context,
            source_coverage_report=source_report,
            source_signal_index=source_index,
        )
        per_term = {item["term"]: item for item in result["per_term_classifications"]}

        self.assertEqual(per_term["LangChain"]["classification"], "recoverable_from_source")
        self.assertEqual(
            per_term["Experience with LangChain and OpenAI."]["classification"],
            "recoverable_from_source",
        )
        self.assertEqual(result["summary"]["counts"]["recoverable_from_source"], 2)
        self.assertEqual(result["recommended_generation_status"], "review_before_generation")

    def test_classifier_keeps_unsupported_terms_as_true_gaps(self):
        result = classify_jd_gaps(
            {"keyword_signals": ["Kubernetes"], "top_requirements": ["Production Kubernetes experience."]},
            _candidate_context(),
        )
        per_term = {item["term"]: item for item in result["per_term_classifications"]}

        self.assertEqual(per_term["Kubernetes"]["classification"], "true_gap")
        self.assertEqual(per_term["Production Kubernetes experience."]["classification"], "true_gap")
        self.assertEqual(result["summary"]["counts"]["true_gap"], 2)
        self.assertEqual(result["recommended_generation_status"], "generate_with_true_gaps")

    def test_requirement_becomes_true_gap_when_one_signal_remains_unsupported(self):
        candidate_context = _candidate_context()
        candidate_context["skills"]["tools"] = ["Docker"]
        candidate_context["experiences"] = [
            {
                "role": "Senior AI Engineer",
                "company": "Acme Labs",
                "start": "2024-01",
                "end": "Present",
                "bullets": [
                    "Built Python services for internal automation.",
                ],
            }
        ]
        source_index = build_source_signal_index(_source_text_with_langchain())
        source_report = build_source_coverage_report_from_profile_data(source_index, candidate_context)

        result = classify_jd_gaps(
            {"top_requirements": ["Experience with LangChain and Kubernetes."]},
            candidate_context,
            source_coverage_report=source_report,
            source_signal_index=source_index,
        )

        requirement = result["per_term_classifications"][0]
        signal_outcomes = {item["signal"]: item["classification"] for item in requirement["signal_outcomes"]}

        self.assertEqual(requirement["classification"], "true_gap")
        self.assertEqual(signal_outcomes["LangChain"], "recoverable_from_source")
        self.assertEqual(signal_outcomes["Kubernetes"], "true_gap")
        self.assertEqual(result["recommended_generation_status"], "generate_with_true_gaps")

    def test_classifier_is_deterministic_for_same_inputs(self):
        jd_analysis = {
            "role": "Senior AI Engineer",
            "keyword_signals": ["Python", "vector databases", "LangChain"],
            "top_requirements": [
                "Hands-on Python experience.",
                "Experience with vector databases and LangChain.",
            ],
        }
        source_index = build_source_signal_index(_source_text_with_langchain())
        source_report = build_source_coverage_report_from_profile_data(source_index, _candidate_context())

        self.assertEqual(
            classify_jd_gaps(
                jd_analysis,
                _candidate_context(),
                source_coverage_report=source_report,
                source_signal_index=source_index,
            ),
            classify_jd_gaps(
                jd_analysis,
                _candidate_context(),
                source_coverage_report=source_report,
                source_signal_index=source_index,
            ),
        )


if __name__ == "__main__":
    unittest.main()
