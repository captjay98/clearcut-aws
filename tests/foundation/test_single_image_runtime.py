"""Provider-free contracts for the single production container artifact."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def docker_source() -> str:
    return (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_root_image_builds_and_copies_both_frontends() -> None:
    source = docker_source()
    for app in ("site", "web"):
        assert f"COPY apps/{app}/" in source
        assert re.search(rf"RUN .*pnpm --filter clearcut-{app} build", source)
        assert re.search(
            rf"COPY --from=frontend-build /app/apps/{app}/dist /app/{app}-dist", source
        )
    assert "CLEARCUT_STATIC_DELIVERY_ENABLED=true" in source
    assert "CLEARCUT_SITE_DIST_PATH=/app/site-dist" in source
    assert "CLEARCUT_WORKSPACE_DIST_PATH=/app/web-dist" in source
    assert "WEB_DIST_PATH=" not in source


def test_container_installs_locked_workspace_dependencies_without_fallback() -> None:
    source = docker_source()
    assert "pnpm-lock.yaml pnpm-workspace.yaml" in source
    assert "pnpm install --frozen-lockfile" in source
    assert "COPY pyproject.toml uv.lock" in source
    assert "uv sync --frozen --no-dev --no-install-workspace --package clearcut-api" in source
    assert not re.search(r"(?:install|sync).*\|\|", source)


def test_runtime_contains_api_and_explicit_migration_tools_without_host_state() -> None:
    source = docker_source()
    assert "COPY services/api/src/ /app/api/src/" in source
    assert "COPY services/api/alembic/ /app/api/alembic/" in source
    assert "COPY services/api/alembic.ini /app/api/alembic.ini" in source
    assert "COPY services/api/scripts/ /app/api/scripts/" in source
    assert not re.search(r"^COPY services/api/ /app/api", source, re.MULTILINE)
    assert 'PATH="/app/.venv/bin:$PATH"' in source
    assert 'PYTHONPATH="/app/api/src"' in source
    assert "USER 1001" in source
    assert 'ENTRYPOINT ["tini", "--"]' in source
    command = json.loads(re.search(r"^CMD (.+)$", source, re.MULTILINE).group(1))
    assert command[:2] == ["sh", "-c"]
    assert command[2].startswith("exec uvicorn clearcut.main:app")
    assert "alembic" not in command[2]
    assert '${CLEARCUT_API_WORKERS:-${WEB_CONCURRENCY:-1}}' in command[2]


def test_compose_application_roles_share_one_production_image() -> None:
    config = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = config["services"]
    roles = [services[name] for name in ("app", "migrate", "seed")]
    assert {role["image"] for role in roles} == {"clearcut:local"}
    assert all(role["build"] == {"context": ".", "dockerfile": "Dockerfile"} for role in roles)
    assert services["app"]["restart"] == "unless-stopped"
    assert services["migrate"]["restart"] == services["seed"]["restart"] == "no"
    for role in roles:
        assert role["environment"]["CLEARCUT_API_WORKERS"] == "${CLEARCUT_API_WORKERS:-1}"
        assert role["environment"]["CLEARCUT_JOB_DISPATCH_MODE"] == "${CLEARCUT_JOB_DISPATCH_MODE:-local}"


def test_cloudbuild_publishes_only_the_clearcut_revision_artifact() -> None:
    source = (ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")
    config = yaml.safe_load(source)
    expected = "${_REGISTRY_HOST}/$PROJECT_ID/${_REPOSITORY}/clearcut:sha-$COMMIT_SHA"
    assert config["images"] == [expected]
    build = next(step for step in config["steps"] if step["args"][0] == "build")
    assert build["args"][build["args"].index("--tag") + 1] == expected
    assert build["args"][-1] == "."
    assert "org.opencontainers.image.revision=$COMMIT_SHA" in build["args"]
    assert all(name not in source for name in ("clearcut-site", "clearcut-web", "clearcut-api"))
