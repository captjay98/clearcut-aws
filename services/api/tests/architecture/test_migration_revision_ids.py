"""Alembic revision identifiers must fit the column that stores them.

``alembic_version.version_num`` is ``VARCHAR(32)``. SQLite does not enforce
declared string lengths, so an over-long revision id passes every local test and
then fails only when the migration chain is first run against PostgreSQL — which
is the deployment path, and the worst possible place to discover it.

Two revisions had already crossed the limit at 35 and 36 characters before this
guard existed.
"""

import re
from pathlib import Path

import pytest

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"

# Alembic's own default for alembic_version.version_num.
MAX_REVISION_LENGTH = 32

_REVISION = re.compile(r'^revision: str = "([^"]+)"', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision: str \| None = "([^"]+)"', re.MULTILINE)


def _migration_files() -> list[Path]:
    return sorted(path for path in VERSIONS_DIR.glob("*.py") if path.name != "__init__.py")


def test_migration_directory_is_discoverable() -> None:
    """Guard the guard: a bad path would make every assertion below vacuous."""
    assert VERSIONS_DIR.is_dir(), VERSIONS_DIR
    assert len(_migration_files()) > 0


@pytest.mark.parametrize("path", _migration_files(), ids=lambda path: path.stem)
def test_revision_id_fits_the_alembic_version_column(path: Path) -> None:
    match = _REVISION.search(path.read_text())
    assert match is not None, f"{path.name} declares no revision id"
    revision = match.group(1)
    assert len(revision) <= MAX_REVISION_LENGTH, (
        f"{path.name} declares a {len(revision)}-character revision id "
        f"{revision!r}, which does not fit alembic_version.version_num "
        f"VARCHAR({MAX_REVISION_LENGTH}). PostgreSQL rejects it; SQLite does not."
    )


@pytest.mark.parametrize("path", _migration_files(), ids=lambda path: path.stem)
def test_revision_id_matches_its_filename(path: Path) -> None:
    """A rename that misses either half leaves a chain nothing can resolve."""
    match = _REVISION.search(path.read_text())
    assert match is not None, f"{path.name} declares no revision id"
    assert match.group(1) == path.stem, (
        f"{path.name} declares revision id {match.group(1)!r}, which does not "
        "match its filename."
    )


def test_every_down_revision_resolves_to_a_real_revision() -> None:
    """A dangling down_revision is an unrunnable chain, not a lint nit."""
    revisions: set[str] = set()
    edges: dict[str, str] = {}
    for path in _migration_files():
        text = path.read_text()
        revision_match = _REVISION.search(text)
        assert revision_match is not None, f"{path.name} declares no revision id"
        revisions.add(revision_match.group(1))
        down_match = _DOWN_REVISION.search(text)
        if down_match is not None:
            edges[revision_match.group(1)] = down_match.group(1)

    dangling = {
        revision: parent for revision, parent in edges.items() if parent not in revisions
    }
    assert dangling == {}, f"down_revision targets that do not exist: {dangling}"


def test_the_chain_is_linear_with_exactly_one_head() -> None:
    """Two heads make ``upgrade head`` ambiguous and stop a deployment."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in _migration_files():
        text = path.read_text()
        revision_match = _REVISION.search(text)
        assert revision_match is not None
        revisions.add(revision_match.group(1))
        down_match = _DOWN_REVISION.search(text)
        if down_match is not None:
            parents.add(down_match.group(1))

    heads = revisions - parents
    assert len(heads) == 1, f"expected exactly one head, found {sorted(heads)}"
