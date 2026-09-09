"""Deterministic screenplay parser for text-based PDF exports.

A PDF carries no element semantics. What it does carry, for every screenplay
produced by a screenwriting application, is the fixed horizontal geometry the
format mandates: action and scene headings sit at the left margin, dialogue is
indented about an inch, parentheticals a little further, character cues further
still, and transitions sit near the right margin. pypdf's layout extraction
preserves that geometry as leading whitespace, so element type can be recovered
from indentation plus a small number of unambiguous textual signals.

The parser is deterministic: identical bytes always yield identical elements, in
identical order, with identical ordinals. That is a hard requirement rather than
a nicety, because selective rescan diffs passages between versions, and a
classifier that labelled the same line differently across two runs would report
phantom changes and re-research passages nobody touched.

Indent thresholds are derived from the document rather than hardcoded in points.
Producers disagree on exact margins, and pypdf normalises each page so its
leftmost glyph sits at column zero, so absolute columns are not portable but the
relative structure is.

What this parser does not do: it does not OCR. Pages that carry no extractable
text are reported as scanned, and a document with no extractable text at all is
rejected. Inventing element text from an image would put unattributable content
into the evidence pipeline.
"""

import io
import re
from collections import Counter
from dataclasses import dataclass

from clearcut.scripts.domain.elements import ElementType, ScriptElement
from clearcut.scripts.domain.versions import ParseResult, ParseWarning
from clearcut.scripts.ports.parser import ScriptParserPort

MAX_PDF_PAGES = 400
"""Refuse documents far longer than any feature screenplay.

Layout extraction cost scales with page count, and the size ceiling upstream
does not bound page count for a highly compressed file.
"""

_SCENE_HEADING = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|EXT\.?/INT|I/E)[.\s]", re.IGNORECASE)
_TRANSITION_TAIL = re.compile(r"\b(TO|IN|OUT|BLACK|UP)\s*[:.]$")
_KNOWN_TRANSITIONS = frozenset(
    {
        "CUT TO:",
        "SMASH CUT TO:",
        "MATCH CUT TO:",
        "JUMP CUT TO:",
        "HARD CUT TO:",
        "DISSOLVE TO:",
        "FADE TO:",
        "FADE IN:",
        "FADE OUT.",
        "FADE OUT",
        "FADE TO BLACK.",
        "FADE TO BLACK",
        "THE END",
        "END OF ACT ONE",
        "END OF ACT TWO",
    }
)
_PRINTED_PAGE_NUMBER = re.compile(r"^(\d{1,4})\s*[.)]?$")
_RUNNING_FURNITURE = frozenset(
    {
        "(MORE)",
        "(CONTINUED)",
        "CONTINUED:",
        "(CONT'D)",
        "(CONT’D)",
        "CONTINUED",
    }
)
_CHARACTER_EXTENSION = re.compile(
    r"\s*\((?:CONT'D|CONT’D|CONTD|V\.O\.|O\.S\.|O\.C\.|VOICE OVER|PRE-LAP|FILTERED)\)\s*$",
    re.IGNORECASE,
)
_LEADING_SCENE_NUMBER = re.compile(r"^(\d{1,4}[A-Z]?)\s{2,}")
_TRAILING_SCENE_NUMBER = re.compile(r"\s{2,}(\d{1,4}[A-Z]?)$")
_MAX_CHARACTER_CUE_LENGTH = 45

_SINGLE_LINE_TYPES = frozenset(
    {
        ElementType.SCENE_HEADING,
        ElementType.TRANSITION,
        ElementType.PARENTHETICAL,
        ElementType.CHARACTER,
    }
)


class PdfParseError(ValueError):
    """A PDF that cannot yield a screenplay.

    ValueError is what the import application layer translates into a client
    validation failure, so this stays a ValueError subclass while still being
    distinguishable in tests.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Line:
    """One visual line of extracted text with its indentation column."""

    page_number: int
    indent: int
    text: str


@dataclass
class _Block:
    """Consecutive lines that belong to a single screenplay element."""

    element_type: ElementType
    page_number: int
    parts: list[str]


class PdfParser(ScriptParserPort):
    def parse(self, data: bytes, filename: str) -> ParseResult:
        reader = _open_document(data)
        lines, unextractable_pages, total_pages = _extract_lines(reader)
        if not lines:
            raise PdfParseError(
                "This PDF contains no extractable text. Every page appears to be a "
                "scanned image. Export a text-based PDF, or import the Fountain or "
                "Final Draft source instead.",
                code="PDF_NO_EXTRACTABLE_TEXT",
            )

        body, printed_page_numbers, stripped_scene_numbers = _strip_running_furniture(lines)
        dialogue_floor = _dialogue_indent_floor(body)
        elements = _build_elements(body, dialogue_floor)

        warnings = _collect_warnings(
            total_pages=total_pages,
            unextractable_pages=unextractable_pages,
            printed_page_numbers=printed_page_numbers,
            stripped_scene_numbers=stripped_scene_numbers,
            dialogue_floor=dialogue_floor,
            body=body,
            elements=elements,
        )

        return ParseResult(
            title=_resolve_title(reader, filename),
            elements=elements,
            warnings=warnings,
            parser_name="PdfParser",
        )


def _open_document(data: bytes):
    """Open the document, refusing anything that blocks text extraction."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except PdfReadError as error:
        raise PdfParseError(
            f"The PDF structure could not be read: {error}. Re-export the file from "
            "the application that produced it.",
            code="PDF_MALFORMED",
        ) from error

    if reader.is_encrypted:
        # Screenplays circulated with an owner password but no user password
        # decrypt with an empty string. Anything stronger needs the password,
        # which this import path has no way to collect.
        try:
            opened = reader.decrypt("")
        except Exception as error:  # pypdf raises several unrelated types here
            raise PdfParseError(
                "This PDF is encrypted with a password this import cannot supply. "
                "Export an unprotected copy.",
                code="PDF_ENCRYPTED_NO_PASSWORD",
            ) from error
        if not opened:
            raise PdfParseError(
                "This PDF is encrypted. The file carries a password that blocks text "
                "extraction. Export an unprotected copy.",
                code="PDF_ENCRYPTED_NO_PASSWORD",
            )

    try:
        page_count = len(reader.pages)
    except Exception as error:
        raise PdfParseError(
            "The PDF page tree could not be read. Re-export the file from the "
            "application that produced it.",
            code="PDF_MALFORMED",
        ) from error

    if page_count == 0:
        raise PdfParseError("This PDF has no pages.", code="PDF_EMPTY")
    if page_count > MAX_PDF_PAGES:
        raise PdfParseError(
            f"This PDF has {page_count} pages, beyond the {MAX_PDF_PAGES}-page import "
            "limit. Split the document or import the screenplay source.",
            code="PDF_TOO_MANY_PAGES",
        )
    return reader


def _extract_lines(reader) -> tuple[list[_Line], tuple[int, ...], int]:
    """Extract lines with indentation, recording pages that yielded no text."""
    lines: list[_Line] = []
    unextractable: list[int] = []
    pages = reader.pages
    for index, page in enumerate(pages, start=1):
        try:
            raw = page.extract_text(extraction_mode="layout")
        except Exception:
            # A page whose fonts or content stream defeat extraction is reported,
            # never silently treated as blank.
            unextractable.append(index)
            continue
        page_lines = [
            _Line(page_number=index, indent=len(line) - len(line.lstrip()), text=line.strip())
            for line in raw.splitlines()
            if line.strip()
        ]
        if not page_lines:
            unextractable.append(index)
            continue
        lines.extend(page_lines)
    return lines, tuple(unextractable), len(pages)


def _strip_running_furniture(
    lines: list[_Line],
) -> tuple[list[_Line], tuple[tuple[int, int], ...], int]:
    """Remove page numbers and continuation markers from the element stream.

    Returns the surviving lines, the printed page numbers observed paired with
    the physical page they appeared on, and how many scene numbers were stripped
    off the edges of scene headings.
    """
    body: list[_Line] = []
    printed: list[tuple[int, int]] = []
    stripped_scene_numbers = 0

    for line in lines:
        text = line.text
        upper = text.upper()
        if upper in _RUNNING_FURNITURE:
            continue
        page_match = _PRINTED_PAGE_NUMBER.match(text)
        if page_match is not None:
            printed.append((line.page_number, int(page_match.group(1))))
            continue
        cleaned, removed = _strip_edge_scene_numbers(text)
        if removed:
            stripped_scene_numbers += 1
        body.append(_Line(page_number=line.page_number, indent=line.indent, text=cleaned))

    return body, tuple(printed), stripped_scene_numbers


def _strip_edge_scene_numbers(text: str) -> tuple[str, bool]:
    """Drop the marginal scene numbers production drafts print beside headings.

    Only applied to lines that read as scene headings, so a numbered list inside
    action survives intact.
    """
    candidate = _LEADING_SCENE_NUMBER.sub("", text)
    candidate = _TRAILING_SCENE_NUMBER.sub("", candidate)
    if candidate == text:
        return text, False
    if not _SCENE_HEADING.match(candidate.strip()):
        return text, False
    return candidate.strip(), True


_MIN_DIALOGUE_INDENT_GAP = 4
"""Smallest gap from the margin that can mark a genuine dialogue column.

Screenplay dialogue is indented about an inch, roughly ten columns at 12pt
Courier. Requiring a real gap is what separates a dialogue block from extraction
jitter, and it is a better guard than demanding the column recur, which would
flatten a short excerpt that only carries a few dialogue lines.
"""


def _dialogue_indent_floor(lines: list[_Line]) -> int | None:
    """Find the column at or beyond which a line belongs to a dialogue block.

    The left margin is the smallest indent that recurs often enough to be
    structural rather than noise; action and scene headings guarantee it is well
    populated. The dialogue column is the leftmost indent sitting a real distance
    to its right, and the floor sits halfway between them so small extraction
    jitter cannot promote an action line into dialogue.

    Returns None when the document has no indented block at all, in which case
    nothing is dialogue.
    """
    if not lines:
        return None
    counts = Counter(line.indent for line in lines)
    threshold = max(2, len(lines) // 100)
    frequent = sorted(indent for indent, count in counts.items() if count >= threshold)
    margin = frequent[0] if frequent else min(counts)
    indented = sorted(indent for indent in counts if indent >= margin + _MIN_DIALOGUE_INDENT_GAP)
    if not indented:
        return None
    return margin + max(2, (indented[0] - margin) // 2)


def _classify(line: _Line, dialogue_floor: int | None) -> ElementType:
    """Assign an element type from unambiguous text signals, then geometry."""
    text = line.text
    upper = text.upper()
    is_upper = text == upper and any(character.isalpha() for character in text)

    if _SCENE_HEADING.match(text):
        return ElementType.SCENE_HEADING
    if is_upper and (upper in _KNOWN_TRANSITIONS or _TRANSITION_TAIL.search(upper)):
        return ElementType.TRANSITION
    if text.startswith("(") and text.endswith(")"):
        return ElementType.PARENTHETICAL

    in_dialogue_block = dialogue_floor is not None and line.indent >= dialogue_floor
    if not in_dialogue_block:
        return ElementType.ACTION

    cue = _CHARACTER_EXTENSION.sub("", text).strip()
    if cue and cue == cue.upper() and len(cue) <= _MAX_CHARACTER_CUE_LENGTH:
        return ElementType.CHARACTER
    return ElementType.DIALOGUE


def _build_elements(lines: list[_Line], dialogue_floor: int | None) -> list[ScriptElement]:
    """Join wrapped lines into elements and number scenes.

    Visual line breaks are a property of the page, not the screenplay. Joining
    them matters for more than tidiness: passages are the unit a selective rescan
    diffs, so a rewrap caused by a font change must not read as a content change.
    """
    elements: list[ScriptElement] = []
    scene_count = 0
    ordinal = 1
    block: _Block | None = None
    previous_page = lines[0].page_number if lines else 1

    def flush(current: _Block | None) -> None:
        nonlocal ordinal
        if current is None:
            return
        text = " ".join(current.parts).strip()
        if not text:
            return
        elements.append(
            ScriptElement.create(
                ordinal=ordinal,
                element_type=current.element_type,
                text=text,
                scene_number=scene_count or None,
                page_number=current.page_number,
            )
        )
        ordinal += 1

    for line in lines:
        element_type = _classify(line, dialogue_floor)
        # A page boundary always ends a block. Two unrelated paragraphs that
        # happen to share a type and sit either side of a break are separate
        # passages, and their page numbers differ.
        page_changed = line.page_number != previous_page
        starts_new = (
            block is None
            or block.element_type != element_type
            or element_type in _SINGLE_LINE_TYPES
            or page_changed
        )
        if starts_new:
            flush(block)
            if element_type == ElementType.SCENE_HEADING:
                scene_count += 1
            block = _Block(
                element_type=element_type,
                page_number=line.page_number,
                parts=[line.text],
            )
        else:
            assert block is not None
            block.parts.append(line.text)
        previous_page = line.page_number

    flush(block)
    return elements


def _collect_warnings(
    *,
    total_pages: int,
    unextractable_pages: tuple[int, ...],
    printed_page_numbers: tuple[tuple[int, int], ...],
    stripped_scene_numbers: int,
    dialogue_floor: int | None,
    body: list[_Line],
    elements: list[ScriptElement],
) -> list[ParseWarning]:
    """Report every inference a reviewer should be able to audit."""
    warnings: list[ParseWarning] = []

    if unextractable_pages:
        warnings.append(
            ParseWarning(
                warning_code="pdf_pages_without_text",
                message=(
                    f"{len(unextractable_pages)} of {total_pages} pages carry no "
                    f"extractable text and contributed nothing: "
                    f"{_page_list(unextractable_pages)}. They are most likely scanned "
                    "images. Their content is absent from this parse, not inferred."
                ),
            )
        )

    if dialogue_floor is None:
        warnings.append(
            ParseWarning(
                warning_code="pdf_no_dialogue_geometry",
                message=(
                    "No indented dialogue block was found, so every line was read as "
                    "action. Check that this PDF is a formatted screenplay."
                ),
            )
        )

    renumbered = [
        (physical, printed) for physical, printed in printed_page_numbers if physical != printed
    ]
    if renumbered:
        first_physical, first_printed = renumbered[0]
        warnings.append(
            ParseWarning(
                warning_code="pdf_page_numbering_normalised",
                message=(
                    f"Printed page numbers do not match document order in "
                    f"{len(renumbered)} places, starting at document page "
                    f"{first_physical} which prints as {first_printed}. Element page "
                    "numbers follow document order."
                ),
            )
        )

    if stripped_scene_numbers:
        warnings.append(
            ParseWarning(
                warning_code="pdf_scene_numbers_stripped",
                message=(
                    f"Removed production scene numbers printed beside "
                    f"{stripped_scene_numbers} scene headings so the heading text "
                    "matches the screenplay."
                ),
            )
        )

    dialogue_count = sum(1 for element in elements if element.element_type == ElementType.DIALOGUE)
    character_count = sum(
        1 for element in elements if element.element_type == ElementType.CHARACTER
    )
    if character_count and not dialogue_count:
        warnings.append(
            ParseWarning(
                warning_code="pdf_characters_without_dialogue",
                message=(
                    f"{character_count} character cues were found but no dialogue "
                    "followed any of them. Element classification for this file is "
                    "low confidence."
                ),
            )
        )

    if body and len(elements) * 4 < len(body):
        warnings.append(
            ParseWarning(
                warning_code="pdf_heavy_line_joining",
                message=(
                    f"{len(body)} extracted lines collapsed into {len(elements)} "
                    "elements. Verify that paragraph boundaries survived extraction."
                ),
            )
        )

    return warnings


def _page_list(pages: tuple[int, ...], limit: int = 12) -> str:
    """Render page numbers as compact ranges, truncated for very long lists."""
    if not pages:
        return ""
    ranges: list[tuple[int, int]] = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        ranges.append((start, previous))
        start = previous = page
    ranges.append((start, previous))

    rendered = [str(low) if low == high else f"{low}\u2013{high}" for low, high in ranges]
    if len(rendered) > limit:
        return ", ".join(rendered[:limit]) + f", and {len(rendered) - limit} more"
    return ", ".join(rendered)


def _resolve_title(reader, filename: str) -> str:
    """Prefer the document's own title, falling back to the filename."""
    try:
        metadata = reader.metadata
    except Exception:
        metadata = None
    if metadata is not None:
        raw = metadata.title
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip().title()
