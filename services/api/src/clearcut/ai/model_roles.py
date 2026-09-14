"""Typed model-role configuration with no implicit fallback switching."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class GeminiRole(StrEnum):
    DETECTION = "detection"
    RESEARCH_PLANNING = "research_planning"
    JUDGE = "judge"


class BedrockRole(StrEnum):
    DETECTION = "detection"
    RESEARCH_PLANNING = "research_planning"
    CLAIM_SYNTHESIS = "claim_synthesis"
    JUDGE = "judge"


class ModelRoleConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelRoleConfiguration:
    role: GeminiRole | BedrockRole
    model: str
    environment_variable: str
    overridden: bool


_ROLE_SETTINGS = {
    GeminiRole.DETECTION: (
        "CLEARCUT_GEMINI_DETECTION_MODEL",
        "gemini-3.7-flash",
    ),
    GeminiRole.RESEARCH_PLANNING: (
        "CLEARCUT_GEMINI_RESEARCH_MODEL",
        "gemini-3.1-flash-lite",
    ),
    GeminiRole.JUDGE: (
        "CLEARCUT_GEMINI_JUDGE_MODEL",
        "gemini-3.1-pro-preview",
    ),
}

_BEDROCK_ROLE_SETTINGS = {
    BedrockRole.DETECTION: (
        "CLEARCUT_BEDROCK_DETECTION_MODEL",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ),
    BedrockRole.RESEARCH_PLANNING: (
        "CLEARCUT_BEDROCK_RESEARCH_MODEL",
        "anthropic.claude-3-haiku-20240307-v1:0",
    ),
    BedrockRole.CLAIM_SYNTHESIS: (
        "CLEARCUT_BEDROCK_SYNTHESIS_MODEL",
        "anthropic.claude-3-haiku-20240307-v1:0",
    ),
    BedrockRole.JUDGE: (
        "CLEARCUT_BEDROCK_JUDGE_MODEL",
        "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ),
}


def resolve_model_role(role: GeminiRole) -> ModelRoleConfiguration:
    """Resolve one Gemini role without consulting or switching to another role's model."""
    environment_variable, default_model = _ROLE_SETTINGS[role]
    configured_model = os.getenv(environment_variable)
    if configured_model is not None and not configured_model.strip():
        raise ModelRoleConfigurationError(
            f"{environment_variable} must not be blank when configured."
        )
    return ModelRoleConfiguration(
        role=role,
        model=configured_model.strip() if configured_model is not None else default_model,
        environment_variable=environment_variable,
        overridden=configured_model is not None,
    )


def resolve_bedrock_role(role: BedrockRole) -> ModelRoleConfiguration:
    """Resolve one Bedrock role without consulting or switching to another role's model."""
    environment_variable, default_model = _BEDROCK_ROLE_SETTINGS[role]
    configured_model = os.getenv(environment_variable)
    if configured_model is not None and not configured_model.strip():
        raise ModelRoleConfigurationError(
            f"{environment_variable} must not be blank when configured."
        )
    return ModelRoleConfiguration(
        role=role,
        model=configured_model.strip() if configured_model is not None else default_model,
        environment_variable=environment_variable,
        overridden=configured_model is not None,
    )
