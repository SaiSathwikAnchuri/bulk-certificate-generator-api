"""Tests for certificate retrieval (single PDF download, ZIP, verification)."""

import io
import uuid
import zipfile
from unittest.mock import patch

from app.models import CertificateStatus, JobStatus


VALID_CERT = {
    "title": "Certificate of Completion",
    "event_name": "Data Science Bootcamp 2026",
    "issue_date": "2026-10-10",
    "issued_by": "Analytics Academy",
}


def _create_completed_job(client, recipients=None):
    """Submit a job and let TestClient run the background task."""
    if recipients is None:
        recipients = [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
        ]
    payload = {"certificate": VALID_CERT, "recipients": recipients}
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    return response.json()


class TestSingleCertificateDownload:
    """Tests for GET /api/v1/jobs/{job_id}/certificates/{cert_id}/download."""

    def test_download_generated_certificate(self, client):
        """Downloading a generated certificate returns a valid PDF."""
        data = _create_completed_job(client)
        job_id = data["job_id"]

        certs = client.get(f"/api/v1/jobs/{job_id}/certificates?status=generated").json()
        cert = certs["items"][0]

        response = client.get(cert["download_url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")

    def test_download_failed_certificate_returns_409(self, client):
        """Attempting to download a failed certificate returns 409 Conflict."""
        from app.services.certificate_generator import generate_certificate

        def fail_for_bob(data, output_path):
            if data["recipient_name"] == "Bob Jones":
                raise RuntimeError("render error")
            return generate_certificate(data, output_path)

        with patch("app.services.job_processor.generate_certificate", side_effect=fail_for_bob):
            data = _create_completed_job(client)

        job_id = data["job_id"]
        failed = client.get(f"/api/v1/jobs/{job_id}/certificates?status=failed").json()
        cert_id = failed["items"][0]["id"]

        response = client.get(f"/api/v1/jobs/{job_id}/certificates/{cert_id}/download")
        assert response.status_code == 409

    def test_download_wrong_job_returns_404(self, client):
        """Certificate ID valid but wrong job_id returns 404."""
        data = _create_completed_job(client)
        job_id = data["job_id"]
        certs = client.get(f"/api/v1/jobs/{job_id}/certificates").json()
        cert_id = certs["items"][0]["id"]

        fake_job = uuid.uuid4()
        response = client.get(f"/api/v1/jobs/{fake_job}/certificates/{cert_id}/download")
        assert response.status_code == 404

    def test_download_nonexistent_cert_returns_404(self, client):
        """Nonexistent certificate ID returns 404."""
        data = _create_completed_job(client)
        job_id = data["job_id"]
        fake_cert = uuid.uuid4()
        response = client.get(f"/api/v1/jobs/{job_id}/certificates/{fake_cert}/download")
        assert response.status_code == 404


class TestZipDownload:
    """Tests for GET /api/v1/jobs/{job_id}/download."""

    def test_zip_contains_all_generated(self, client):
        """ZIP archive contains exactly the generated certificates."""
        data = _create_completed_job(client)
        job_id = data["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}/download")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            names = z.namelist()
            assert len(names) == 2
            for name in names:
                assert name.endswith(".pdf")

    def test_zip_while_pending_returns_409(self, client):
        """Requesting ZIP while job is still pending returns 409."""
        with patch("app.routes.jobs.process_job"):
            data = _create_completed_job(client)

        job_id = data["job_id"]
        response = client.get(f"/api/v1/jobs/{job_id}/download")
        assert response.status_code == 409

    def test_zip_nonexistent_job_returns_404(self, client):
        """Requesting ZIP for a nonexistent job returns 404."""
        fake_id = uuid.uuid4()
        response = client.get(f"/api/v1/jobs/{fake_id}/download")
        assert response.status_code == 404


class TestCertificateVerification:
    """Tests for GET /api/v1/certificates/{cert_id}/verify."""

    def test_verify_valid_certificate(self, client):
        """Verifying a generated certificate returns is_valid=True."""
        data = _create_completed_job(client)
        job_id = data["job_id"]
        certs = client.get(f"/api/v1/jobs/{job_id}/certificates?status=generated").json()
        cert_id = certs["items"][0]["id"]

        response = client.get(f"/api/v1/certificates/{cert_id}/verify")
        assert response.status_code == 200
        body = response.json()
        assert body["is_valid"] is True
        assert body["recipient_name"] == certs["items"][0]["recipient_name"]

    def test_verify_nonexistent_certificate_returns_404(self, client):
        """Verifying a nonexistent certificate returns 404."""
        fake_id = uuid.uuid4()
        response = client.get(f"/api/v1/certificates/{fake_id}/verify")
        assert response.status_code == 404
