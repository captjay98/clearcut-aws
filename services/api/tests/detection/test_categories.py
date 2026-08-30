import uuid6
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.scripts.domain.elements import ElementType, ScriptElement


def test_ten_protected_categories_exist():
    assert len(ClearanceCategory) == 10
    expected = {
        "real_persons_living",
        "real_persons_deceased",
        "corporate_entities",
        "products_and_trademarks",
        "copyrighted_works",
        "music_and_lyrics",
        "locations_and_landmarks",
        "vehicles_and_insignia",
        "sensitive_historical_events",
        "contact_information",
    }
    assert {c.value for c in ClearanceCategory} == expected


def test_candidate_detection_across_categories():
    runtime = HermeticDetectionRuntime()

    elem_id = uuid6.uuid7()
    action = ScriptElement.create(
        element_id=elem_id,
        ordinal=1,
        element_type=ElementType.ACTION,
        text=(
            "Tom Cruise drinks a cold Coca-Cola while listening to Bohemian Rhapsody "
            "in front of the Chrysler Building."
        ),
    )

    candidates = runtime.detect_candidates([action])
    assert len(candidates) >= 3

    categories = {c.category for c in candidates}
    assert (
        ClearanceCategory.REAL_PERSONS_LIVING in categories
        or ClearanceCategory.PRODUCTS_AND_TRADEMARKS in categories
    )
    assert (
        ClearanceCategory.MUSIC_AND_LYRICS in categories
        or ClearanceCategory.LOCATIONS_AND_LANDMARKS in categories
    )
