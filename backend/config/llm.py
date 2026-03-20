"""
AdEngineAI — LLM Configuration
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from dotenv import load_dotenv
load_dotenv()

AgentName = Literal["researcher", "director", "production", "qa", "publisher"]

class LLMProvider(str, Enum):
    GROQ = "groq"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

@dataclass(frozen=True)
class LLMConfig:
    provider: LLMProvider
    model: str
    api_key: str
    max_tokens: int
    temperature: float

    def is_dev(self) -> bool:
        return self.provider == LLMProvider.GROQ

    def is_prod(self) -> bool:
        return self.provider in (LLMProvider.ANTHROPIC, LLMProvider.OPENAI)

_DEV_MODELS: dict[str, str] = {
    "researcher": os.getenv("GROQ_MODEL_RESEARCHER", "llama-3.3-70b-versatile"),
    "director":   os.getenv("GROQ_MODEL_DIRECTOR",   "moonshotai/kimi-k2-instruct"),
    "production": os.getenv("GROQ_MODEL_PRODUCTION", "llama-3.1-8b-instant"),
    "qa":         os.getenv("GROQ_MODEL_QA",         "llama-3.3-70b-versatile"),
    "publisher":  os.getenv("GROQ_MODEL_PUBLISHER",  "llama-3.1-8b-instant"),
}

_PROD_MODELS: dict[str, tuple[LLMProvider, str]] = {
    "researcher": (LLMProvider.ANTHROPIC, "claude-sonnet-4-5"),
    "director":   (LLMProvider.ANTHROPIC, "claude-sonnet-4-5"),
    "production": (LLMProvider.OPENAI,    "gpt-4o-mini"),
    "qa":         (LLMProvider.ANTHROPIC, "claude-sonnet-4-5"),
    "publisher":  (LLMProvider.OPENAI,    "gpt-4o-mini"),
}

_MAX_TOKENS: dict[str, int] = {
    "researcher": 2000,
    "director":   4000,
    "production": 500,
    "qa":         1000,
    "publisher":  500,
}

_TEMPERATURE: dict[str, float] = {
    "researcher": 0.2,
    "director":   0.8,
    "production": 0.1,
    "qa":         0.1,
    "publisher":  0.1,
}

def get_llm_config(agent: AgentName) -> LLMConfig:
    env = os.getenv("LLM_ENV", "development").lower()
    if env == "development":
        return _build_dev_config(agent)
    elif env == "production":
        return _build_prod_config(agent)
    else:
        raise ValueError(f"Invalid LLM_ENV='{env}'. Must be 'development' or 'production'.")

def get_current_env() -> str:
    return os.getenv("LLM_ENV", "development").lower()

def _build_dev_config(agent: AgentName) -> LLMConfig:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set.")
    return LLMConfig(
        provider=LLMProvider.GROQ,
        model=_DEV_MODELS[agent],
        api_key=api_key,
        max_tokens=_MAX_TOKENS[agent],
        temperature=_TEMPERATURE[agent],
    )

def _build_prod_config(agent: AgentName) -> LLMConfig:
    provider, model = _PROD_MODELS[agent]
    if provider == LLMProvider.ANTHROPIC:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
    else:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set.")
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        max_tokens=_MAX_TOKENS[agent],
        temperature=_TEMPERATURE[agent],
    )
