"""Tests for job status polling and progress tracking."""

import uuid
from unittest.mock import patch

from app.models import JobStatus


VALID_CERT = {
    "title": "Certificate of Completion",
    "event_name": "AI Workshop 2026",
    "issue_date": "2026-10-10",
    "issued_by": "Tech Academy",
}


def _create_job(client, recipients=None):
    """Helper to submit a valid job and return the response data."""
    if recipients is None:
        recipients = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]
    payload = {"certificate": VALID_CERT, "recipients": recipients}
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    return response.json()


class TestJobStatusAfterProcessing:
    """Tests for GET /api/v1/jobs/{job_id} after background task completes."""

    def test_completed_job_has_correct_counts(self, client):
        """After processing, counts and progress should reflect completion."""
        data = _create_job(client)
        job_id = data["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        status_data = response.json()

        assert status_data["status"] == JobStatus.COMPLETED.value
        assert status_data["counts"]["total"] == 2
        assert status_data["counts"]["generated"] == 2
        assert status_data["counts"]["pending"] == 0
        assert status_data["counts"]["failed"] == 0
        assert status_data["progress_percent"] == 100.0

    def test_completed_with_errors_when_invalid_rows(self, client):
        """Job with valid + invalid rows results in completed_with_errors."""
        recipients = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "", "email": "bad"},  # invalid
        ]
        data = _create_job(client, recipients)
        job_id = data["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}")
        status_data = response.json()

        assert status_data["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
        assert status_data["counts"]["generated"] == 1
        assert status_data["counts"]["invalid"] == 1

    def test_status_has_resource_links(self, client):
        """Status response includes HATEOAS-style resource links."""
        data = _create_job(client)
        job_id = data["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}")
        links = response.json()["links"]

        assert f"/api/v1/jobs/{job_id}" in links["status"]
        assert "certificates" in links["certificates"]
        assert "status=failed" in links["failed"]
        assert "download" in links["download_all"]


class TestJobStatusBeforeProcessing:
    """Tests for status when background task has NOT run."""

    def test_pending_status_when_unprocessed(self, client):
        """Patching out process_job should leave the job in pending state."""
        with patch("app.routes.jobs.process_job"):
            data = _create_job(client)

        job_id = data["job_id"]
        response = client.get(f"/api/v1/jobs/{job_id}")
        status_data = response.json()

        assert status_data["status"] == JobStatus.PENDING.value
        assert status_data["counts"]["pending"] == 2
        assert status_data["progress_percent"] == 0.0


class TestJobStatusErrors:
    """Tests for error conditions on the status endpoint."""

    def test_unknown_job_returns_404(self, client):
        """Requesting status of a non-existent job returns 404."""
        fake_id = uuid.uuid4()
        response = client.get(f"/api/v1/jobs/{fake_id}")
        assert response.status_code == 404

    def test_certificates_filter_returns_only_matching(self, client):
        """?status=failed filter returns only failed certificates."""
        recipients = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "", "email": "bad"},  # invalid
        ]
        data = _create_job(client, recipients)
        job_id = data["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}/certificates?status=invalid")
        assert response.status_code == 200
        certs = response.json()
        assert certs["total"] == 1
        assert all(c["status"] == "invalid" for c in certs["items"])

    def test_invalid_status_filter_returns_422(self, client):
        """Invalid status filter value returns 422."""
        data = _create_job(client)
        job_id = data["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}/certificates?status=nonexistent")
        assert response.status_code == 422
