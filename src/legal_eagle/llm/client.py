"""LLM client wrapper.

Wraps LiteLLM so the rest of the system speaks one interface regardless of
provider. Defaults to MiniMax (configurable via env).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import litellm
from pydantic import BaseModel

from ..config import get_settings

logger = logging.getLogger(__name__)

# Quiet LiteLLM's noisy default logging
litellm.set_verbose = False


class LLMClient:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        s = get_settings()
        self.model = model or s.minimax_model
        self.api_key = api_key or s.minimax_api_key
        self.base_url = base_url or s.minimax_base_url
        if self.api_key:
            # LiteLLM auto-detects provider from model prefix; set the env
            # variable the provider expects. For `minimax/...` LiteLLM looks at
            # MINIMAX_API_KEY, but also accepts OPENAI_API_KEY for openai/*.
            if self.model.startswith("minimax/"):
                import os
                os.environ.setdefault("MINIMAX_API_KEY", self.api_key)
                if self.base_url:
                    os.environ.setdefault("MINIMAX_BASE_URL", self.base_url)
            elif self.model.startswith("openai/"):
                import os
                os.environ.setdefault("OPENAI_API_KEY", self.api_key)
                if self.base_url:
                    os.environ.setdefault("OPENAI_BASE_URL", self.base_url)

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        response_format: Optional[dict[str, str]] = None,
    ) -> str:
        """Plain text completion."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format
        try:
            resp = litellm.completion(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:  # pragma: no cover - logged for observability
            logger.exception("LLM completion failed: %s", e)
            raise

    def complete_json(
        self,
        system: str,
        user: str,
        schema_hint: Optional[BaseModel] = None,
        *,
        temperature: float = 0.1,
        max_tokens: int = 3000,
    ) -> dict[str, Any]:
        """Ask the LLM for JSON. Falls back to lenient parsing if needed."""
        json_instruction = (
            "Return ONLY a single valid JSON object. No prose, no markdown fences."
        )
        if schema_hint is not None:
            json_instruction += (
                f"\n\nConform to this Pydantic schema (field names and types):\n"
                f"{schema_hint.model_json_schema()}"
            )
        text = self.complete(
            system=system + "\n\n" + json_instruction,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _parse_json_lenient(text)


def _parse_json_lenient(text: str) -> dict[str, Any]:
    """Try strict JSON, then extract a JSON object from prose/markdown."""
    text = text.strip()
    if not text:
        return {}
    # Strip code fences
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first and last fence lines
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse LLM JSON output; returning empty dict")
    return {}
