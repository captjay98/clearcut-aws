"""Safe same-origin delivery for the Astro site and TanStack workspace."""

from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _validated_distribution(path: Path, *, label: str) -> tuple[Path, Path]:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"Configured {label} distribution directory does not exist: {path}")

    index = (root / "index.html").resolve()
    if not index.is_relative_to(root) or not index.is_file():
        raise RuntimeError(f"Configured {label} distribution index.html does not exist: {index}")
    return root, index


def _decoded_relative_path(value: str) -> Path:
    decoded = value
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value

    if "\\" in decoded or "\x00" in decoded:
        raise _not_found()
    relative = PurePosixPath(decoded)
    if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
        raise _not_found()
    return Path(*relative.parts)


def _resolved_candidate(root: Path, requested_path: str) -> Path:
    candidate = (root / _decoded_relative_path(requested_path)).resolve()
    if not candidate.is_relative_to(root):
        raise _not_found()
    return candidate


def _exact_file(root: Path, requested_path: str) -> FileResponse:
    candidate = _resolved_candidate(root, requested_path)
    if not candidate.is_file():
        raise _not_found()
    return FileResponse(candidate)


def _public_file(site_root: Path, requested_path: str) -> FileResponse:
    candidate = _resolved_candidate(site_root, requested_path)
    if candidate.is_file():
        return FileResponse(candidate)

    directory_index = (candidate / "index.html").resolve()
    if directory_index.is_relative_to(site_root) and directory_index.is_file():
        return FileResponse(directory_index)

    html_file = candidate.with_suffix(".html").resolve()
    if html_file.is_relative_to(site_root) and html_file.is_file():
        return FileResponse(html_file)
    raise _not_found()


def install_same_origin_routes(
    app: FastAPI,
    *,
    site_dist: Path,
    workspace_dist: Path,
) -> None:
    """Install static routes after API routers, failing on invalid distributions."""
    site_root, site_index = _validated_distribution(site_dist, label="site")
    workspace_root, workspace_index = _validated_distribution(
        workspace_dist,
        label="workspace",
    )
    astro_assets = site_root / "_astro"
    workspace_assets = workspace_root / "assets"

    async def serve_astro_asset(asset_path: str) -> FileResponse:
        return _exact_file(astro_assets, asset_path)

    async def serve_workspace_asset(asset_path: str) -> FileResponse:
        return _exact_file(workspace_assets, asset_path)

    async def serve_workspace_root() -> FileResponse:
        return FileResponse(workspace_index)

    async def serve_workspace_path(workspace_path: str) -> FileResponse:
        candidate = _resolved_candidate(workspace_root, workspace_path)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(workspace_index)

    async def serve_public_root() -> FileResponse:
        return FileResponse(site_index)

    async def serve_public_path(public_path: str) -> FileResponse:
        if public_path == "api" or public_path.startswith("api/"):
            raise _not_found()
        if public_path == "healthz":
            raise _not_found()
        return _public_file(site_root, public_path)

    app.add_api_route(
        "/_astro/{asset_path:path}",
        serve_astro_asset,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/app/assets/{asset_path:path}",
        serve_workspace_asset,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/app",
        serve_workspace_root,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/app/{workspace_path:path}",
        serve_workspace_path,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/",
        serve_public_root,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/{public_path:path}",
        serve_public_path,
        methods=["GET"],
        include_in_schema=False,
    )
