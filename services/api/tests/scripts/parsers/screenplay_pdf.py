"""Build minimal Courier PDFs that carry real screenplay geometry.

The parser recovers element type from horizontal position, so a fixture has to
place text at genuine coordinates rather than describe it. These helpers emit an
uncompressed single-font PDF, which keeps the fixture readable and keeps the
tests free of any screenwriting application.

Geometry follows standard US screenplay format at 12pt Courier: a 1.5 inch left
margin, dialogue at 2.5 inches, parentheticals at 3.0, character cues at 3.7,
and transitions near the right margin.
"""

import io

POINTS_PER_INCH = 72.0
LINE_HEIGHT = 12.0
FIRST_BASELINE = 700.0

MARGIN = 1.5 * POINTS_PER_INCH
DIALOGUE = 2.5 * POINTS_PER_INCH
PARENTHETICAL = 3.0 * POINTS_PER_INCH
CHARACTER = 3.7 * POINTS_PER_INCH
TRANSITION = 6.0 * POINTS_PER_INCH


class PageBuilder:
    """Accumulate positioned text lines down a page."""

    def __init__(self) -> None:
        self.lines: list[tuple[float, float, str]] = []
        self._baseline = FIRST_BASELINE

    def put(self, x: float, text: str) -> "PageBuilder":
        self.lines.append((x, self._baseline, text))
        self._baseline -= LINE_HEIGHT
        return self

    def blank(self) -> "PageBuilder":
        self._baseline -= LINE_HEIGHT
        return self

    def footer(self, x: float, text: str) -> "PageBuilder":
        """Place text near the bottom edge, where page numbers live."""
        self.lines.append((x, 60.0, text))
        return self


def build_pdf(
    pages: list[list[tuple[float, float, str]]],
    *,
    title: str | None = None,
    encrypt_marker: bool = False,
) -> bytes:
    """Serialise positioned pages into an uncompressed PDF."""
    page_count = len(pages)
    catalog_id = 1
    pages_id = 2
    page_ids = [3 + 2 * index for index in range(page_count)]
    content_ids = [4 + 2 * index for index in range(page_count)]
    font_id = 3 + 2 * page_count
    info_id = font_id + 1
    encrypt_id = font_id + 2

    objects: dict[int, bytes] = {}
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id] = f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode()

    for index, lines in enumerate(pages):
        objects[page_ids[index]] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_ids[index]} 0 R >>"
        ).encode()
        chunks = [
            f"BT /F1 12 Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_escape(text)}) Tj ET"
            for x, y, text in lines
        ]
        stream = "\n".join(chunks).encode("latin-1")
        objects[content_ids[index]] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"
    if title is not None:
        objects[info_id] = f"<< /Title ({_escape(title)}) >>".encode()
    if encrypt_marker:
        # A standard security handler entry with a revision no reader can open
        # with an empty password, which is what an owner-locked script looks like.
        objects[encrypt_id] = (
            b"<< /Filter /Standard /V 1 /R 2 /O <"
            + b"00" * 32
            + b"> /U <"
            + b"11" * 32
            + b"> /P -44 >>"
        )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for object_id in sorted(objects):
        offsets[object_id] = out.tell()
        out.write(f"{object_id} 0 obj\n".encode())
        out.write(objects[object_id])
        out.write(b"\nendobj\n")

    xref_offset = out.tell()
    highest_id = max(objects)
    out.write(f"xref\n0 {highest_id + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for object_id in range(1, highest_id + 1):
        if object_id in offsets:
            out.write(f"{offsets[object_id]:010d} 00000 n \n".encode())
        else:
            out.write(b"0000000000 65535 f \n")

    trailer = f"trailer\n<< /Size {highest_id + 1} /Root {catalog_id} 0 R"
    if title is not None:
        trailer += f" /Info {info_id} 0 R"
    if encrypt_marker:
        trailer += f" /Encrypt {encrypt_id} 0 R /ID [<{'00' * 16}> <{'00' * 16}>]"
    trailer += " >>\n"
    out.write(trailer.encode())
    out.write(f"startxref\n{xref_offset}\n%%EOF\n".encode())
    return out.getvalue()


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def sample_screenplay_pdf(*, title: str | None = "Borrowed Light") -> bytes:
    """A two-page excerpt exercising every element type and a wrapped paragraph."""
    first = PageBuilder()
    first.put(MARGIN, "INT. WAREHOUSE - NIGHT")
    first.blank()
    first.put(MARGIN, "Rain hammers the skylight. MARA crouches over a")
    first.put(MARGIN, "battered Vega Camera, thumbing the shutter dial.")
    first.blank()
    first.put(CHARACTER, "MARA")
    first.put(PARENTHETICAL, "(quietly)")
    first.put(DIALOGUE, "This thing still runs. Forty years")
    first.put(DIALOGUE, "and it still runs.")
    first.blank()
    first.put(MARGIN, "She lifts it to the light.")
    first.blank()
    first.put(TRANSITION, "CUT TO:")
    first.footer(4.0 * POINTS_PER_INCH, "1.")

    second = PageBuilder()
    second.put(MARGIN, "EXT. ROOFTOP - CONTINUOUS")
    second.blank()
    second.put(MARGIN, "The city glitters below.")
    second.blank()
    second.put(CHARACTER, "MARA (CONT'D)")
    second.put(DIALOGUE, "Every frame of it.")
    second.blank()
    second.put(TRANSITION, "FADE OUT.")
    second.footer(4.0 * POINTS_PER_INCH, "2.")

    return build_pdf([first.lines, second.lines], title=title)
