"""Tests for creating certificate generation jobs."""

import uuid
from app.models import Certificate, Job, JobStatus


def test_create_job_success(client, db):
    """Test successful submission of a bulk job returns 202 and creates DB records."""
    payload = {
        "certificate": {
            "title": "Certificate of Excellence",
            "event_name": "AI Systems Workshop 2026",
            "issue_date": "2026-10-10",
            "issued_by": "DeepMind Academy",
        },
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
        ],
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    # Validate response schema
    job_id_str = data["job_id"]
    job_uuid = uuid.UUID(job_id_str)
    assert data["total_recipients"] == 2
    assert data["accepted"] == 2
    assert data["invalid"] == 0
    assert data["invalid_rows"] == []
    assert data["status_url"] == f"/api/v1/jobs/{job_id_str}"

    # Verify database persistence
    job = db.get(Job, job_uuid)
    assert job is not None
    assert job.title == "Certificate of Excellence"
    assert job.event_name == "AI Systems Workshop 2026"
    assert job.total_recipients == 2

    certs = db.query(Certificate).filter(Certificate.job_id == job_uuid).all()
    assert len(certs) == 2
