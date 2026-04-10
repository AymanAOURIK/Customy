"""LLM orchestration: build prompts, call OpenAI, validate, and return a tailored ApplicationPack."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.fallbacks import _repair_pack_content, _validate_pack_content
from app.language import _experience_bullets_for_language, _resume_language
from app.models import ApplicationPack
from app.normalization import _normalize_detected_company, _normalize_payload, _unwrap_payload
from app.openai_usage import OpenAIUsageRecord, summarize_usage, usage_from_response
from app.schemas import MAPPING_SCHEMA, MAPPING_SYSTEM_PROMPT, PACK_RESPONSE_SCHEMA
from app.text_utils import clean_text as _clean_text

_log = logging.getLogger(__name__)


class PackGenerationError(ValueError):
    def __init__(self, message: str, usage_summary: dict | None = None) -> None:
        super().__init__(message)
        self.usage_summary = usage_summary or summarize_usage([])


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _get_generation_model(config: dict) -> str:
    return config["llm"].get("generation_model", config["llm"].get("model", "gpt-4.1"))


def _get_analysis_model(config: dict) -> str:
    return config["llm"].get("analysis_model", config["llm"].get("model", "gpt-4o-mini"))


def _load_prompt(config: dict) -> str:
    prompt_path = Path(config["paths"]["prompts_dir"]) / "system.md"
    return prompt_path.read_text(encoding="utf-8")


def _candidate_payload(candidate_context: dict) -> dict:
    return {
        "name": candidate_context.get("personal", {}).get("name", ""),
        "headline": candidate_context.get("headline", ""),
        "summary": candidate_context.get("summary", ""),
        "skills": {
            "languages": list(candidate_context.get("skills", {}).get("languages", [])),
            "frameworks": list(candidate_context.get("skills", {}).get("frameworks", [])),
            "tools": list(candidate_context.get("skills", {}).get("tools", [])),
            "soft": list(candidate_context.get("skills", {}).get("soft", [])),
        },
        "experiences": list(candidate_context.get("experiences", [])),
        "education": list(candidate_context.get("education", [])),
        "spoken_languages": list(candidate_context.get("spoken_languages", [])),
    }


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------


def _build_messages(
    prompt: str,
    compact_message: dict,
    *,
    validation_error: str | None = None,
    previous_payload: dict | None = None,
) -> list[dict]:
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(compact_message, ensure_ascii=False, separators=(",", ":"))},
    ]
    if validation_error and previous_payload is not None:
        messages.extend(
            [
                {"role": "assistant", "content": json.dumps(previous_payload, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": (
                        "Repair the previous JSON so it satisfies the required schema. "
                        f"Validation error: {validation_error}. "
                        "Keep all facts grounded in the candidate profile and job description."
                    ),
                },
            ]
        )
    return messages


def _message_content_as_text(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if item.get("type") == "text" and isinstance(text_value, str):
                    parts.append(text_value)
                elif isinstance(text_value, dict):
                    value = text_value.get("value")
                    if isinstance(value, str):
                        parts.append(value)
            else:
                text_value = getattr(item, "text", None)
                if isinstance(text_value, str):
                    parts.append(text_value)
                else:
                    value = getattr(text_value, "value", None)
                    if isinstance(value, str):
                        parts.append(value)
        return "".join(parts).strip()
    return _clean_text(content)


def _parse_response_payload(response: object) -> dict:
    choices = getattr(response, "choices", [])
    if not choices:
        raise ValueError("Model returned no choices.")
    message = getattr(choices[0], "message", None)
    refusal = getattr(message, "refusal", None) if message is not None else None
    if refusal:
        raise ValueError(f"Model refused the request: {refusal}")
    content = _message_content_as_text(message)
    if not content:
        raise ValueError("Model returned an empty response.")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {exc}") from exc


def _create_completion(
    client: object,
    *,
    config: dict,
    messages: list[dict],
    response_format: dict,
) -> object:
    return client.chat.completions.create(
        model=_get_generation_model(config),
        temperature=config["llm"]["temperature"],
        max_tokens=config["llm"]["max_tokens"],
        response_format=response_format,
        messages=messages,
    )


def _should_fallback_to_json_object(error: Exception) -> bool:
    message = str(error).lower()
    return "json_schema" in message or "response_format" in message or "structured" in message


def _request_model_response(client: object, *, config: dict, messages: list[dict]) -> object:
    try:
        return _create_completion(
            client,
            config=config,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": PACK_RESPONSE_SCHEMA},
        )
    except Exception as exc:
        if not _should_fallback_to_json_object(exc):
            raise
    return _create_completion(
        client,
        config=config,
        messages=messages,
        response_format={"type": "json_object"},
    )


def _ensure_requested_outputs(pack: ApplicationPack, outputs: list[str]) -> None:
    if "cover_letter" in outputs and not pack.cover_letter:
        raise ValueError("Model response is missing cover_letter.")
    if "linkedin_msg" in outputs and not pack.linkedin_message:
        raise ValueError("Model response is missing linkedin_message.")
    if "email_draft" in outputs and not pack.email_draft:
        raise ValueError("Model response is missing email_draft.")


def _get_requirement_mapping(
    client: object,
    *,
    config: dict,
    jd_analysis: dict,
    candidate_context: dict,
    resume_language: str,
) -> dict:
    requirements = list(jd_analysis.get("top_requirements") or jd_analysis.get("keyword_signals", [])[:5])
    if not requirements:
        return {"mappings": [], "summary_anchor": ""}

    bullet_blocks = []
    for item in candidate_context.get("experiences", []):
        company = _clean_text((item or {}).get("company", ""))
        bullets = _experience_bullets_for_language(item, resume_language)
        if company and bullets:
            bullet_blocks.append({"company": company, "bullets": bullets})

    if not bullet_blocks:
        return {"mappings": [], "summary_anchor": ""}

    user_message = json.dumps(
        {
            "target_language": resume_language,
            "jd_requirements": requirements[:6],
            "candidate_bullets": bullet_blocks,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    messages = [
        {"role": "system", "content": MAPPING_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    analysis_model = _get_analysis_model(config)
    try:
        response = client.chat.completions.create(
            model=analysis_model,
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_schema", "json_schema": MAPPING_SCHEMA},
            messages=messages,
        )
        content = _message_content_as_text(response.choices[0].message)
        mapping = json.loads(content)
        if not isinstance(mapping, dict):
            return {"mappings": [], "summary_anchor": ""}
        return mapping
    except Exception:
        return {"mappings": [], "summary_anchor": ""}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pack(
    jd_text: str,
    jd_analysis: dict,
    candidate_context: dict,
    outputs: list[str],
    application_url: str | None,
    config: dict,
) -> tuple[ApplicationPack, dict, str | None]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Add it to .env before generating.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("The openai package is not installed. Run pip install -r requirements.txt.") from exc

    prompt = _load_prompt(config)
    resume_language = _resume_language(jd_analysis)

    client = OpenAI(api_key=api_key)
    requirement_mapping = _get_requirement_mapping(
        client,
        config=config,
        jd_analysis=jd_analysis,
        candidate_context=candidate_context,
        resume_language=resume_language,
    )
    compact_message = {
        "requested_outputs": outputs,
        "application_url": application_url or "",
        "resume_language": resume_language,
        "input_language": jd_analysis.get("language", "en"),
        "jd_analysis": {
            "company": jd_analysis.get("company"),
            "role": jd_analysis.get("role"),
            "seniority": jd_analysis.get("seniority"),
            "matched_keywords": jd_analysis.get("matched_keywords", []),
            "top_requirements": jd_analysis.get("top_requirements", []),
            "keyword_signals": jd_analysis.get("keyword_signals", []),
            "missing_candidate_keywords": jd_analysis.get("missing_candidate_keywords", []),
        },
        "requirement_mapping": requirement_mapping,
        "jd_full": jd_text,
        "candidate": _candidate_payload(candidate_context),
    }
    usage_records: list[OpenAIUsageRecord] = []
    previous_payload = None
    last_error = ""

    for attempt_number in range(1, 3):
        _log.info("generate_pack attempt=%d model=%s", attempt_number, _get_generation_model(config))
        messages = _build_messages(
            prompt,
            compact_message,
            validation_error=last_error or None,
            previous_payload=previous_payload,
        )
        try:
            response = _request_model_response(client, config=config, messages=messages)
        except Exception as exc:
            usage_summary = summarize_usage(usage_records)
            raise PackGenerationError(str(exc), usage_summary=usage_summary) from exc

        record = usage_from_response(
            response,
            request_kind="generate_pack",
            attempt_number=attempt_number,
            fallback_model=_get_generation_model(config),
            config=config,
        )
        usage_records.append(record)
        _log.info(
            "generate_pack tokens prompt=%s completion=%s cached=%s cost=$%s",
            record.prompt_tokens,
            record.completion_tokens,
            record.cached_prompt_tokens,
            f"{record.total_cost_usd:.6f}" if record.total_cost_usd is not None else "?",
        )

        try:
            payload = _parse_response_payload(response)
            previous_payload = payload
            unwrapped_payload = _unwrap_payload(payload)
            detected_company = _normalize_detected_company(unwrapped_payload)
            normalized_payload = _normalize_payload(payload, candidate_context, jd_analysis, jd_text)
            pack = ApplicationPack.model_validate(normalized_payload)
            _repair_pack_content(pack, candidate_context, jd_analysis, jd_text, outputs)
            _ensure_requested_outputs(pack, outputs)
            _validate_pack_content(pack, outputs)
        except ValueError as exc:
            last_error = str(exc)
            if "Missing tailored_experiences" in last_error:
                last_error = (
                    f"{last_error}. "
                    f"Candidate experiences loaded: {len(candidate_context.get('experiences', []))}. "
                    f"Candidate source: {candidate_context.get('candidate_source') or 'unknown'}."
                )
            _log.warning("generate_pack validation failed attempt=%d: %s", attempt_number, last_error)
            if attempt_number >= 2:
                raise PackGenerationError(last_error, usage_summary=summarize_usage(usage_records)) from exc
            continue

        if "cover_letter" not in outputs:
            pack.cover_letter = None
        if "linkedin_msg" not in outputs:
            pack.linkedin_message = None
        if "email_draft" not in outputs:
            pack.email_draft = None

        return pack, summarize_usage(usage_records), detected_company

    raise PackGenerationError(last_error or "Model response validation failed.", usage_summary=summarize_usage(usage_records))
