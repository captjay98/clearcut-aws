import pytest
from clearcut.scripts.adapters.pdf_parser import MAX_PDF_PAGES, PdfParseError, PdfParser
from clearcut.scripts.domain.elements import ElementType
from screenplay_pdf import (
    CHARACTER,
    DIALOGUE,
    MARGIN,
    POINTS_PER_INCH,
    PageBuilder,
    build_pdf,
    sample_screenplay_pdf,
)


def _types(result):
    return [element.element_type for element in result.elements]


def _text_of(result, element_type):
    return [e.text for e in result.elements if e.element_type == element_type]


def test_classifies_every_element_type_from_page_geometry():
    result = PdfParser().parse(sample_screenplay_pdf(), "Borrowed-Light.pdf")

    assert _types(result) == [
        ElementType.SCENE_HEADING,
        ElementType.ACTION,
        ElementType.CHARACTER,
        ElementType.PARENTHETICAL,
        ElementType.DIALOGUE,
        ElementType.ACTION,
        ElementType.TRANSITION,
        ElementType.SCENE_HEADING,
        ElementType.ACTION,
        ElementType.CHARACTER,
        ElementType.DIALOGUE,
        ElementType.TRANSITION,
    ]
    assert result.parser_name == "PdfParser"


def test_joins_wrapped_lines_into_one_element():
    """A visual line break is a property of the page, not of the screenplay."""
    result = PdfParser().parse(sample_screenplay_pdf(), "Borrowed-Light.pdf")

    assert (
        "Rain hammers the skylight. MARA crouches over a battered Vega Camera, "
        "thumbing the shutter dial." in _text_of(result, ElementType.ACTION)
    )
    assert "This thing still runs. Forty years and it still runs." in _text_of(
        result, ElementType.DIALOGUE
    )


def test_numbers_scenes_and_records_source_pages():
    result = PdfParser().parse(sample_screenplay_pdf(), "Borrowed-Light.pdf")

    headings = [e for e in result.elements if e.element_type == ElementType.SCENE_HEADING]
    assert [e.scene_number for e in headings] == [1, 2]
    assert [e.page_number for e in headings] == [1, 2]
    assert all(e.scene_number == 1 for e in result.elements if e.page_number == 1)
    assert all(e.scene_number == 2 for e in result.elements if e.page_number == 2)


def test_ordinals_are_dense_and_sequential():
    result = PdfParser().parse(sample_screenplay_pdf(), "Borrowed-Light.pdf")

    assert [e.ordinal for e in result.elements] == list(range(1, len(result.elements) + 1))


def test_identical_bytes_produce_identical_elements():
    """Selective rescan diffs passages, so classification must not drift."""
    data = sample_screenplay_pdf()
    first = PdfParser().parse(data, "Borrowed-Light.pdf")
    second = PdfParser().parse(data, "Borrowed-Light.pdf")

    assert [(e.ordinal, e.element_type, e.text, e.page_number) for e in first.elements] == [
        (e.ordinal, e.element_type, e.text, e.page_number) for e in second.elements
    ]
    assert [(w.warning_code, w.message) for w in first.warnings] == [
        (w.warning_code, w.message) for w in second.warnings
    ]


def test_strips_page_numbers_and_continuation_markers():
    page = PageBuilder()
    page.put(MARGIN, "INT. KITCHEN - DAY")
    page.blank()
    page.put(CHARACTER, "SAM")
    page.put(DIALOGUE, "Half a line.")
    page.put(CHARACTER, "(MORE)")
    page.footer(4.0 * POINTS_PER_INCH, "12.")

    result = PdfParser().parse(build_pdf([page.lines], title="Kitchen"), "kitchen.pdf")
    texts = [element.text for element in result.elements]

    assert "(MORE)" not in texts
    assert "12." not in texts
    assert "12" not in texts


def test_reports_printed_page_numbers_that_disagree_with_document_order():
    page = PageBuilder()
    page.put(MARGIN, "INT. KITCHEN - DAY")
    page.put(MARGIN, "Sam stares at the kettle.")
    page.footer(4.0 * POINTS_PER_INCH, "52.")

    result = PdfParser().parse(build_pdf([page.lines], title="Kitchen"), "kitchen.pdf")
    codes = {warning.warning_code for warning in result.warnings}

    assert "pdf_page_numbering_normalised" in codes
    message = next(
        w.message for w in result.warnings if w.warning_code == "pdf_page_numbering_normalised"
    )
    assert "prints as 52" in message


def test_strips_production_scene_numbers_beside_headings_and_warns():
    page = PageBuilder()
    page.put(MARGIN, "14   INT. WAREHOUSE - NIGHT")
    page.put(MARGIN, "Mara waits.")
    page.blank()
    page.put(CHARACTER, "MARA")
    page.put(DIALOGUE, "Now.")

    result = PdfParser().parse(build_pdf([page.lines], title="Numbered"), "numbered.pdf")
    headings = _text_of(result, ElementType.SCENE_HEADING)

    assert headings == ["INT. WAREHOUSE - NIGHT"]
    assert "pdf_scene_numbers_stripped" in {w.warning_code for w in result.warnings}


def test_numbered_action_lines_keep_their_numbers():
    """Only scene headings shed edge numbers, so ordinary text is untouched."""
    page = PageBuilder()
    page.put(MARGIN, "INT. WAREHOUSE - NIGHT")
    page.put(MARGIN, "14   crates are stacked against the wall.")

    result = PdfParser().parse(build_pdf([page.lines], title="Crates"), "crates.pdf")

    assert "14   crates are stacked against the wall." in _text_of(result, ElementType.ACTION)


def test_reports_pages_without_extractable_text_and_never_infers_them():
    populated = PageBuilder()
    populated.put(MARGIN, "INT. WAREHOUSE - NIGHT")
    populated.put(MARGIN, "Mara waits.")
    populated.blank()
    populated.put(CHARACTER, "MARA")
    populated.put(DIALOGUE, "Now.")

    result = PdfParser().parse(build_pdf([populated.lines, [], []], title="Mixed"), "mixed.pdf")
    warning = next(w for w in result.warnings if w.warning_code == "pdf_pages_without_text")

    assert "2 of 3 pages" in warning.message
    assert "2\u20133" in warning.message
    assert {element.page_number for element in result.elements} == {1}


def test_rejects_a_document_with_no_extractable_text():
    with pytest.raises(PdfParseError) as caught:
        PdfParser().parse(build_pdf([[], []], title="Scanned"), "scanned.pdf")

    assert caught.value.code == "PDF_NO_EXTRACTABLE_TEXT"
    assert "scanned image" in str(caught.value)


def test_rejects_an_encrypted_document_with_actionable_copy():
    with pytest.raises(PdfParseError) as caught:
        PdfParser().parse(sample_screenplay_pdf_encrypted(), "locked.pdf")

    assert caught.value.code == "PDF_ENCRYPTED_NO_PASSWORD"
    assert "unprotected copy" in str(caught.value)


def sample_screenplay_pdf_encrypted() -> bytes:
    page = PageBuilder()
    page.put(MARGIN, "INT. WAREHOUSE - NIGHT")
    return build_pdf([page.lines], title="Locked", encrypt_marker=True)


def test_rejects_bytes_that_are_not_a_pdf():
    with pytest.raises(PdfParseError) as caught:
        PdfParser().parse(b"Title: Not a PDF\n\nINT. ROOM - DAY\n", "fake.pdf")

    assert caught.value.code in {"PDF_MALFORMED", "PDF_EMPTY"}


def test_rejects_documents_beyond_the_page_limit():
    page = PageBuilder()
    page.put(MARGIN, "INT. ROOM - DAY")
    oversized = build_pdf([page.lines] * (MAX_PDF_PAGES + 1), title="Long")

    with pytest.raises(PdfParseError) as caught:
        PdfParser().parse(oversized, "long.pdf")

    assert caught.value.code == "PDF_TOO_MANY_PAGES"


def test_prefers_document_title_over_filename():
    result = PdfParser().parse(sample_screenplay_pdf(title="Borrowed Light"), "whatever.pdf")

    assert result.title == "Borrowed Light"


def test_falls_back_to_the_filename_when_metadata_carries_no_title():
    result = PdfParser().parse(sample_screenplay_pdf(title=None), "borrowed-light_v2.pdf")

    assert result.title == "Borrowed Light V2"


def test_flat_documents_report_missing_dialogue_geometry():
    page = PageBuilder()
    page.put(MARGIN, "INT. WAREHOUSE - NIGHT")
    page.put(MARGIN, "Nothing but action lines here.")
    page.put(MARGIN, "And another one.")

    result = PdfParser().parse(build_pdf([page.lines], title="Flat"), "flat.pdf")

    assert "pdf_no_dialogue_geometry" in {w.warning_code for w in result.warnings}
    assert set(_types(result)) == {ElementType.SCENE_HEADING, ElementType.ACTION}


def test_character_extensions_do_not_become_dialogue():
    page = PageBuilder()
    page.put(MARGIN, "INT. BOOTH - DAY")
    page.blank()
    page.put(CHARACTER, "NARRATOR (V.O.)")
    page.put(DIALOGUE, "It began in the rain.")

    result = PdfParser().parse(build_pdf([page.lines], title="Booth"), "booth.pdf")

    assert _text_of(result, ElementType.CHARACTER) == ["NARRATOR (V.O.)"]
    assert _text_of(result, ElementType.DIALOGUE) == ["It began in the rain."]


def test_transitions_are_recognised_regardless_of_indentation():
    page = PageBuilder()
    page.put(MARGIN, "INT. HALL - DAY")
    page.put(MARGIN, "A door closes.")
    page.blank()
    page.put(MARGIN, "DISSOLVE TO:")
    page.blank()
    page.put(CHARACTER, "SAM")
    page.put(DIALOGUE, "Later.")

    result = PdfParser().parse(build_pdf([page.lines], title="Hall"), "hall.pdf")

    assert _text_of(result, ElementType.TRANSITION) == ["DISSOLVE TO:"]


def test_a_page_break_ends_an_element_even_within_one_paragraph():
    first = PageBuilder()
    first.put(MARGIN, "INT. WAREHOUSE - NIGHT")
    first.put(MARGIN, "The sentence begins on this page")
    second = PageBuilder()
    second.put(MARGIN, "and continues onto the next.")
    second.blank()
    second.put(CHARACTER, "MARA")
    second.put(DIALOGUE, "Enough.")

    result = PdfParser().parse(build_pdf([first.lines, second.lines], title="Split"), "split.pdf")
    actions = [e for e in result.elements if e.element_type == ElementType.ACTION]

    assert [e.text for e in actions] == [
        "The sentence begins on this page",
        "and continues onto the next.",
    ]
    assert [e.page_number for e in actions] == [1, 2]
