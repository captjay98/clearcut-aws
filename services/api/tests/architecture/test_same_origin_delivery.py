"""Same-origin delivery contract for the public site, workspace, and API."""

from pathlib import Path

import pytest
from clearcut.bootstrap.settings import ClearcutSettings
from clearcut.main import create_app
from clearcut.static_delivery import install_same_origin_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient

SITE_INDEX = "<html>public-site</html>"
WORKSPACE_INDEX = "<html>workspace</html>"


def _write_distributions(tmp_path: Path) -> tuple[Path, Path]:
    site_dist = tmp_path / "site-dist"
    workspace_dist = tmp_path / "workspace-dist"

    (site_dist / "features").mkdir(parents=True)
    (site_dist / "docs").mkdir()
    (site_dist / "api").mkdir()
    (site_dist / "_astro").mkdir()
    (site_dist / "index.html").write_text(SITE_INDEX, encoding="utf-8")
    (site_dist / "features" / "index.html").write_text("<html>features</html>", encoding="utf-8")
    (site_dist / "docs" / "index.html").write_text("<html>public-docs</html>", encoding="utf-8")
    (site_dist / "api" / "private").write_text("reserved-api-file", encoding="utf-8")
    (site_dist / "healthz").write_text("reserved-health-file", encoding="utf-8")
    (site_dist / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    (site_dist / "_astro" / "site.js").write_text("site-asset", encoding="utf-8")
    (site_dist / "private.txt").write_text("site-private", encoding="utf-8")

    (workspace_dist / "assets").mkdir(parents=True)
    (workspace_dist / "index.html").write_text(WORKSPACE_INDEX, encoding="utf-8")
    (workspace_dist / "manifest.webmanifest").write_text("workspace-file", encoding="utf-8")
    (workspace_dist / "assets" / "app.js").write_text("workspace-asset", encoding="utf-8")
    (workspace_dist / "private.txt").write_text("workspace-private", encoding="utf-8")
    return site_dist, workspace_dist


def _minimal_app(site_dist: Path, workspace_dist: Path) -> FastAPI:
    app = FastAPI(
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
    )

    @app.get("/healthz")
    @app.get("/api/v1/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    install_same_origin_routes(
        app,
        site_dist=site_dist,
        workspace_dist=workspace_dist,
    )
    return app


def test_serves_authored_public_routes_files_and_astro_assets(tmp_path: Path) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    client = TestClient(_minimal_app(site_dist, workspace_dist))

    assert client.get("/").text == SITE_INDEX
    assert client.get("/features").text == "<html>features</html>"
    assert client.get("/docs").text == "<html>public-docs</html>"
    assert client.get("/robots.txt").text == "User-agent: *"
    assert client.get("/_astro/site.js").text == "site-asset"


def test_serves_workspace_files_assets_and_client_route_refreshes(tmp_path: Path) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    client = TestClient(_minimal_app(site_dist, workspace_dist))

    assert client.get("/app").text == WORKSPACE_INDEX
    assert client.get("/app/").text == WORKSPACE_INDEX
    assert client.get("/app/auth/sign-in").text == WORKSPACE_INDEX
    assert client.get("/app/manifest.webmanifest").text == "workspace-file"
    assert client.get("/app/assets/app.js").text == "workspace-asset"


def test_api_and_health_routes_never_receive_html_fallback(tmp_path: Path) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    client = TestClient(_minimal_app(site_dist, workspace_dist))

    for path in ("/healthz", "/api/v1/healthz", "/api/not-found"):
        response = client.get(path)
        assert response.headers["content-type"].startswith("application/json")
        assert SITE_INDEX not in response.text
        assert WORKSPACE_INDEX not in response.text
    assert client.get("/api/not-found").status_code == 404


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/api/private", 404),
        ("/%2561pi/private", 404),
        ("/%252561pi/private", 404),
        ("/%2568ealthz", 200),
        ("/%252568ealthz", 404),
    ],
)
def test_encoded_reserved_namespaces_never_serve_public_files(
    tmp_path: Path,
    path: str,
    expected_status: int,
) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    response = TestClient(_minimal_app(site_dist, workspace_dist)).get(path)

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/json")
    assert "reserved-api-file" not in response.text
    assert "reserved-health-file" not in response.text
    assert SITE_INDEX not in response.text
    assert WORKSPACE_INDEX not in response.text


def test_fastapi_docs_and_openapi_use_api_namespace(tmp_path: Path) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    client = TestClient(_minimal_app(site_dist, workspace_dist))

    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/redoc").status_code == 200
    assert client.get("/api/openapi.json").json()["openapi"].startswith("3.")
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").text == "<html>public-docs</html>"


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("site-directory", "site distribution directory"),
        ("site-index", "site distribution index.html"),
        ("workspace-directory", "workspace distribution directory"),
        ("workspace-index", "workspace distribution index.html"),
    ],
)
def test_invalid_configured_distributions_fail_closed(
    tmp_path: Path,
    missing: str,
    message: str,
) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    if missing == "site-directory":
        site_dist = tmp_path / "missing-site"
    elif missing == "site-index":
        (site_dist / "index.html").unlink()
    elif missing == "workspace-directory":
        workspace_dist = tmp_path / "missing-workspace"
    else:
        (workspace_dist / "index.html").unlink()

    with pytest.raises(RuntimeError, match=message):
        install_same_origin_routes(
            FastAPI(),
            site_dist=site_dist,
            workspace_dist=workspace_dist,
        )


@pytest.mark.parametrize(
    "path",
    [
        "/_astro/%2e%2e/private.txt",
        "/_astro/%252e%252e%252fprivate.txt",
        "/app/assets/%2e%2e/private.txt",
        "/app/assets/%252e%252e%252fprivate.txt",
        "/app/%2e%2e%2foutside.txt",
        "/%2e%2e%2foutside.txt",
    ],
)
def test_encoded_traversal_cannot_escape_distribution_roots(
    tmp_path: Path,
    path: str,
) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    (tmp_path / "outside.txt").write_text("outside-secret", encoding="utf-8")
    response = TestClient(_minimal_app(site_dist, workspace_dist)).get(path)

    assert response.status_code == 404
    assert "private" not in response.text
    assert "outside-secret" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/_astro/../../outside.txt",
        "/app/assets/../../../outside.txt",
        "/app/../../outside.txt",
        "/../../outside.txt",
    ],
)
def test_plain_traversal_never_returns_files_outside_distribution_roots(
    tmp_path: Path,
    path: str,
) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    (tmp_path / "outside.txt").write_text("outside-secret", encoding="utf-8")
    response = TestClient(_minimal_app(site_dist, workspace_dist)).get(path)

    assert response.status_code == 404
    assert "outside-secret" not in response.text


def test_create_app_installs_static_delivery_after_api_routes(tmp_path: Path) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    settings = ClearcutSettings.from_environment(
        {
            "CLEARCUT_DEPLOYMENT_PROFILE": "local",
            "CLEARCUT_STATIC_DELIVERY_ENABLED": "true",
            "CLEARCUT_SITE_DIST_PATH": str(site_dist),
            "CLEARCUT_WORKSPACE_DIST_PATH": str(workspace_dist),
            "CLEARCUT_STORAGE_PATH": str(tmp_path / "storage"),
            "CLEARCUT_JOB_DISPATCH_MODE": "disabled",
        }
    )
    client = TestClient(create_app(settings))

    assert client.get("/").text == SITE_INDEX
    assert client.get("/app/auth/sign-in").text == WORKSPACE_INDEX
    assert client.get("/api/v1/healthz").json()["status"] == "ok"
    assert client.get("/api/not-found").headers["content-type"].startswith("application/json")
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200


def test_local_profile_can_explicitly_disable_static_delivery() -> None:
    settings = ClearcutSettings.from_environment(
        {
            "CLEARCUT_DEPLOYMENT_PROFILE": "local",
            "CLEARCUT_STATIC_DELIVERY_ENABLED": "false",
            "CLEARCUT_JOB_DISPATCH_MODE": "disabled",
        }
    )

    assert settings.static_delivery.enabled is False
    assert settings.static_delivery.site_dist is None
    assert settings.static_delivery.workspace_dist is None


def test_unknown_api_path_uses_canonical_error_envelope(tmp_path: Path) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    settings = ClearcutSettings.from_environment(
        {
            "CLEARCUT_DEPLOYMENT_PROFILE": "local",
            "CLEARCUT_STATIC_DELIVERY_ENABLED": "true",
            "CLEARCUT_SITE_DIST_PATH": str(site_dist),
            "CLEARCUT_WORKSPACE_DIST_PATH": str(workspace_dist),
            "CLEARCUT_STORAGE_PATH": str(tmp_path / "storage"),
            "CLEARCUT_JOB_DISPATCH_MODE": "disabled",
        }
    )
    response = TestClient(create_app(settings)).get("/api/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "requestId": response.headers["x-request-id"],
            "retryable": False,
        }
    }


@pytest.mark.parametrize(
    ("link_path", "request_path"),
    [
        ("site-dist/_astro/escape.txt", "/_astro/escape.txt"),
        ("site-dist/public-escape.txt", "/public-escape.txt"),
        ("workspace-dist/assets/escape.txt", "/app/assets/escape.txt"),
        ("workspace-dist/workspace-escape.txt", "/app/workspace-escape.txt"),
    ],
)
def test_symlinks_cannot_escape_distribution_roots(
    tmp_path: Path,
    link_path: str,
    request_path: str,
) -> None:
    site_dist, workspace_dist = _write_distributions(tmp_path)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside-secret", encoding="utf-8")
    (tmp_path / link_path).symlink_to(outside)

    response = TestClient(_minimal_app(site_dist, workspace_dist)).get(request_path)

    assert response.status_code == 404
    assert "outside-secret" not in response.text


@pytest.mark.parametrize(
    ("static_environment", "message"),
    [
        (
            {
                "CLEARCUT_STATIC_DELIVERY_ENABLED": "false",
                "CLEARCUT_SITE_DIST_PATH": "/tmp/unused-site-dist",
            },
            "cannot be configured while static delivery is disabled",
        ),
        (
            {
                "CLEARCUT_STATIC_DELIVERY_ENABLED": "true",
                "CLEARCUT_SITE_DIST_PATH": "/tmp/incomplete-site-dist",
            },
            "requires both site and workspace distribution paths",
        ),
    ],
)
def test_create_app_rejects_inconsistent_static_delivery_configuration(
    static_environment: dict[str, str],
    message: str,
) -> None:
    settings = ClearcutSettings.from_environment(
        {
            "CLEARCUT_DEPLOYMENT_PROFILE": "local",
            "CLEARCUT_JOB_DISPATCH_MODE": "disabled",
            **static_environment,
        }
    )

    with pytest.raises(RuntimeError, match=message):
        create_app(settings)
