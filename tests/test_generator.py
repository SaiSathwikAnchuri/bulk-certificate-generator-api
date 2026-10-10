"""Tests for the ReportLab certificate generator service."""

from pathlib import Path

from pypdf import PdfReader

from app.services.certificate_generator import generate_certificate


SAMPLE_DATA = {
    "certificate_id": "aaaa-bbbb-cccc-dddd",
    "recipient_name": "Asha Rao",
    "title": "Certificate of Completion",
    "event_name": "Python Bootcamp 2026",
    "issue_date": "2026-10-01",
    "issued_by": "VNR Tech Club",
}


def test_pdf_file_created(tmp_path):
    """generate_certificate creates a valid PDF file on disk."""
    out = tmp_path / "cert.pdf"
    result = generate_certificate(SAMPLE_DATA, out)
    assert result.exists()
    assert result.stat().st_size > 0
    # Check PDF magic bytes
    with open(result, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_pdf_contains_recipient_name(tmp_path):
    """The generated PDF contains the recipient's name in extractable text."""
    out = tmp_path / "cert.pdf"
    generate_certificate(SAMPLE_DATA, out)
    reader = PdfReader(str(out))
    text = reader.pages[0].extract_text()
    assert "Asha Rao" in text


def test_pdf_contains_event_name(tmp_path):
    """The generated PDF contains the event name."""
    out = tmp_path / "cert.pdf"
    generate_certificate(SAMPLE_DATA, out)
    reader = PdfReader(str(out))
    text = reader.pages[0].extract_text()
    assert "Python Bootcamp 2026" in text


def test_pdf_contains_certificate_id(tmp_path):
    """The generated PDF contains the certificate ID for verification."""
    out = tmp_path / "cert.pdf"
    generate_certificate(SAMPLE_DATA, out)
    reader = PdfReader(str(out))
    text = reader.pages[0].extract_text()
    assert "aaaa-bbbb-cccc-dddd" in text


def test_long_name_still_generates(tmp_path):
    """A 60+ character name should still produce a valid PDF (font scales down)."""
    long_data = {
        **SAMPLE_DATA,
        "recipient_name": "Dr. Alexander Bartholomew Montgomery-Chamberlain III, Ph.D.",
    }
    out = tmp_path / "cert_long.pdf"
    result = generate_certificate(long_data, out)
    assert result.exists()
    reader = PdfReader(str(result))
    text = reader.pages[0].extract_text()
    assert "Alexander" in text


def test_no_temp_file_left_behind(tmp_path):
    """After successful generation, no .pdf.tmp file should remain."""
    out = tmp_path / "cert.pdf"
    generate_certificate(SAMPLE_DATA, out)
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_parent_dirs_created_automatically(tmp_path):
    """Output path with non-existent parent directories is created automatically."""
    deep_path = tmp_path / "a" / "b" / "c" / "cert.pdf"
    result = generate_certificate(SAMPLE_DATA, deep_path)
    assert result.exists()
