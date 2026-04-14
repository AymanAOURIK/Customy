from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

psycopg2_stub = types.ModuleType("psycopg2")
psycopg2_stub.connect = lambda *args, **kwargs: None
psycopg2_stub.extensions = types.SimpleNamespace(connection=object, cursor=object)
psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
psycopg2_extras_stub.RealDictCursor = object
psycopg2_stub.extras = psycopg2_extras_stub
sys.modules.setdefault("psycopg2", psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras_stub)

from app.routes_onboarding import _draft_source_coverage_report, _onboarding_draft_payload
from app.routes_profile import _profile_response, _source_coverage_report_for_profile
from app.source_coverage_report import build_source_coverage_report_from_parsed_text


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
""".strip()


def _draft_data() -> dict[str, object]:
    return {
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


def _draft_row() -> dict[str, object]:
    return {
        "id": "draft-1",
        "status": "draft",
        "source_resume_upload_id": "upload-1",
        "updated_at": "2026-04-14T00:00:00+00:00",
        "draft_data": _draft_data(),
        "gap_analysis": {"skill_count": 3},
    }


def _profile_data() -> dict[str, object]:
    return {
        "user_id": "user-1",
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


class SourceCoverageApiPayloadTests(unittest.TestCase):
    def test_parsed_text_wrapper_returns_none_without_source_text(self):
        self.assertIsNone(
            build_source_coverage_report_from_parsed_text(
                "",
                _draft_data(),
                candidate_source="onboarding_draft",
            )
        )

    @patch("app.routes_onboarding.get_resume_upload")
    def test_onboarding_draft_report_uses_linked_resume_upload(self, mock_get_resume_upload):
        mock_get_resume_upload.return_value = {"parsed_text": _source_resume_text()}

        report = _draft_source_coverage_report("user-1", _draft_row())

        self.assertIsNotNone(report)
        self.assertEqual(report["candidate_source"], "onboarding_draft")
        self.assertEqual(report["counts"]["missing_source_experience_entries"], 1)

    def test_onboarding_draft_payload_only_adds_report_when_provided(self):
        payload_without_report = _onboarding_draft_payload(_draft_row())
        payload_with_report = _onboarding_draft_payload(
            _draft_row(),
            source_coverage_report={"report_version": "source_coverage_report.v1"},
        )

        self.assertNotIn("source_coverage_report", payload_without_report)
        self.assertEqual(
            payload_with_report["source_coverage_report"],
            {"report_version": "source_coverage_report.v1"},
        )

    def test_onboarding_draft_payload_builds_source_aware_plan_when_report_is_provided(self):
        source_coverage_report = build_source_coverage_report_from_parsed_text(
            _source_resume_text(),
            _draft_data(),
            candidate_source="onboarding_draft",
        )
        payload_without_report = _onboarding_draft_payload(_draft_row())
        payload_with_report = _onboarding_draft_payload(
            _draft_row(),
            source_coverage_report=source_coverage_report,
        )
        targets_without_report = {
            target["target_key"]: target
            for target in payload_without_report["profile_enrichment_plan"]["targets"]
        }
        targets_with_report = {
            target["target_key"]: target
            for target in payload_with_report["profile_enrichment_plan"]["targets"]
        }

        self.assertEqual(targets_without_report["scoring_keywords"]["classification"], "auto_derive")
        self.assertEqual(
            targets_with_report["scoring_keywords"]["classification"],
            "recover_from_source_with_confirmation",
        )

    @patch("app.routes_profile.get_resume_upload")
    @patch("app.routes_profile.get_onboarding_draft_db")
    def test_profile_report_uses_linked_onboarding_resume_context(
        self,
        mock_get_onboarding_draft,
        mock_get_resume_upload,
    ):
        mock_get_onboarding_draft.return_value = {"source_resume_upload_id": "upload-1"}
        mock_get_resume_upload.return_value = {"parsed_text": _source_resume_text()}

        report = _source_coverage_report_for_profile("user-1", _profile_data())

        self.assertIsNotNone(report)
        self.assertEqual(report["candidate_source"], "postgres")
        self.assertEqual(report["counts"]["missing_source_experience_entries"], 1)

    def test_profile_response_only_adds_report_when_provided(self):
        response_without_report = _profile_response(_profile_data())
        response_with_report = _profile_response(
            _profile_data(),
            source_coverage_report={"report_version": "source_coverage_report.v1"},
        )

        self.assertNotIn("source_coverage_report", response_without_report)
        self.assertEqual(
            response_with_report["source_coverage_report"],
            {"report_version": "source_coverage_report.v1"},
        )

    def test_profile_response_builds_source_aware_plan_when_report_is_provided(self):
        source_coverage_report = build_source_coverage_report_from_parsed_text(
            _source_resume_text(),
            _profile_data(),
            candidate_source="postgres",
        )
        response_without_report = _profile_response(_profile_data())
        response_with_report = _profile_response(
            _profile_data(),
            source_coverage_report=source_coverage_report,
        )
        targets_without_report = {
            target["target_key"]: target
            for target in response_without_report["profile_enrichment_plan"]["targets"]
        }
        targets_with_report = {
            target["target_key"]: target
            for target in response_with_report["profile_enrichment_plan"]["targets"]
        }

        self.assertEqual(targets_without_report["scoring_keywords"]["classification"], "auto_derive")
        self.assertEqual(
            targets_with_report["scoring_keywords"]["classification"],
            "recover_from_source_with_confirmation",
        )


if __name__ == "__main__":
    unittest.main()
