"""Tests for input validation logic."""

import pytest
from app.config import settings


VALID_CERT = {
    "title": "Certificate of Completion",
    "event_name": "Python Bootcamp 2026",
    "issue_date": "2026-10-01",
    "issued_by": "VNR Tech Club",
}


class TestRequestLevelValidation:
    """Level 1: whole-request validation returning 422."""

    def test_missing_certificate_field(self, client):
        """Missing certificate object returns 422."""
        response = client.post("/api/v1/jobs", json={"recipients": [{"name": "A", "email": "a@b.com"}]})
        assert response.status_code == 422

    def test_missing_recipients_field(self, client):
        """Missing recipients list returns 422."""
        response = client.post("/api/v1/jobs", json={"certificate": VALID_CERT})
        assert response.status_code == 422

    def test_empty_recipients_list(self, client):
        """Empty recipients list returns 422."""
        response = client.post("/api/v1/jobs", json={"certificate": VALID_CERT, "recipients": []})
        assert response.status_code == 422

    def test_over_max_recipients(self, client):
        """Exceeding MAX_RECIPIENTS returns 422."""
        big_list = [{"name": f"Person {i}", "email": f"p{i}@example.com"} for i in range(settings.max_recipients + 1)]
        response = client.post("/api/v1/jobs", json={"certificate": VALID_CERT, "recipients": big_list})
        assert response.status_code == 422

    def test_missing_certificate_title(self, client):
        """Missing certificate title returns 422."""
        cert = {**VALID_CERT, "title": ""}
        response = client.post(
            "/api/v1/jobs",
            json={"certificate": cert, "recipients": [{"name": "A", "email": "a@b.com"}]},
        )
        assert response.status_code == 422

    def test_invalid_issue_date(self, client):
        """Non-date issue_date returns 422."""
        cert = {**VALID_CERT, "issue_date": "not-a-date"}
        response = client.post(
            "/api/v1/jobs",
            json={"certificate": cert, "recipients": [{"name": "A", "email": "a@b.com"}]},
        )
        assert response.status_code == 422

    def test_all_rows_invalid_returns_422(self, client):
        """If every recipient is invalid, return 422 and create no job."""
        payload = {
            "certificate": VALID_CERT,
            "recipients": [
                {"name": "", "email": "not-email"},
                {"name": "", "email": "also-bad"},
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "invalid_rows" in detail
        assert len(detail["invalid_rows"]) == 2


class TestRecipientLevelValidation:
    """Level 2: per-row validation; bad rows marked invalid, good rows accepted."""

    def test_blank_name_marked_invalid(self, client):
        """Blank name row is accepted but marked invalid."""
        payload = {
            "certificate": VALID_CERT,
            "recipients": [
                {"name": "Good Person", "email": "good@example.com"},
                {"name": "", "email": "blank@example.com"},
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["invalid"] == 1
        assert data["invalid_rows"][0]["row_index"] == 1
        assert "name" in data["invalid_rows"][0]["error"]

    def test_bad_email_marked_invalid(self, client):
        """Bad email row is accepted but marked invalid."""
        payload = {
            "certificate": VALID_CERT,
            "recipients": [
                {"name": "Good Person", "email": "good@example.com"},
                {"name": "Ravi Kumar", "email": "not-an-email"},
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["invalid"] == 1
        assert "email" in data["invalid_rows"][0]["error"]

    def test_non_object_row_marked_invalid(self, client):
        """A non-dict row (number, null, string) is marked invalid."""
        payload = {
            "certificate": VALID_CERT,
            "recipients": [
                {"name": "Good Person", "email": "good@example.com"},
                42,
                None,
                "just a string",
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["invalid"] == 3

    def test_duplicate_email_marked_invalid(self, client):
        """Second row with same email is marked as duplicate."""
        payload = {
            "certificate": VALID_CERT,
            "recipients": [
                {"name": "Alice", "email": "same@example.com"},
                {"name": "Bob", "email": "same@example.com"},
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["invalid"] == 1
        assert "duplicate" in data["invalid_rows"][0]["error"].lower()

    def test_name_whitespace_collapsed(self, client):
        """Names with excessive whitespace are trimmed and collapsed."""
        payload = {
            "certificate": VALID_CERT,
            "recipients": [
                {"name": "  Asha   Rao  ", "email": "asha@example.com"},
            ],
        }
        response = client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 202
        # Verify via certificates list
        job_id = response.json()["job_id"]
        certs = client.get(f"/api/v1/jobs/{job_id}/certificates").json()
        assert certs["items"][0]["recipient_name"] == "Asha Rao"
