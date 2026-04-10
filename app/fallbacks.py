"""Fallback content builders, output validators, and repair logic."""
from __future__ import annotations

import re
from datetime import date

from app.language import (
    _experience_bullets_for_language,
    _looks_like_french,
    _text_conflicts_with_language,
    _text_matches_language,
)
from app.schemas import (
    CONTENT_TOKEN_STOPWORDS,
    COVER_LETTER_BANNED_PHRASES,
    COVER_LETTER_CULTURE_TERMS,
    NUMERIC_FACT_PATTERN,
    SUMMARY_BANNED_PHRASES,
    SUMMARY_SENTENCE_MAX,
    SUMMARY_SENTENCE_MIN,
    _clean_text_list,
    _normalize_match_key,
)
from app.targeting import (
    is_credible_role_title,
    normalize_role_title,
    target_resume_concepts,
)
from app.text_utils import clean_text as _clean_text
from app.text_utils import term_matches_text as _term_matches_text

# ---------------------------------------------------------------------------
# Generic text helpers
# ---------------------------------------------------------------------------


def _sentence_chunks(text: object) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _paragraph_chunks(text: object) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    return [_clean_text(part) for part in re.split(r"\n\s*\n", raw) if _clean_text(part)]


def _word_count(text: object) -> int:
    cleaned = _clean_text(text)
    if not cleaned:
        return 0
    return len(re.findall(r"\S+", cleaned))


def _content_tokens(text: object) -> set[str]:
    tokens = set()
    for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", _clean_text(text).lower()):
        if token in CONTENT_TOKEN_STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def _join_phrases(phrases: list[str], resume_language: str) -> str:
    cleaned = [_clean_text(item).strip(" .,:;") for item in phrases if _clean_text(item)]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} {'et' if resume_language == 'fr' else 'and'} {cleaned[1]}"
    if resume_language == "fr":
        return ", ".join(cleaned[:-1]) + f" et {cleaned[-1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _natural_culture_phrase(term: str, resume_language: str) -> str:
    cleaned = _clean_text(term).strip(" .,:;").lower()
    if not cleaned:
        return ""
    if resume_language == "fr":
        mapping = {
            "mentor": "le mentorat",
            "pragmatique": "le pragmatisme",
            "autonomie": "l'autonomie",
            "autonome": "l'autonomie",
            "rigueur": "la rigueur",
            "execution": "l'exécution",
            "delivery-focused": "une exécution orientée résultat",
            "cross-functional": "la collaboration cross-fonctionnelle",
            "stakeholder communication": "la communication avec les parties prenantes",
        }
        return mapping.get(cleaned, cleaned)
    mapping = {
        "doer": "a doer mindset",
        "mentor": "mentoring",
        "pragmatic": "pragmatism",
        "pragmatist": "pragmatism",
        "builder": "building from scratch",
        "hands-on": "a hands-on style",
        "ownership": "ownership",
        "owner": "ownership",
        "autonomy": "autonomy",
        "autonomous": "autonomy",
        "rigor": "rigor",
        "rigorous": "rigor",
        "cross-functional": "cross-functional collaboration",
        "stakeholder communication": "stakeholder communication",
        "delivery-focused": "delivery-focused execution",
    }
    return mapping.get(cleaned, cleaned)


def _ensure_sentence(text: object) -> str:
    cleaned = _clean_text(text)
    if cleaned and cleaned[-1] not in ".!?":
        return cleaned + "."
    return cleaned


def _summary_has_target_length(text: object) -> bool:
    count = len(_sentence_chunks(text))
    return SUMMARY_SENTENCE_MIN <= count <= SUMMARY_SENTENCE_MAX


def _contains_banned_phrase(text: str) -> bool:
    lowered = _clean_text(text).lower()
    return any(phrase in lowered for phrase in SUMMARY_BANNED_PHRASES)


# ---------------------------------------------------------------------------
# Candidate experience helpers
# ---------------------------------------------------------------------------


def _candidate_years_experience(candidate_context: dict) -> int:
    starts = []
    for item in candidate_context.get("experiences", []):
        match = re.fullmatch(r"(\d{4})-(\d{2})", _clean_text((item or {}).get("start")))
        if match:
            starts.append((int(match.group(1)), int(match.group(2))))
    if not starts:
        return 0
    year, month = min(starts)
    months = max((date.today().year - year) * 12 + (date.today().month - month), 0)
    return max(months // 12, 0)


def _experience_year_label(candidate_context: dict, resume_language: str) -> str:
    years = max(_candidate_years_experience(candidate_context), 1)
    if resume_language == "fr":
        return f"{years}+ ans"
    return f"{years}+ years"


def _find_experience(candidate_context: dict, company: str, role: str) -> dict | None:
    company_key = _normalize_match_key(company)
    role_key = _normalize_match_key(role)
    for item in candidate_context.get("experiences", []):
        if company_key != _normalize_match_key((item or {}).get("company")):
            continue
        if role_key != _normalize_match_key((item or {}).get("role")):
            continue
        return item
    return None


# ---------------------------------------------------------------------------
# Cover letter helpers
# ---------------------------------------------------------------------------


def _cover_letter_focus_phrases(jd_analysis: dict) -> list[str]:
    phrases = []
    seen = set()
    for item in (
        list(jd_analysis.get("top_requirements", []))
        + list(jd_analysis.get("keyword_signals", []))
        + list(jd_analysis.get("matched_keywords", []))
    ):
        cleaned = _clean_text(item).strip(" .,:;")
        if not cleaned or len(cleaned.split()) > 8:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        phrases.append(cleaned)
        seen.add(key)
        if len(phrases) >= 5:
            break
    role = _clean_text(jd_analysis.get("role"))
    if role and not phrases:
        phrases.append(role)
    return phrases


def _cover_letter_culture_phrases(jd_analysis: dict, jd_text: str) -> list[str]:
    lowered_jd = _clean_text(jd_text).lower()
    phrases = []
    seen = set()
    for term in COVER_LETTER_CULTURE_TERMS:
        if term in lowered_jd and term not in seen:
            phrases.append(term)
            seen.add(term)
        if len(phrases) >= 3:
            return phrases
    for phrase in _cover_letter_focus_phrases(jd_analysis):
        lowered_phrase = phrase.lower()
        if not any(term in lowered_phrase for term in COVER_LETTER_CULTURE_TERMS):
            continue
        if lowered_phrase in seen:
            continue
        phrases.append(phrase)
        seen.add(lowered_phrase)
        if len(phrases) >= 3:
            break
    return phrases


def _select_cover_letter_proof_bullets(candidate_context: dict, jd_analysis: dict, resume_language: str) -> list[str]:
    signal_phrases = [
        _clean_text(item).lower()
        for item in (
            list(jd_analysis.get("top_requirements", []))
            + list(jd_analysis.get("keyword_signals", []))
            + list(jd_analysis.get("matched_keywords", []))
            + [_clean_text(jd_analysis.get("role"))]
        )
        if _clean_text(item)
    ]
    signal_tokens = set()
    for phrase in signal_phrases:
        signal_tokens.update(_content_tokens(phrase))

    ranked = []
    for experience_index, item in enumerate(candidate_context.get("experiences", []) or []):
        for bullet in _experience_bullets_for_language(item, resume_language):
            cleaned = _clean_text(bullet)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            metric_count = len(NUMERIC_FACT_PATTERN.findall(cleaned))
            phrase_hits = sum(1 for phrase in signal_phrases if phrase and phrase in lowered)
            token_hits = len(signal_tokens & _content_tokens(cleaned))
            score = (metric_count * 6) + (phrase_hits * 4) + token_hits
            if experience_index == 0:
                score += 1
            ranked.append((score, metric_count, len(cleaned), _ensure_sentence(cleaned)))

    ordered = []
    seen: set[str] = set()
    for _, _, _, bullet in sorted(ranked, key=lambda item: (-item[0], -item[1], item[2])):
        key = bullet.lower()
        if key in seen:
            continue
        ordered.append(bullet)
        seen.add(key)

    metric_bullets = [bullet for bullet in ordered if NUMERIC_FACT_PATTERN.search(bullet)]
    selected = metric_bullets[:3] if len(metric_bullets) >= 2 else ordered[:3]
    if len(selected) > 2 and sum(_word_count(item) for item in selected) > 55:
        selected = selected[:2]
    for candidate in ordered:
        if len(selected) >= 2:
            break
        if candidate not in selected:
            selected.append(candidate)
    return selected[:3]


def _cover_letter_has_expected_structure(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if re.search(r"(?m)^\s*(?:[-*•#]|\d+\.)\s+", raw):
        return False
    paragraphs = _paragraph_chunks(raw)
    if len(paragraphs) != 4:
        return False
    if len(_sentence_chunks(paragraphs[-1])) != 1:
        return False
    if _word_count(raw) > 200:
        return False
    return len(NUMERIC_FACT_PATTERN.findall(raw)) >= 2


def _cover_letter_is_generic(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    return any(phrase in lowered for phrase in COVER_LETTER_BANNED_PHRASES)


def _build_fallback_cover_letter(
    candidate_context: dict,
    jd_analysis: dict,
    jd_text: str,
    resume_language: str,
) -> str:
    company = _clean_text(jd_analysis.get("company"))
    role = _preferred_email_role(jd_analysis, resume_language)
    focus_phrases = _cover_letter_focus_phrases(jd_analysis)[:3]
    if not focus_phrases and role:
        focus_phrases = [role]
    culture_phrases = _cover_letter_culture_phrases(jd_analysis, jd_text)[:3]
    proofs = _select_cover_letter_proof_bullets(candidate_context, jd_analysis, resume_language)[:2]
    focus_text = _join_phrases(focus_phrases, resume_language)
    culture_text = _join_phrases(
        [_natural_culture_phrase(item, resume_language) for item in culture_phrases if _natural_culture_phrase(item, resume_language)],
        resume_language,
    )
    closing_focus = focus_phrases[0] if focus_phrases else (role or ("ce périmètre" if resume_language == "fr" else "this scope"))
    proof_paragraph = " ".join(proofs).strip()

    if resume_language == "fr":
        focus_target = focus_text or "la livraison de systèmes utiles en production"
        culture_text = culture_text or "ownership, pragmatisme et exécution"
        first = (
            f"Je construis des systèmes data et IA de production qui remplacent une charge manuelle réelle, et l'accent mis par {company} sur {focus_target} correspond exactement au type de problème que j'aime prendre en main."
            if company
            else f"Je construis des systèmes data et IA de production qui remplacent une charge manuelle réelle, et votre focus sur {focus_target} correspond exactement au type de problème que j'aime prendre en main."
        )
        second = proof_paragraph or (
            "J'ai livré des systèmes de production qui automatisent des workflows critiques, réduisent les coûts et améliorent la qualité opérationnelle."
        )
        third = (
            f"L'accent mis sur {culture_text} correspond à ma façon de travailler : exécution directe, arbitrages pragmatiques et collaboration fluide avec les équipes métier et techniques."
        )
        fourth = (
            f"J'apprécie particulièrement la manière dont {company} cadre {closing_focus} comme un vrai sujet opérationnel."
            if company
            else f"J'apprécie particulièrement la manière dont le poste cadre {closing_focus} comme un vrai sujet opérationnel."
        )
    else:
        focus_target = focus_text or "shipping useful production systems"
        culture_text = culture_text or "ownership, pragmatism, and execution"
        first = (
            f"I build production AI and data systems that remove real manual workload, and {company}'s focus on {focus_target} is exactly the kind of operating problem I like to own."
            if company
            else f"I build production AI and data systems that remove real manual workload, and your focus on {focus_target} is exactly the kind of operating problem I like to own."
        )
        second = proof_paragraph or (
            "I have shipped production systems that automate critical workflows, reduce costs, and improve operational quality."
        )
        third = (
            f"The emphasis on {culture_text} matches how I work: direct execution, clear tradeoffs, and steady collaboration with engineers and stakeholders."
        )
        fourth = (
            f"What stands out about {company} is the way you frame {closing_focus} as a real operating problem."
            if company
            else f"What stands out about the role is the way it frames {closing_focus} as a real operating problem."
        )

    paragraphs = [first, second, third, fourth]
    return "\n\n".join(_clean_text(paragraph) for paragraph in paragraphs if _clean_text(paragraph))


# ---------------------------------------------------------------------------
# Summary fallback helpers
# ---------------------------------------------------------------------------


def _build_fallback_title(candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    preferred = normalize_role_title(jd_analysis.get("role"), resume_language)
    if is_credible_role_title(preferred):
        return preferred
    headline = normalize_role_title(candidate_context.get("headline"), resume_language)
    if is_credible_role_title(headline):
        return headline
    experiences = candidate_context.get("experiences") or []
    if experiences:
        fallback_role = normalize_role_title((experiences[0] or {}).get("role"), resume_language)
        if is_credible_role_title(fallback_role):
            return fallback_role
    return "Lead Tech Data & IA" if resume_language == "fr" else "AI & Data Lead"


def _build_fallback_summary(candidate_context: dict, jd_analysis: dict, resume_language: str, title: str) -> str:
    years_label = _experience_year_label(candidate_context, resume_language)
    seniority = _clean_text(jd_analysis.get("seniority")).lower()
    leadership = seniority == "lead" or "lead" in title.lower()
    if resume_language == "fr":
        if leadership:
            return (
                f"{title} avec {years_label} d'expérience dans la mise en production de systèmes data et IA à impact opérationnel mesurable. "
                "Je pilote la livraison du cadrage à la production, j'encadre des équipes techniques et je privilégie des systèmes fiables qui remplacent une charge manuelle réelle avec des arbitrages solides entre impact, coût et maintenabilité."
            )
        return (
            f"Professionnel Data & IA avec {years_label} d'expérience dans la conception et le déploiement de systèmes de production liés à des résultats métier mesurables. "
            "Je transforme les besoins métier en modèles, pipelines et automatisations exploitables en production, avec un focus sur l'exécution concrète, la qualité opérationnelle et la réduction durable de la charge manuelle."
        )
    if leadership:
        return (
            f"{title} with {years_label} of experience shipping production data and AI systems tied to measurable operational impact. "
            "I lead engineers, drive delivery from scoping through production, and focus on reliable systems that replace real manual workload with clear tradeoffs across impact, cost, and maintainability."
        )
    return (
        f"Data and AI professional with {years_label} of experience designing and deploying production systems tied to measurable business outcomes. "
        "I turn business needs into reliable models, pipelines, and automation that teams can operate in production, with a focus on practical delivery, operational quality, and reducing manual workload."
    )


def _summary_bridge_sentence(concepts: list[str], resume_language: str) -> str:
    cleaned = [_clean_text(item).strip(" .,:;") for item in concepts if _clean_text(item)]
    if not cleaned:
        return ""

    lowered = {item.lower() for item in cleaned}
    agent_pair = {"agents ia", "orchestration d'agents"} if resume_language == "fr" else {"ai agents", "agent orchestration"}
    remaining = [item for item in cleaned if item.lower() not in agent_pair]

    if agent_pair.issubset(lowered):
        lead = "les agents IA et leur orchestration" if resume_language == "fr" else "AI agents and their orchestration"
        tail = _join_phrases(remaining, resume_language)
        if resume_language == "fr":
            if tail:
                return f"Mon expérience couvre {lead}, {tail}, ainsi que des intégrations d'API IA livrées en production."
            return f"Mon expérience couvre {lead}, ainsi que des intégrations d'API IA livrées en production."
        if tail:
            return f"My experience covers {lead}, {tail}, along with production AI API integrations."
        return f"My experience covers {lead}, along with production AI API integrations."

    joined = _join_phrases(cleaned, resume_language)
    if resume_language == "fr":
        return f"Mon expérience couvre {joined} et leur mise en production sur des workflows métier réels."
    return f"My experience covers {joined} in production across real business workflows."


def _align_summary_to_jd(summary: str, candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    cleaned_summary = _clean_text(summary)
    concepts = target_resume_concepts(candidate_context, jd_analysis, resume_language=resume_language, limit=3)
    if not cleaned_summary or not concepts:
        return cleaned_summary

    missing = [item for item in concepts if not _term_matches_text(cleaned_summary, item)]
    if not missing:
        return cleaned_summary

    bridge_sentence = _summary_bridge_sentence(missing[:3], resume_language)
    if not bridge_sentence:
        return cleaned_summary

    sentences = _sentence_chunks(cleaned_summary)
    if len(sentences) >= SUMMARY_SENTENCE_MAX:
        sentences[-1] = bridge_sentence
    else:
        sentences.append(bridge_sentence)
    candidate = " ".join(sentences[:SUMMARY_SENTENCE_MAX])
    return candidate if _summary_has_target_length(candidate) else cleaned_summary


def _normalize_summary(
    model_summary: object,
    candidate_context: dict,
    jd_analysis: dict,
    resume_language: str,
    title: str,
) -> str:
    summary = _clean_text(model_summary)
    if (
        summary
        and not _contains_banned_phrase(summary)
        and _text_matches_language(summary, resume_language)
        and _summary_has_target_length(summary)
    ):
        return _align_summary_to_jd(summary, candidate_context, jd_analysis, resume_language)
    return _align_summary_to_jd(
        _build_fallback_summary(candidate_context, jd_analysis, resume_language, title),
        candidate_context,
        jd_analysis,
        resume_language,
    )


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------


def _email_is_generic(text: str) -> bool:
    from app.schemas import GENERIC_EMAIL_PHRASES  # avoid module-level name collision

    cleaned = _clean_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in GENERIC_EMAIL_PHRASES):
        return True
    return len(NUMERIC_FACT_PATTERN.findall(cleaned)) < 2


def _linkedin_is_generic(text: str, resume_language: str) -> bool:
    from app.schemas import GENERIC_LINKEDIN_PHRASES

    cleaned = _clean_text(text)
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in GENERIC_LINKEDIN_PHRASES):
        return True
    if len(cleaned) > 420:
        return True
    if len(cleaned.split()) < 12:
        return True
    metric_count = len(NUMERIC_FACT_PATTERN.findall(cleaned))
    if resume_language == "fr":
        if "bonjour" not in lowered:
            return True
        return metric_count < 1
    return metric_count < 1


def _email_has_expected_structure(text: str, resume_language: str) -> bool:
    raw = str(text or "")
    lowered = raw.lower()
    if resume_language == "fr":
        stack_hits = sum(1 for token in ("python", "fastapi", "docker", "airflow", "postgresql") if token in lowered)
        return (
            ("objet :" in lowered or "subject:" in lowered)
            and "bonjour" in lowered
            and "quelques exemples concrets" in lowered
            and raw.count("•") >= 3
            and stack_hits >= 3
            and "cordialement" in lowered
        )
    stack_hits = sum(1 for token in ("python", "fastapi", "docker", "airflow", "postgresql") if token in lowered)
    return (
        "hello" in lowered
        and raw.count("•") >= 3
        and stack_hits >= 3
        and ("best regards" in lowered or "regards" in lowered)
    )


def _select_email_proof_bullets(candidate_context: dict, resume_language: str) -> list[str]:
    experiences = candidate_context.get("experiences", []) or []
    candidates = []
    for item in experiences:
        localized = _experience_bullets_for_language(item, resume_language)
        for bullet in localized:
            lowered = bullet.lower()
            score = 0
            if "lead" in lowered or "dirig" in lowered or "équipe" in lowered or "engineers" in lowered or "ingénieurs" in lowered:
                score += 4
            if "$" in bullet or "gpu" in lowered or "cost" in lowered or "coût" in lowered:
                score += 4
            if "llm" in lowered or "ai" in lowered or "ia" in lowered:
                score += 3
            if "%" in bullet or "~" in bullet or "2m+" in lowered or "20k" in lowered or "80k" in lowered or "2,400" in bullet:
                score += 2
            candidates.append((score, bullet))

    ordered: list[str] = []
    seen: set[str] = set()
    for _, bullet in sorted(candidates, key=lambda item: item[0], reverse=True):
        key = bullet.lower()
        if key in seen:
            continue
        ordered.append(bullet)
        seen.add(key)
        if len(ordered) >= 3:
            break
    return ordered


def _find_localized_bullet(
    candidate_context: dict,
    resume_language: str,
    company: str,
    role: str,
    *patterns: str,
) -> str:
    experience = _find_experience(candidate_context, company, role)
    if not experience:
        return ""
    bullets = _experience_bullets_for_language(experience, resume_language)
    normalized_patterns = [pattern.lower() for pattern in patterns if pattern]
    for bullet in bullets:
        lowered = bullet.lower()
        if all(pattern in lowered for pattern in normalized_patterns):
            return bullet
    return ""


def _email_years_label(candidate_context: dict, resume_language: str) -> str:
    years = max(_candidate_years_experience(candidate_context), 1)
    if resume_language == "fr":
        return "1 an" if years == 1 else f"{years} ans"
    return "1 year" if years == 1 else f"{years} years"


def _format_contact_phone(phone: str) -> str:
    cleaned = _clean_text(phone)
    digits = re.sub(r"\D+", "", cleaned)
    if cleaned.startswith("+") and digits.startswith("212") and len(digits) == 12:
        return f"+212 {digits[3:6]} {digits[6:9]} {digits[9:12]}"
    return cleaned


def _first_person_fr(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered.startswith(("j'ai ", "je ")):
        return cleaned
    return "J'ai " + cleaned[0].lower() + cleaned[1:]


def _preferred_email_role(jd_analysis: dict, resume_language: str) -> str:
    role = normalize_role_title(jd_analysis.get("role"), resume_language)
    combined = " ".join(
        _clean_text(item)
        for item in (
            [role]
            + list(jd_analysis.get("matched_keywords", []))
            + list(jd_analysis.get("keyword_signals", []))
            + list(jd_analysis.get("top_requirements", []))
            + list(jd_analysis.get("missing_candidate_keywords", []))
        )
    ).lower()
    if role and "data" in role.lower() and "ai" not in role.lower() and "ia" not in role.lower() and (" ai" in combined or "/ ai" in combined or "ia" in combined):
        return f"{role} / AI"
    return role or ("Tech Lead Data / AI" if resume_language == "fr" else "Data / AI Tech Lead")


def _leadership_email_bullet(candidate_context: dict, resume_language: str) -> str:
    if resume_language != "fr":
        return ""
    sizes = []
    for item in candidate_context.get("experiences", []):
        for bullet in _experience_bullets_for_language(item, resume_language):
            lowered = bullet.lower()
            if "équipe" not in lowered and "ingénieur" not in lowered:
                continue
            for match in re.findall(r"\b\d+\b", bullet):
                try:
                    value = int(match)
                except ValueError:
                    continue
                if 2 <= value <= 20:
                    sizes.append(value)
    if sizes:
        low = min(sizes)
        high = max(sizes)
        range_label = f"{low} à {high} ingénieurs" if low != high else f"{low} ingénieurs"
        return (
            f"J'ai encadré des équipes cross-fonctionnelles ({range_label}), "
            "piloté la roadmap AI et géré les arbitrages coût/performance."
        )
    return "J'ai encadré des équipes techniques, piloté la roadmap AI et géré les arbitrages coût/performance."


def _linkedin_interest_topic(jd_analysis: dict, resume_language: str) -> str:
    role = _clean_text(jd_analysis.get("role")).lower()
    combined = " ".join(
        _clean_text(item).lower()
        for item in (
            [role]
            + list(jd_analysis.get("top_requirements", []))
            + list(jd_analysis.get("keyword_signals", []))
            + list(jd_analysis.get("matched_keywords", []))
        )
    )
    if resume_language == "fr":
        if "lead" in role and ("data" in role or "ai" in role):
            return "La partie leadership technique / architecture m'a particulièrement parlé"
        if "architecture" in combined and ("performance" in combined or "releases" in combined):
            return "La partie architecture / performance m'a particulièrement parlé"
        if "architecture" in combined:
            return "La partie architecture m'a particulièrement parlé"
        if "spark" in combined or "scala" in combined or "kafka" in combined:
            return "La partie systèmes distribués / performance m'a particulièrement parlé"
        if "performance" in combined:
            return "La partie performance m'a particulièrement parlé"
        if "leadership" in combined or "encadrer" in combined:
            return "La partie leadership technique m'a particulièrement parlé"
        return "Le scope du poste m'a particulièrement parlé"
    if "lead" in role and ("data" in role or "ai" in role):
        return "The technical leadership / architecture side is especially relevant to me"
    if "architecture" in combined and "performance" in combined:
        return "The architecture / performance angle is especially relevant to me"
    if "architecture" in combined:
        return "The architecture side is especially relevant to me"
    if "performance" in combined:
        return "The performance side is especially relevant to me"
    if "leadership" in combined:
        return "The technical leadership side is especially relevant to me"
    return "The scope of the role is especially relevant to me"


def _distributed_gap_line(jd_analysis: dict, resume_language: str) -> str:
    hints = {_clean_text(item).lower() for item in jd_analysis.get("missing_candidate_keywords", [])}
    distributed = {"spark", "kafka", "scala", "hdfs", "hive", "elasticsearch", "java"}
    if not (hints & distributed):
        if resume_language == "fr":
            return "Sur la stack, je travaille principalement en Python / FastAPI / Docker / Airflow / PostgreSQL."
        return "My main stack is Python / FastAPI / Docker / Airflow / PostgreSQL."
    if resume_language == "fr":
        return (
            "Sur la stack, je travaille principalement en Python / FastAPI / Docker / Airflow / PostgreSQL. "
            "Je monte rapidement sur Spark, Kafka et Scala — des environnements distribués, "
            "j'en gère la logique au quotidien."
        )
    return (
        "My main stack is Python / FastAPI / Docker / Airflow / PostgreSQL. "
        "I ramp quickly on Spark, Kafka, and Scala, and I already operate daily in distributed environments."
    )


def _build_fallback_email(candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    name = _clean_text(candidate_context.get("personal", {}).get("name"))
    role = _preferred_email_role(jd_analysis, resume_language)
    location = _clean_text(jd_analysis.get("location"))
    gap_line = _distributed_gap_line(jd_analysis, resume_language)
    if resume_language == "fr":
        years_label = _email_years_label(candidate_context, resume_language)
        intro = f"Je me permets de vous contacter suite à votre offre pour le poste de {role}" + (f" à {location}" if location else "") + "."
        auto_responder = "J'ai déployé un auto-répondeur LLM traitant ~20 000 leads/mois à 96% de précision, en production."
        cv_cost = "J'ai remplacé un pipeline Computer Vision par une approche LLM sur 2M+ véhicules, évitant 20 000$+ en coûts GPU."
        leadership = _leadership_email_bullet(candidate_context, resume_language)
        proof_lines = "\n".join(
            [
                f"• {auto_responder}",
                f"• {cv_cost}",
                f"• {leadership}",
            ]
        )
        body = [
            f"Objet : Candidature – {role} | {name}",
            "",
            "Bonjour,",
            "",
            intro,
            "",
            f"Avec {years_label} d'expérience à construire et livrer des systèmes AI en production — pas des prototypes — je pense correspondre à ce que vous cherchez. Quelques exemples concrets :",
            "",
            proof_lines,
            "",
            gap_line,
        ]
        body.extend(
            [
                "",
                "Je serais ravi d'échanger sur la façon dont je peux contribuer à vos projets data et AI.",
                "",
                "Cordialement,",
                name,
                f"{_clean_text(candidate_context.get('personal', {}).get('email'))} | {_format_contact_phone(_clean_text(candidate_context.get('personal', {}).get('phone')))}",
                _clean_text(candidate_context.get("personal", {}).get("linkedin")),
            ]
        )
        return "\n".join(line for line in body if line is not None).strip()

    years_label = _email_years_label(candidate_context, resume_language)
    intro = f"I'm reaching out regarding your {role} opening" + (f" in {location}" if location else "") + "."
    proofs = _select_email_proof_bullets(candidate_context, resume_language)
    proof_lines = "\n".join(f"• {bullet}" for bullet in proofs[:3])
    body = [
        f"Subject: Application – {role} | {name}",
        "",
        "Hello,",
        "",
        intro,
        "",
        f"With {years_label} of experience building and shipping production AI systems, not prototypes, I believe I can contribute quickly. A few concrete examples:",
        "",
        proof_lines,
        "",
        gap_line,
    ]
    body.extend(
        [
            "",
            "I'd be glad to discuss how I can contribute to your data and AI projects.",
            "",
            "Best regards,",
            name,
            f"{_clean_text(candidate_context.get('personal', {}).get('email'))} | {_format_contact_phone(_clean_text(candidate_context.get('personal', {}).get('phone')))}",
        ]
    )
    return "\n".join(line for line in body if line is not None).strip()


def _build_fallback_linkedin_message(candidate_context: dict, jd_analysis: dict, resume_language: str) -> str:
    role = _preferred_email_role(jd_analysis, resume_language)
    location = _clean_text(jd_analysis.get("location"))
    interest = _linkedin_interest_topic(jd_analysis, resume_language)
    if resume_language == "fr":
        location_suffix = f" à {location}" if location else ""
        return (
            f"Bonjour, j'ai vu votre offre de {role}{location_suffix}. "
            f"{interest} : j'ai déjà déployé un auto-répondeur LLM à ~20 000 leads/mois à 96% de précision et remplacé un pipeline Computer Vision sur 2M+ véhicules. "
            "Ravi d'échanger si le sujet est toujours d'actualité."
        )
    location_suffix = f" in {location}" if location else ""
    return (
        f"Hello, I saw your {role} opening{location_suffix}. "
        f"{interest}: I have already deployed an LLM auto-responder at ~20,000 leads/month with 96% accuracy and replaced a computer vision pipeline across 2M+ vehicles. "
        "I'd be glad to connect if the role is still open."
    )


# ---------------------------------------------------------------------------
# Pack repair and validation
# ---------------------------------------------------------------------------


def _repair_pack_content(
    pack: object,
    candidate_context: dict,
    jd_analysis: dict,
    jd_text: str,
    outputs: list[str],
) -> None:
    if "cover_letter" in outputs:
        cover_letter = pack.cover_letter or ""
        if (
            not cover_letter
            or _text_conflicts_with_language(cover_letter, pack.resume_language)
            or _cover_letter_is_generic(cover_letter)
            or not _cover_letter_has_expected_structure(cover_letter)
        ):
            pack.cover_letter = _build_fallback_cover_letter(candidate_context, jd_analysis, jd_text, pack.resume_language)

    if "email_draft" in outputs:
        email = pack.email_draft or ""
        if (
            _text_conflicts_with_language(email, pack.resume_language)
            or _email_is_generic(email)
            or not _email_has_expected_structure(email, pack.resume_language)
        ):
            pack.email_draft = _build_fallback_email(candidate_context, jd_analysis, pack.resume_language)

    if "linkedin_msg" in outputs:
        linkedin = pack.linkedin_message or ""
        if (
            not linkedin
            or _text_conflicts_with_language(linkedin, pack.resume_language)
            or _linkedin_is_generic(linkedin, pack.resume_language)
            or (pack.resume_language == "fr" and not _looks_like_french(linkedin))
            or (pack.resume_language == "en" and _looks_like_french(linkedin))
        ):
            pack.linkedin_message = _build_fallback_linkedin_message(candidate_context, jd_analysis, pack.resume_language)


def _validate_pack_content(pack: object, outputs: list[str]) -> None:
    language_name = "French" if pack.resume_language == "fr" else "English"

    if not _summary_has_target_length(pack.tailored_summary):
        raise ValueError("tailored_summary must contain 2 to 3 sentences.")

    for item in pack.tailored_experiences:
        for bullet in item.bullets:
            if _text_conflicts_with_language(bullet, pack.resume_language):
                raise ValueError(
                    f"Tailored experience bullets must all be in {language_name}. "
                    f"Mixed-language bullet detected for {item.company}: {bullet}"
                )

    if "linkedin_msg" in outputs and pack.linkedin_message and _text_conflicts_with_language(pack.linkedin_message, pack.resume_language):
        raise ValueError(f"linkedin_message must be fully written in {language_name}.")

    if "cover_letter" in outputs:
        cover_letter = pack.cover_letter or ""
        if _text_conflicts_with_language(cover_letter, pack.resume_language):
            raise ValueError(f"cover_letter must be fully written in {language_name}.")
        if _cover_letter_is_generic(cover_letter):
            raise ValueError(
                "cover_letter uses generic application language. Lead with a sharp company-specific hook, "
                "2-3 quantified wins, JD language on working style, and a specific one-sentence close."
            )
        if not _cover_letter_has_expected_structure(cover_letter):
            raise ValueError(
                "cover_letter must be exactly 4 short paragraphs, plain text only, under 200 words total, "
                "with 2-3 quantified wins and a one-sentence closing compliment."
            )

    if "email_draft" in outputs:
        email = pack.email_draft or ""
        if _text_conflicts_with_language(email, pack.resume_language):
            raise ValueError(f"email_draft must be fully written in {language_name}.")
        if _email_is_generic(email):
            raise ValueError(
                "email_draft is too generic. Lead with 2-3 quantified proof points tied to the job, "
                "then close with a low-friction ask."
            )
