"""AI layer — Anthropic Claude with strict structured outputs.

Design principles (from the brief §17 and industry best practice):
- The model must return structured fields, never free narrative: every call
  uses `output_config.format` with a JSON schema, and the result is parsed
  with json.loads.
- Deterministic, evidence-first prompting; the fairness rules are injected
  into every scoring prompt.
- Resilient: typed exception handling, bounded retries for retryable errors,
  and a deterministic rule-based fallback engine (see screening.py) so the
  system keeps working when the API is unreachable (brief §13: "able to
  recover from unreadable files or API failures").
"""
from __future__ import annotations

import json
import logging
import time

from .. import config

logger = logging.getLogger("peopleiq.llm")

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

_client = None


def llm_available() -> bool:
    return bool(config.ANTHROPIC_API_KEY) and anthropic is not None


def _get_client():
    global _client
    if _client is None and llm_available():
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, max_retries=2)
    return _client


class LLMUnavailable(RuntimeError):
    """Raised when the AI layer cannot serve a request; callers fall back."""


def structured_call(
    *,
    system: str,
    user_content: str,
    schema: dict,
    max_tokens: int | None = None,
    retries: int = 2,
) -> dict:
    """One structured request to Claude. Returns the parsed JSON object.

    Raises LLMUnavailable when no key is configured or the API cannot be
    reached after bounded retries — callers must degrade gracefully.
    """
    client = _get_client()
    if client is None:
        raise LLMUnavailable("ANTHROPIC_API_KEY not configured")

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=max_tokens or config.LLM_MAX_TOKENS,
                system=system,
                thinking={"type": "adaptive"},
                output_config={
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": user_content}],
            )
            if response.stop_reason == "refusal":
                raise LLMUnavailable("Model declined the request")
            text = next((b.text for b in response.content if b.type == "text"), "")
            return json.loads(text)
        except LLMUnavailable:
            raise
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("LLM returned unparseable JSON (attempt %s): %s", attempt, exc)
        except Exception as exc:  # noqa: BLE001 — classify below
            last_error = exc
            if anthropic is not None:
                if isinstance(exc, anthropic.AuthenticationError):
                    raise LLMUnavailable(f"Anthropic auth failed: {exc}") from exc
                if isinstance(exc, anthropic.RateLimitError):
                    wait = 2 ** attempt * 5
                    logger.warning("Rate limited; backing off %ss", wait)
                    time.sleep(wait)
                    continue
                if isinstance(exc, anthropic.APIStatusError) and exc.status_code < 500:
                    raise LLMUnavailable(f"Anthropic API error: {exc}") from exc
            logger.warning("LLM call failed (attempt %s): %s", attempt, exc)
            time.sleep(min(2 ** attempt, 8))
    raise LLMUnavailable(f"LLM call failed after retries: {last_error}")
