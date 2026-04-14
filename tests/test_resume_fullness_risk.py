from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.models import ApplicationPack, TailoredExperience
from app.resume_fullness_risk import build_resume_fullness_risk
from app.storage import write_pack


def _candidate_context(*, minimal: bool = False) -> dict[str, object]:
    skills = {
        "languages": ["Python", "SQL"],
        "frameworks": ["FastAPI", "LangChain"],
        "tools": ["Docker", "PostgreSQL", "Airflow", "Power BI"],
        "soft": [] if minimal else ["Stakeholder Communication", "Team Leadership"],
    }
    return {
        "personal": {
            "name": "Ayman Aourik",
            "email": "ayman@example.com",
            "phone": "+212600000000",
            "location": "Casablanca, Morocco",
            "linkedin": "in/aourik-ayman/",
            "github": "",
        },
        "headline": "AI Engineer",
        "summary": "Builds production AI and data systems." if minimal else (
            "AI engineer focused on production automation, data systems, and measurable delivery outcomes."
        ),
        "skills": skills,
        "experiences": [
            {
                "role": "Senior AI Engineer",
                "company": "Acme Labs",
                "start": "2024-01",
                "end": "Present",
                "bullets": [
                    "Built FastAPI and PostgreSQL services that cut triage time by 35% across 14 workflows.",
                ],
            }
        ],
        "education": [] if minimal else [
            {
                "institution": "Mohammadia School of Engineering",
                "degree": "Data Analysis and Mining Engineer",
                "start_year": 2019,
                "end_year": 2022,
                "year": 2022,
            }
        ],
        "spoken_languages": [] if minimal else ["English (Fluent)", "French (Fluent)", "Arabic (Native)"],
        "scoring_keywords": ["python", "sql", "fastapi", "docker"],
        "source_resume_text": "",
        "candidate_source": "candidate_yaml",
    }


def _dense_pack() -> ApplicationPack:
    return ApplicationPack(
        resume_language="en",
        tailored_title="AI & Data Science Lead",
        tailored_summary=(
            "AI and data lead building production systems that automate workflows, improve reliability, "
            "and deliver measurable cost and throughput gains."
        ),
        tailored_experiences=[
            TailoredExperience(
                company="Acme Labs",
                role="Senior AI Engineer",
                start="2024-01",
                end="Present",
                bullets=[
                    "Built FastAPI and PostgreSQL services that cut triage time by 35% across 14 workflows.",
                    "Deployed Docker and Airflow pipelines processing 4M events per month with 99.9% uptime.",
                    "Automated support routing with Python services, saving 60 hours per week across 30 agents.",
                    "Led delivery for 4 engineers and reduced ticket escalations by 25%.",
                ],
            ),
            TailoredExperience(
                company="Beta Systems",
                role="Data Scientist",
                start="2022-01",
                end="2023-12",
                bullets=[
                    "Fine-tuned a local LLM with LoRA adapters, improving new-label accuracy by 18%.",
                    "Built a Dockerized RAG chatbot with ChromaDB and OpenAI for 3 internal teams.",
                    "Developed Power BI dashboards that cut reporting latency by 50%.",
                    "Implemented Selenium and Puppeteer workflows that generated 80K enriched leads.",
                ],
            ),
            TailoredExperience(
                company="Gamma Logistics",
                role="Data Scientist",
                start="2021-01",
                end="2021-12",
                bullets=[
                    "Forecasted demand with XGBoost at 86% accuracy, reducing overstock by 35%.",
                    "Reduced delivery time by 18% and saved $25K per year through routing analysis.",
                    "Built Python analytics workflows that halved reporting time for logistics KPIs.",
                ],
            ),
        ],
        tailored_skills={
            "languages": ["Python", "SQL"],
            "frameworks": ["FastAPI", "LangChain"],
            "tools": ["Docker", "PostgreSQL", "Airflow", "Power BI"],
        },
        cover_letter=None,
        linkedin_message=None,
        email_draft=None,
        focus_areas=[],
        detected_emails=[],
        profile_update_hints=[],
    )


def _generic_pack() -> ApplicationPack:
    return ApplicationPack(
        resume_language="en",
        tailored_title="AI & Data Science Lead",
        tailored_summary=(
            "Delivery-focused leader who improves operations, drives alignment, and keeps execution moving across teams."
        ),
        tailored_experiences=[
            TailoredExperience(
                company="Acme Labs",
                role="Senior AI Engineer",
                start="2024-01",
                end="Present",
                bullets=[
                    "Led cross-functional delivery for customer support operations and aligned priorities with stakeholders.",
                    "Improved process clarity across teams by translating business goals into execution plans.",
                    "Partnered with operations teams to streamline daily workflows and reduce manual coordination.",
                    "Owned roadmap planning and kept delivery moving across multiple streams of work.",
                ],
            ),
            TailoredExperience(
                company="Beta Systems",
                role="Data Scientist",
                start="2022-01",
                end="2023-12",
                bullets=[
                    "Supported platform initiatives across teams and kept project work moving on schedule.",
                    "Worked closely with stakeholders to improve communication and delivery consistency.",
                    "Strengthened process quality by standardizing execution patterns across recurring work.",
                    "Helped teams make better decisions by organizing information and clarifying priorities.",
                ],
            ),
        ],
        tailored_skills={
            "languages": ["Python", "SQL"],
            "frameworks": ["FastAPI", "LangChain"],
            "tools": ["Docker", "PostgreSQL"],
        },
        cover_letter=None,
        linkedin_message=None,
        email_draft=None,
        focus_areas=[],
        detected_emails=[],
        profile_update_hints=[],
    )


def _thin_but_substantive_pack() -> ApplicationPack:
    return ApplicationPack(
        resume_language="en",
        tailored_title="AI Engineer",
        tailored_summary="Builds production automation that saves time and improves reliability.",
        tailored_experiences=[
            TailoredExperience(
                company="Acme Labs",
                role="Senior AI Engineer",
                start="2024-01",
                end="Present",
                bullets=[
                    "Built FastAPI and Docker services that reduced triage time by 35%.",
                    "Automated PostgreSQL reporting pipelines handling 4M events per month.",
                    "Saved 20 hours per week by streamlining support workflows.",
                ],
            )
        ],
        tailored_skills={
            "languages": ["Python", "SQL"],
            "frameworks": ["FastAPI"],
            "tools": ["Docker", "PostgreSQL"],
        },
        cover_letter=None,
        linkedin_message=None,
        email_draft=None,
        focus_areas=[],
        detected_emails=[],
        profile_update_hints=[],
    )


class ResumeFullnessRiskTests(unittest.TestCase):
    def test_dense_pack_returns_clear_report(self):
        report = build_resume_fullness_risk(_candidate_context(), _dense_pack())

        self.assertEqual(report["report_version"], "resume_fullness_risk.v1")
        self.assertEqual(report["overall_status"], "clear")
        self.assertGreaterEqual(report["visual_fill_score"], 80)
        self.assertGreaterEqual(report["substance_score"], 80)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["recommended_action"]["code"], "none")

    def test_generic_pack_can_be_visually_full_but_substantively_weak(self):
        report = build_resume_fullness_risk(_candidate_context(), _generic_pack())

        blocker_codes = {item["code"] for item in report["blockers"]}
        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertEqual(report["overall_status"], "elevated_risk")
        self.assertGreaterEqual(report["visual_fill_score"], 75)
        self.assertLess(report["substance_score"], report["visual_fill_score"])
        self.assertIn("no_quantified_proof", blocker_codes)
        self.assertIn("no_named_system_tool_proof", blocker_codes)
        self.assertIn("low_estimated_word_count", warning_codes)
        self.assertEqual(report["recommended_action"]["code"], "surface_quantified_proof")

    def test_thin_pack_can_have_better_substance_than_visual_fill(self):
        report = build_resume_fullness_risk(_candidate_context(minimal=True), _thin_but_substantive_pack())

        blocker_codes = {item["code"] for item in report["blockers"]}
        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertEqual(report["overall_status"], "elevated_risk")
        self.assertLess(report["visual_fill_score"], report["substance_score"])
        self.assertIn("very_low_work_bullet_count", blocker_codes)
        self.assertIn("recent_roles_visually_thin", blocker_codes)
        self.assertIn("very_low_estimated_word_count", blocker_codes)
        self.assertIn("no_supporting_sections", warning_codes)

    def test_report_accepts_wrapped_pack_payload_and_is_deterministic(self):
        wrapped_pack = {"pack": _dense_pack().model_dump()}
        first = build_resume_fullness_risk(_candidate_context(), wrapped_pack)
        second = build_resume_fullness_risk(_candidate_context(), wrapped_pack)

        self.assertEqual(first, second)

    def test_write_pack_persists_resume_fullness_risk(self):
        pack = _dense_pack()
        report = build_resume_fullness_risk(_candidate_context(), pack)

        with tempfile.TemporaryDirectory() as temp_dir:
            files = write_pack(
                applications_dir=temp_dir,
                slug="acme-ai-engineer-20260414",
                jd_text="Example JD",
                application_url="https://example.com/job",
                pack=pack,
                tex_string="\\documentclass{article}\\begin{document}x\\end{document}",
                requested_outputs=["resume"],
                candidate_name="Ayman Aourik",
                usage_summary={"total_tokens": 123},
                initial_analysis={"score": 75},
                updated_analysis={"score": 82},
                resume_fullness_risk=report,
            )

            generated_path = Path(files["generated_json"])
            payload = json.loads(generated_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["resume_fullness_risk"], report)


if __name__ == "__main__":
    unittest.main()
