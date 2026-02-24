from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_LEFT = 50
MARGIN_TOP = 52
MARGIN_BOTTOM = 52
FONT_SIZE = 10
LEADING = 14
TEXT_WIDTH_CHARS = 95


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_paragraph(text: str, width: int) -> list[str]:
    if not text.strip():
        return [""]
    return textwrap.wrap(
        text.strip(),
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]


def markdown_to_lines(markdown_text: str) -> list[str]:
    lines: list[str] = []
    numbered_re = re.compile(r"^(\d+)\.\s+(.*)$")

    for raw in markdown_text.splitlines():
        row = raw.rstrip()
        stripped = row.strip()

        if not stripped:
            lines.append("")
            continue

        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            lines.append(title.upper())
            lines.append("")
            continue

        if stripped.startswith("- "):
            body = stripped[2:].strip()
            wrapped = _wrap_paragraph(body, TEXT_WIDTH_CHARS - 2)
            if wrapped:
                lines.append(f"- {wrapped[0]}")
                for cont in wrapped[1:]:
                    lines.append(f"  {cont}")
            else:
                lines.append("-")
            continue

        numbered_match = numbered_re.match(stripped)
        if numbered_match:
            num = numbered_match.group(1)
            body = numbered_match.group(2)
            wrapped = _wrap_paragraph(body, TEXT_WIDTH_CHARS - (len(num) + 2))
            if wrapped:
                lines.append(f"{num}. {wrapped[0]}")
                indent = " " * (len(num) + 2)
                for cont in wrapped[1:]:
                    lines.append(f"{indent}{cont}")
            else:
                lines.append(f"{num}.")
            continue

        lines.extend(_wrap_paragraph(stripped, TEXT_WIDTH_CHARS))

    # Trim trailing blank lines.
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def paginate(lines: list[str]) -> list[list[str]]:
    usable_height = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    lines_per_page = max(1, int(usable_height // LEADING))
    return [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]


def make_content_stream(page_lines: list[str]) -> bytes:
    start_x = MARGIN_LEFT
    start_y = PAGE_HEIGHT - MARGIN_TOP
    ops = [
        "BT",
        f"/F1 {FONT_SIZE} Tf",
        f"{LEADING} TL",
        f"{start_x} {start_y} Td",
    ]

    first = True
    for row in page_lines:
        text = _escape_pdf_text(row)
        if first:
            ops.append(f"({text}) Tj")
            first = False
        else:
            ops.append(f"T* ({text}) Tj")
    if first:
        # Empty page fallback.
        ops.append("() Tj")
    ops.append("ET")

    stream = "\n".join(ops).encode("latin-1", "replace")
    header = f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
    return header + stream + b"\nendstream\n"


def build_pdf_bytes(pages: list[list[str]]) -> bytes:
    page_count = len(pages)
    font_obj_id = 3
    first_page_obj_id = 4

    objects: list[bytes] = []

    # 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>\n")

    # 2: Pages
    kids = []
    for i in range(page_count):
        page_id = first_page_obj_id + i * 2
        kids.append(f"{page_id} 0 R")
    pages_obj = f"<< /Type /Pages /Count {page_count} /Kids [{' '.join(kids)}] >>\n".encode("ascii")
    objects.append(pages_obj)

    # 3: Font
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n")

    for i, page_lines in enumerate(pages):
        page_id = first_page_obj_id + i * 2
        content_id = page_id + 1
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> /Contents {content_id} 0 R >>\n"
        ).encode("ascii")
        objects.append(page_obj)
        objects.append(make_content_stream(page_lines))

    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj)
        if not obj.endswith(b"\n"):
            out.extend(b"\n")
        out.extend(b"endobj\n")

    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a simple text PDF from markdown.")
    parser.add_argument("--input", required=True, help="Input markdown path")
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input markdown not found: {input_path}")

    markdown_text = input_path.read_text(encoding="utf-8")
    lines = markdown_to_lines(markdown_text)
    pages = paginate(lines)
    pdf_bytes = build_pdf_bytes(pages)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    print(f"Saved PDF: {output_path}")


if __name__ == "__main__":
    main()
