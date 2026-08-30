from dataclasses import FrozenInstanceError

import pytest
import uuid6
from clearcut.scripts.domain.elements import ElementType, ScriptElement
from clearcut.scripts.domain.versions import ScriptVersion


def test_committed_version_is_immutable():
    version_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()

    elem = ScriptElement.create(
        element_id=uuid6.uuid7(),
        version_id=version_id,
        ordinal=1,
        element_type=ElementType.SCENE_HEADING,
        text="INT. CAFE - DAY",
        scene_number=1,
    )

    version = ScriptVersion.create(
        version_id=version_id,
        script_id=script_id,
        org_id=org_id,
        project_id=project_id,
        ordinal=1,
        source_hash="sha256_hash",
        elements=[elem],
    )

    assert version.ordinal == 1
    assert len(version.elements) == 1

    # Immutability check: frozen dataclass / tuple
    with pytest.raises(FrozenInstanceError):
        version.ordinal = 2  # type: ignore
