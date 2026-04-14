from __future__ import annotations

import unittest

from app.source_signal_index import build_source_signal_index


class SourceSignalIndexTests(unittest.TestCase):
    def test_index_detects_sections_optional_sections_and_experience_signals(self):
        parsed_text = """
AYMAN AOURIK
Casablanca, Morocco | ayman@example.com

SUMMARY
AI Engineer focused on reliable automation and data systems.

PROFESSIONAL EXPERIENCE
Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.
- Deployed Airflow pipelines handling 4M events per month with 99.9% uptime.

Data Engineer | Beta Systems | 2022 - 2023
- Maintained PostgreSQL jobs processing 18M rows per day for finance reporting.
- Shipped React dashboards for 12 analysts and leadership stakeholders.

PROJECTS
RAG Assistant
- Built with LangChain, OpenAI, and ChromaDB.

CERTIFICATIONS
AWS Certified Cloud Practitioner

SKILLS: Python, SQL, Docker, Kubernetes, Power BI
""".strip()

        index = build_source_signal_index(parsed_text)

        self.assertEqual(index["index_version"], "source_signal_index.v1")
        self.assertEqual(
            [section["section_key"] for section in index["sections_detected"]],
            ["summary", "experience", "projects", "certifications", "skills"],
        )
        self.assertEqual(index["optional_sections_detected"], ["projects", "certifications"])
        self.assertEqual(index["counts"]["experience_entries"], 2)

        first_entry = index["experience_entries"][0]
        second_entry = index["experience_entries"][1]

        self.assertEqual(first_entry["role"], "Senior AI Engineer")
        self.assertEqual(first_entry["organization"], "Acme Labs")
        self.assertEqual(first_entry["bullet_count_estimate"], 2)
        self.assertEqual(first_entry["metric_line_count"], 2)
        self.assertEqual(
            first_entry["tool_system_terms"],
            ["FastAPI", "Docker", "Airflow"],
        )

        self.assertEqual(second_entry["role"], "Data Engineer")
        self.assertEqual(second_entry["organization"], "Beta Systems")
        self.assertEqual(second_entry["bullet_count_estimate"], 2)
        self.assertEqual(second_entry["metric_line_count"], 2)
        self.assertEqual(
            second_entry["tool_system_terms"],
            ["PostgreSQL", "React"],
        )

        detected_terms = {item["term"] for item in index["tool_system_terms"]}
        self.assertTrue(
            {
                "FastAPI",
                "Docker",
                "Airflow",
                "PostgreSQL",
                "React",
                "LangChain",
                "OpenAI",
                "ChromaDB",
                "AWS",
                "Python",
                "SQL",
                "Kubernetes",
                "Power BI",
            }.issubset(detected_terms)
        )

        metric_texts = [item["text"] for item in index["metric_bearing_lines"]]
        self.assertIn(
            "- Built FastAPI and Docker services that reduced triage time by 35% across 14 workflows.",
            metric_texts,
        )
        self.assertIn(
            "- Deployed Airflow pipelines handling 4M events per month with 99.9% uptime.",
            metric_texts,
        )
        self.assertNotIn("Data Engineer | Beta Systems | 2022 - 2023", metric_texts)

    def test_index_supports_french_section_aliases(self):
        parsed_text = """
AYMAN AOURIK

EXPÉRIENCE PROFESSIONNELLE
Ingénieur Data | Exemple SA | 2023 - Présent
- Automatisation Python et Docker qui a réduit le temps de traitement de 42%.

PROJETS
Assistant analytique
- Tableaux de bord Power BI pour 8 équipes métier.

CERTIFICATIONS
Azure Fundamentals
""".strip()

        index = build_source_signal_index(parsed_text)

        self.assertEqual(
            [section["section_key"] for section in index["sections_detected"]],
            ["experience", "projects", "certifications"],
        )
        self.assertEqual(index["optional_sections_detected"], ["projects", "certifications"])
        self.assertEqual(index["counts"]["experience_entries"], 1)

        detected_terms = {item["term"] for item in index["tool_system_terms"]}
        self.assertTrue({"Python", "Docker", "Power BI", "Azure"}.issubset(detected_terms))

    def test_index_falls_back_when_resume_has_no_experience_heading(self):
        parsed_text = """
Jane Doe
jane@example.com

Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built Docker services that reduced review time by 35%.

Data Engineer | Beta Systems | 2022 - 2023
- Maintained Airflow jobs processing 18M rows per day.

Education
MSc Computer Science | Example University | 2020
""".strip()

        index = build_source_signal_index(parsed_text)

        self.assertEqual(
            [section["section_key"] for section in index["sections_detected"]],
            ["education"],
        )
        self.assertEqual(index["counts"]["experience_entries"], 2)
        self.assertEqual(index["experience_entries"][0]["organization"], "Acme Labs")
        self.assertEqual(index["experience_entries"][1]["organization"], "Beta Systems")

    def test_index_is_deterministic_for_same_input(self):
        parsed_text = """
SUMMARY
AI Engineer

PROFESSIONAL EXPERIENCE
Senior AI Engineer | Acme Labs | Jan 2024 - Present
- Built Docker services that reduced triage time by 35%.
""".strip()

        self.assertEqual(
            build_source_signal_index(parsed_text),
            build_source_signal_index(parsed_text),
        )


if __name__ == "__main__":
    unittest.main()
