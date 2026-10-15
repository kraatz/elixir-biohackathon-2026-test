"""agent.yaml (rendered by Ansible) and the secrets from the environment."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_ai.usage import UsageLimits

ANTHROPIC_MODELS = frozenset({"claude-haiku-5-5"})


class ConfigError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelCfg(_Strict):
    provider: Literal["openai_compatible", "anthropic"] = "openai_compatible"
    name: str
    base_url: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ModelCfg":
        if self.provider == "anthropic" and self.name not in ANTHROPIC_MODELS:
            raise ValueError(f"anthropic provider: only {', '.join(sorted(ANTHROPIC_MODELS))} is allowed, got {self.name}")
        if self.provider == "openai_compatible" and not self.base_url:
            raise ValueError("openai_compatible provider needs model.base_url")
        return self


class PromptCfg(_Strict):
    file: Path
    include_sandbox_prompt: bool = True


class ToolsCfg(_Strict):
    surface: Literal["shell", "typed"] = "shell"
    sandbox_url: str
    sandbox_operations: Literal["all"] | list[str] = "all"
    max_output_bytes: int = 16384

    @model_validator(mode="after")
    def _check(self) -> "ToolsCfg":
        if self.surface == "typed":
            raise ValueError("tools.surface 'typed' is reserved and not implemented yet; use 'shell'")
        return self


class LimitsCfg(_Strict):
    request_limit: int = 50
    tool_calls_limit: int = 100
    total_tokens_limit: int = 400_000

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class Config(_Strict):
    model: ModelCfg
    prompt: PromptCfg
    tools: ToolsCfg
    limits: LimitsCfg = LimitsCfg()
    run_log: Path = Path("/var/lib/spe-agent/runs.jsonl")


class Secrets(BaseModel):
    agent_api_key: str
    sandbox_api_key: str
    llm_api_key: str

    def values(self) -> list[str]:
        return [self.agent_api_key, self.sandbox_api_key, self.llm_api_key]


def load_config(path: Path) -> Config:
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return Config.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as e:
        raise ConfigError(f"{path}: {e}") from e


def load_secrets(cfg: Config, environ: Mapping[str, str]) -> Secrets:
    llm_var = "ANTHROPIC_API_KEY" if cfg.model.provider == "anthropic" else "OPENAI_API_KEY"
    names = {"agent_api_key": "SPE_AGENT_API_KEY", "sandbox_api_key": "SANDBOX_API_KEY", "llm_api_key": llm_var}
    missing = [var for var in names.values() if not environ.get(var)]
    if missing:
        raise ConfigError(f"missing environment variables: {', '.join(missing)}")
    return Secrets(**{field: environ[var] for field, var in names.items()})
