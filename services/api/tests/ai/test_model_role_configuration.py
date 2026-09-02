import pytest
from clearcut.ai.model_roles import (
    GeminiRole,
    ModelRoleConfigurationError,
    resolve_model_role,
)


@pytest.mark.parametrize(
    ("role", "environment_variable", "expected_model"),
    [
        (
            GeminiRole.DETECTION,
            "CLEARCUT_GEMINI_DETECTION_MODEL",
            "gemini-3.7-flash",
        ),
        (
            GeminiRole.RESEARCH_PLANNING,
            "CLEARCUT_GEMINI_RESEARCH_MODEL",
            "gemini-3.1-flash-lite",
        ),
        (
            GeminiRole.JUDGE,
            "CLEARCUT_GEMINI_JUDGE_MODEL",
            "gemini-3.1-pro-preview",
        ),
    ],
)
def test_model_roles_have_explicit_production_defaults(
    monkeypatch,
    role: GeminiRole,
    environment_variable: str,
    expected_model: str,
) -> None:
    monkeypatch.delenv(environment_variable, raising=False)

    configuration = resolve_model_role(role)

    assert configuration.role is role
    assert configuration.model == expected_model
    assert configuration.environment_variable == environment_variable
    assert configuration.overridden is False


def test_model_role_override_is_isolated_to_requested_role(monkeypatch) -> None:
    monkeypatch.setenv("CLEARCUT_GEMINI_DETECTION_MODEL", "custom-detection-model")
    monkeypatch.delenv("CLEARCUT_GEMINI_JUDGE_MODEL", raising=False)

    detection = resolve_model_role(GeminiRole.DETECTION)
    judge = resolve_model_role(GeminiRole.JUDGE)

    assert detection.model == "custom-detection-model"
    assert detection.overridden is True
    assert judge.model == "gemini-3.1-pro-preview"
    assert judge.overridden is False


def test_blank_model_override_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("CLEARCUT_GEMINI_JUDGE_MODEL", "   ")

    with pytest.raises(ModelRoleConfigurationError, match="must not be blank"):
        resolve_model_role(GeminiRole.JUDGE)
