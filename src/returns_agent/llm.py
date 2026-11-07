"""LLM client. Any OpenAI-compatible API, chosen in .env (default: Gemini free tier)."""

import os
from functools import lru_cache
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Calls and tokens used since the last reset. The eval records them per email.
USAGE = {"calls": 0, "tokens": 0}


def _count(completion) -> None:
    USAGE["calls"] += 1
    if completion.usage:
        USAGE["tokens"] += completion.usage.total_tokens


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        max_retries=3,  # retries 429 rate limits and 5xx errors with backoff
        timeout=45,     # a stuck call fails fast instead of blocking the eval
    )


def model_name() -> str:
    return os.environ["LLM_MODEL"]


def _extra() -> dict:
    """Optional reasoning effort (low/medium/high) for thinking models such as gpt-oss.
    Lower effort = fewer tokens, which matters on free tiers with a daily token limit."""
    effort = os.getenv("LLM_REASONING_EFFORT")
    return {"reasoning_effort": effort} if effort else {}


def parse(schema: type[T], system: str, user: str) -> T:
    """Ask the LLM for an answer that matches a Pydantic schema (structured output)."""
    completion = get_client().chat.completions.parse(
        model=model_name(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format=schema,
        **_extra(),
    )
    _count(completion)
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"LLM gave no parsed output (refusal: {message.refusal})")
    return message.parsed


def complete(system: str, user: str) -> str:
    """Ask the LLM for plain text."""
    completion = get_client().chat.completions.create(
        model=model_name(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **_extra(),
    )
    _count(completion)
    return (completion.choices[0].message.content or "").strip()
