"""Tests for individual certificate failure handling."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.models import JobStatus, CertificateStatus
from app.services.certificate_generator import generate_certificate


VALID_CERT = {
    "title": "Certificate of Completion",
    "event_name": "Cloud Engineering 2026",
    "issue_date": "2026-10-10",
    "issued_by": "Tech Institute",
}


def _failing_generator(data: dict[str, Any], output_path: Path | str) -> Path:
    """Generator that raises RuntimeError for a specific recipient name."""
    if data.get("recipient_name") == "Bad Name":
        raise RuntimeError("font rendering error: unsupported glyph")
    return generate_certificate(data, output_path)


def test_one_failure_does_not_stop_others(client):
    """If one certificate fails, other valid ones should still be generated."""
    recipients = [
        {"name": "Alice Smith", "email": "alice@example.com"},
        {"name": "Bad Name", "email": "bad@example.com"},
        {"name": "Charlie Brown", "email": "charlie@example.com"},
    ]
    payload = {"certificate": VALID_CERT, "recipients": recipients}

    with patch("app.services.job_processor.generate_certificate", side_effect=_failing_generator):
        response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Check job status
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    status_data = status_resp.json()

    assert status_data["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
    assert status_data["counts"]["generated"] == 2
    assert status_data["counts"]["failed"] == 1

    # Verify the failed row has the correct error message
    failed_resp = client.get(f"/api/v1/jobs/{job_id}/certificates?status=failed")
    failed_certs = failed_resp.json()["items"]
    assert len(failed_certs) == 1
    assert failed_certs[0]["recipient_name"] == "Bad Name"
    assert "font rendering error" in failed_certs[0]["error_message"]

    # Verify the successful ones exist
    gen_resp = client.get(f"/api/v1/jobs/{job_id}/certificates?status=generated")
    gen_certs = gen_resp.json()["items"]
    assert len(gen_certs) == 2
    gen_names = {c["recipient_name"] for c in gen_certs}
    assert gen_names == {"Alice Smith", "Charlie Brown"}


def test_all_failures_results_in_failed_job(client):
    """If every certificate fails generation, the job status should be 'failed'."""

    def always_fail(data, output_path):
        raise RuntimeError("catastrophic failure")

    recipients = [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"},
    ]
    payload = {"certificate": VALID_CERT, "recipients": recipients}

    with patch("app.services.job_processor.generate_certificate", side_effect=always_fail):
        response = client.post("/api/v1/jobs", json=payload)

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    status_data = status_resp.json()

    assert status_data["status"] == JobStatus.FAILED.value
    assert status_data["counts"]["generated"] == 0
    assert status_data["counts"]["failed"] == 2


def test_failure_error_message_is_stored(client):
    """The error message from the exception is saved on the certificate row."""

    def specific_fail(data, output_path):
        raise ValueError("missing required field: grade")

    recipients = [{"name": "Alice", "email": "alice@example.com"}]
    payload = {"certificate": VALID_CERT, "recipients": recipients}

    with patch("app.services.job_processor.generate_certificate", side_effect=specific_fail):
        response = client.post("/api/v1/jobs", json=payload)

    job_id = response.json()["job_id"]
    certs = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    assert certs[0]["status"] == CertificateStatus.FAILED.value
    assert "missing required field: grade" in certs[0]["error_message"]
