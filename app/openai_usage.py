from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import re


TOKEN_RATE_DIVISOR = Decimal("1000000")
USD_PRECISION = Decimal("0.0000001")
PRICING_BASIS = "OpenAI public model pricing"

DEFAULT_TEXT_PRICING = {
    "gpt-4o-mini": {
        "input_per_million_usd": Decimal("0.15"),
        "cached_input_per_million_usd": Decimal("0.075"),
        "output_per_million_usd": Decimal("0.60"),
    },
    "gpt-4o": {
        "input_per_million_usd": Decimal("2.50"),
        "cached_input_per_million_usd": Decimal("1.25"),
        "output_per_million_usd": Decimal("10.00"),
    },
    "gpt-4.1-mini": {
        "input_per_million_usd": Decimal("0.40"),
        "cached_input_per_million_usd": Decimal("0.10"),
        "output_per_million_usd": Decimal("1.60"),
    },
}

SNAPSHOT_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _read_path(source: object, *path: str, default: object = None) -> object:
    current = source
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
        if current is None:
            return default
    return current if current is not None else default


def _pricing_lookup_keys(model: str) -> list[str]:
    cleaned = str(model or "").strip()
    if not cleaned:
        return []
    base = SNAPSHOT_SUFFIX.sub("", cleaned)
    keys = [cleaned]
    if base and base not in keys:
        keys.append(base)
    return keys


def _normalize_pricing_entry(entry: dict) -> dict[str, Decimal] | None:
    if not isinstance(entry, dict):
        return None
    input_rate = entry.get("input_per_million_usd")
    cached_input_rate = entry.get("cached_input_per_million_usd", input_rate)
    output_rate = entry.get("output_per_million_usd")
    if input_rate is None or output_rate is None:
        return None
    return {
        "input_per_million_usd": Decimal(str(input_rate)),
        "cached_input_per_million_usd": Decimal(str(cached_input_rate)),
        "output_per_million_usd": Decimal(str(output_rate)),
    }


def resolve_model_pricing(model: str, config: dict) -> tuple[dict[str, Decimal] | None, str]:
    overrides = ((config.get("openai") or {}).get("pricing") or {}) if isinstance(config, dict) else {}
    for key in _pricing_lookup_keys(model):
        override = _normalize_pricing_entry(overrides.get(key))
        if override:
            return override, f"{PRICING_BASIS} override:{key}"
    for key in _pricing_lookup_keys(model):
        default = DEFAULT_TEXT_PRICING.get(key)
        if default:
            return default, PRICING_BASIS
    return None, PRICING_BASIS


def _quantize_usd(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(USD_PRECISION, rounding=ROUND_HALF_UP))


@dataclass
class OpenAIUsageRecord:
    request_kind: str
    attempt_number: int
    model_used: str
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    input_cost_usd: float | None
    cached_input_cost_usd: float | None
    output_cost_usd: float | None
    total_cost_usd: float | None
    pricing_basis: str

    def model_dump(self) -> dict:
        return {
            "request_kind": self.request_kind,
            "attempt_number": self.attempt_number,
            "model_used": self.model_used,
            "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "input_cost_usd": self.input_cost_usd,
            "cached_input_cost_usd": self.cached_input_cost_usd,
            "output_cost_usd": self.output_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "pricing_basis": self.pricing_basis,
        }


def usage_from_response(
    response: object,
    *,
    request_kind: str,
    attempt_number: int,
    fallback_model: str,
    config: dict,
) -> OpenAIUsageRecord:
    usage = _read_path(response, "usage", default={})
    prompt_tokens = int(_read_path(usage, "prompt_tokens", default=0) or 0)
    cached_prompt_tokens = int(_read_path(usage, "prompt_tokens_details", "cached_tokens", default=0) or 0)
    completion_tokens = int(_read_path(usage, "completion_tokens", default=0) or 0)
    total_tokens = int(_read_path(usage, "total_tokens", default=0) or 0)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    model_used = str(_read_path(response, "model", default=fallback_model) or fallback_model)
    pricing, pricing_basis = resolve_model_pricing(model_used, config)
    input_cost_usd = None
    cached_input_cost_usd = None
    output_cost_usd = None
    total_cost_usd = None

    if pricing:
        uncached_prompt_tokens = max(prompt_tokens - cached_prompt_tokens, 0)
        input_cost = (Decimal(uncached_prompt_tokens) * pricing["input_per_million_usd"]) / TOKEN_RATE_DIVISOR
        cached_cost = (Decimal(cached_prompt_tokens) * pricing["cached_input_per_million_usd"]) / TOKEN_RATE_DIVISOR
        output_cost = (Decimal(completion_tokens) * pricing["output_per_million_usd"]) / TOKEN_RATE_DIVISOR
        total_cost = input_cost + cached_cost + output_cost
        input_cost_usd = _quantize_usd(input_cost)
        cached_input_cost_usd = _quantize_usd(cached_cost)
        output_cost_usd = _quantize_usd(output_cost)
        total_cost_usd = _quantize_usd(total_cost)

    return OpenAIUsageRecord(
        request_kind=request_kind,
        attempt_number=attempt_number,
        model_used=model_used,
        prompt_tokens=prompt_tokens,
        cached_prompt_tokens=cached_prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        input_cost_usd=input_cost_usd,
        cached_input_cost_usd=cached_input_cost_usd,
        output_cost_usd=output_cost_usd,
        total_cost_usd=total_cost_usd,
        pricing_basis=pricing_basis,
    )


def summarize_usage(records: list[OpenAIUsageRecord]) -> dict:
    attempts = [record.model_dump() for record in records]
    known_costs = [record.total_cost_usd for record in records if record.total_cost_usd is not None]
    total_cost_usd = round(sum(known_costs), 7) if known_costs else None
    return {
        "attempt_count": len(records),
        "model_used": records[-1].model_used if records else "",
        "prompt_tokens": sum(record.prompt_tokens for record in records),
        "cached_prompt_tokens": sum(record.cached_prompt_tokens for record in records),
        "completion_tokens": sum(record.completion_tokens for record in records),
        "total_tokens": sum(record.total_tokens for record in records),
        "input_cost_usd": round(sum(record.input_cost_usd or 0.0 for record in records), 7) if records else None,
        "cached_input_cost_usd": round(sum(record.cached_input_cost_usd or 0.0 for record in records), 7) if records else None,
        "output_cost_usd": round(sum(record.output_cost_usd or 0.0 for record in records), 7) if records else None,
        "total_cost_usd": total_cost_usd,
        "pricing_basis": records[-1].pricing_basis if records else PRICING_BASIS,
        "attempts": attempts,
    }
