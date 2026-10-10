"""ReportLab certificate template generation service."""

import os
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------------------
# Template Constants (Easily modifiable during technical interviews)
# ---------------------------------------------------------------------------
PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)  # 841.89 x 595.27 points

PRIMARY_COLOR = colors.HexColor("#1E3A8A")     # Deep Classic Navy
ACCENT_COLOR = colors.HexColor("#D97706")      # Warm Amber Gold
TEXT_MAIN = colors.HexColor("#1F2937")         # Dark Charcoal
TEXT_MUTED = colors.HexColor("#4B5563")        # Slate Gray
BORDER_OUTER = colors.HexColor("#1E3A8A")      # Navy
BORDER_INNER = colors.HexColor("#D97706")      # Gold

FONT_TITLE = "Helvetica-Bold"
FONT_SUBTITLE = "Helvetica"
FONT_NAME = "Helvetica-Bold"
FONT_BODY = "Helvetica"
FONT_FOOTER = "Helvetica"

MAX_NAME_FONT_SIZE = 34
MIN_NAME_FONT_SIZE = 16


def _draw_borders_and_decorations(c: canvas.Canvas) -> None:
    """Draw professional double border and corner accents."""
    c.saveState()

    # Outer border (thick navy)
    c.setStrokeColor(BORDER_OUTER)
    c.setLineWidth(3.0)
    c.rect(28, 28, PAGE_WIDTH - 56, PAGE_HEIGHT - 56)

    # Inner border (thin gold)
    c.setStrokeColor(BORDER_INNER)
    c.setLineWidth(1.0)
    c.rect(34, 34, PAGE_WIDTH - 68, PAGE_HEIGHT - 68)

    # Corner diamond decorations (gold)
    c.setFillColor(BORDER_INNER)
    corner_size = 6
    corners = [
        (34, 34),
        (PAGE_WIDTH - 34, 34),
        (34, PAGE_HEIGHT - 34),
        (PAGE_WIDTH - 34, PAGE_HEIGHT - 34),
    ]
    for x, y in corners:
        p = c.beginPath()
        p.moveTo(x, y - corner_size)
        p.lineTo(x + corner_size, y)
        p.lineTo(x, y + corner_size)
        p.lineTo(x - corner_size, y)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    c.restoreState()


def _calculate_name_font_size(name: str, max_width: float) -> int:
    """Measure string width and scale down font size until it fits max_width."""
    font_size = MAX_NAME_FONT_SIZE
    while font_size > MIN_NAME_FONT_SIZE:
        width = pdfmetrics.stringWidth(name, FONT_NAME, font_size)
        if width <= max_width:
            break
        font_size -= 1
    return font_size


def generate_certificate(data: dict[str, Any], output_path: Path | str) -> Path:
    """Generate a high-resolution landscape certificate PDF.

    Args:
        data: Dictionary containing:
            - certificate_id: UUID or string ID
            - recipient_name: Recipient full name
            - title: Certificate title (e.g. 'Certificate of Completion')
            - event_name: Event / course name
            - issue_date: Issue date string (YYYY-MM-DD)
            - issued_by: Issuer name or organization
        output_path: Target destination path for the generated PDF.

    Returns:
        Path to the successfully generated PDF file.
    """
    dest_path = Path(output_path).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".pdf.tmp")

    try:
        c = canvas.Canvas(str(temp_path), pagesize=landscape(A4))

        # 1. Background decorations
        _draw_borders_and_decorations(c)

        # 2. Certificate Title (Header)
        title_text = str(data.get("title", "Certificate of Completion")).upper()
        c.setFillColor(PRIMARY_COLOR)
        c.setFont(FONT_TITLE, 28)
        c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 110, title_text)

        # Decorative divider under title
        c.setStrokeColor(ACCENT_COLOR)
        c.setLineWidth(1.5)
        c.line(PAGE_WIDTH / 2.0 - 90, PAGE_HEIGHT - 122, PAGE_WIDTH / 2.0 + 90, PAGE_HEIGHT - 122)

        # 3. "This is to certify that"
        c.setFillColor(TEXT_MUTED)
        c.setFont(FONT_SUBTITLE, 13)
        c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 165, "THIS IS PROUDLY PRESENTED TO")

        # 4. Recipient Name (Centerpiece with dynamic font scaling)
        recipient_name = str(data.get("recipient_name", "")).strip()
        max_name_width = PAGE_WIDTH - 180  # generous margins
        name_font_size = _calculate_name_font_size(recipient_name, max_name_width)

        c.setFillColor(PRIMARY_COLOR)
        c.setFont(FONT_NAME, name_font_size)
        c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 235, recipient_name)

        # Subtle gold accent line under recipient name
        name_width = min(pdfmetrics.stringWidth(recipient_name, FONT_NAME, name_font_size), max_name_width)
        line_half = max(name_width / 2.0 + 20, 100)
        c.setStrokeColor(ACCENT_COLOR)
        c.setLineWidth(1.0)
        c.line(PAGE_WIDTH / 2.0 - line_half, PAGE_HEIGHT - 250, PAGE_WIDTH / 2.0 + line_half, PAGE_HEIGHT - 250)

        # 5. Course / Event Achievement text
        c.setFillColor(TEXT_MUTED)
        c.setFont(FONT_BODY, 13)
        c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 295, "for successfully completing the course")

        event_name = str(data.get("event_name", ""))
        c.setFillColor(TEXT_MAIN)
        c.setFont(FONT_TITLE, 18)
        c.drawCentredString(PAGE_WIDTH / 2.0, PAGE_HEIGHT - 330, event_name)

        # 6. Bottom Signatures & Date
        issue_date_str = str(data.get("issue_date", ""))
        issued_by_str = str(data.get("issued_by", ""))

        left_x = 130
        right_x = PAGE_WIDTH - 270
        sig_y = 120

        # Left Column: Date
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(1.0)
        c.line(left_x, sig_y + 20, left_x + 140, sig_y + 20)

        c.setFillColor(TEXT_MAIN)
        c.setFont(FONT_BODY, 11)
        c.drawCentredString(left_x + 70, sig_y + 28, issue_date_str)

        c.setFillColor(TEXT_MUTED)
        c.setFont(FONT_BODY, 9)
        c.drawCentredString(left_x + 70, sig_y + 6, "DATE OF ISSUANCE")

        # Right Column: Issued By
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(1.0)
        c.line(right_x, sig_y + 20, right_x + 140, sig_y + 20)

        c.setFillColor(TEXT_MAIN)
        c.setFont(FONT_BODY, 11)
        c.drawCentredString(right_x + 70, sig_y + 28, issued_by_str)

        c.setFillColor(TEXT_MUTED)
        c.setFont(FONT_BODY, 9)
        c.drawCentredString(right_x + 70, sig_y + 6, "AUTHORIZED SIGNATURE")

        # 7. Verification Footer with Certificate ID
        cert_id = str(data.get("certificate_id", ""))
        c.setFillColor(TEXT_MUTED)
        c.setFont(FONT_FOOTER, 8)
        c.drawCentredString(
            PAGE_WIDTH / 2.0,
            46,
            f"Certificate ID: {cert_id}  •  Verify authenticity at organization portal",
        )

        # Complete and write the PDF
        c.showPage()
        c.save()

        # Atomic replacement: rename temp file to target destination
        os.replace(temp_path, dest_path)
        return dest_path

    finally:
        # Guarantee cleanup of temporary file if an exception occurred before rename
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
