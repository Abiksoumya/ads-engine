"""
AdEngineAI — LLM Client Factory
=================================
Builds the actual SDK client from an LLMConfig.
Agents call build_client() — they never import groq/anthropic/openai directly.

Usage in any agent:
    from config.llm import get_llm_config
    from config.llm_client import build_client, complete

    cfg = get_llm_config("director")
    response_text = await complete(cfg, system_prompt, user_prompt)

That's it. One function call, works in both dev and prod.
"""

import json
import logging
from typing import Optional

from config.llm import LLMConfig, LLMProvider  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


async def complete(
    cfg: LLMConfig,
    system: str,
    user: str,
    json_mode: bool = False,
) -> str:
    """
    Unified completion function — works with Groq, Anthropic, and OpenAI.

    Args:
        cfg:       LLMConfig from get_llm_config()
        system:    System prompt string
        user:      User prompt string
        json_mode: If True, instructs the model to return valid JSON only.
                   Adds a reminder to the system prompt automatically.

    Returns:
        Raw response string. If json_mode=True, caller should json.loads() it.
    """
    if json_mode:
        system = system + "\n\nRespond with valid JSON only. No markdown, no explanation, no preamble."

    logger.debug(f"LLM call — provider={cfg.provider} model={cfg.model} json={json_mode}")

    if cfg.provider == LLMProvider.GROQ:
        return await _complete_groq(cfg, system, user)
    elif cfg.provider == LLMProvider.ANTHROPIC:
        return await _complete_anthropic(cfg, system, user)
    elif cfg.provider == LLMProvider.OPENAI:
        return await _complete_openai(cfg, system, user)
    else:
        raise ValueError(f"Unknown provider: {cfg.provider}")


async def complete_json(cfg: LLMConfig, system: str, user: str) -> dict:
    """
    Convenience wrapper — calls complete() with json_mode=True and parses result.
    Strips accidental markdown fences before parsing.

    Raises json.JSONDecodeError if the model returns invalid JSON.
    """
    raw = await complete(cfg, system, user, json_mode=True)
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

async def _complete_groq(cfg: LLMConfig, system: str, user: str) -> str:
    try:
        from groq import AsyncGroq
    except ImportError:
        raise ImportError("groq package not installed. Run: pip install groq")

    client = AsyncGroq(api_key=cfg.api_key)
    response = await client.chat.completions.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content or ""


async def _complete_anthropic(cfg: LLMConfig, system: str, user: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.AsyncAnthropic(api_key=cfg.api_key)
    response = await client.messages.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text or ""
    return ""


async def _complete_openai(cfg: LLMConfig, system: str, user: str) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    client = AsyncOpenAI(api_key=cfg.api_key)
    response = await client.chat.completions.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content or ""