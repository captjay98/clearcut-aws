"""Typed Gemini model-role configuration with no implicit fallback switching."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class GeminiRole(StrEnum):
    DETECTION = "detection"
    RESEARCH_PLANNING = "research_planning"
    JUDGE = "judge"


class ModelRoleConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelRoleConfiguration:
    role: GeminiRole
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


def resolve_model_role(role: GeminiRole) -> ModelRoleConfiguration:
    """Resolve one role without consulting or switching to another role's model."""
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
