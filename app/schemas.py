"""Pydantic schemas for request and response validation."""

import datetime
import re
import uuid
from typing import Any
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)
from app.config import settings
from app.models import CertificateStatus, JobStatus


class CertificateInfoIn(BaseModel):
    """Metadata shared across all certificates in a job."""

    title: str = Field(..., min_length=1, max_length=255, description="Certificate title")
    event_name: str = Field(..., min_length=1, max_length=255, description="Course or event name")
    issue_date: datetime.date = Field(..., description="Issue date in YYYY-MM-DD format")
    issued_by: str = Field(..., min_length=1, max_length=255, description="Issuer organization or person")

    @field_validator("title", "event_name", "issued_by")
    @classmethod
    def validate_non_blank_string(cls, v: str) -> str:
        """Ensure string is non-blank after stripping whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class RecipientIn(BaseModel):
    """Schema for individual recipient input validation."""

    name: str = Field(..., min_length=1, max_length=100, description="Recipient full name")
    email: EmailStr = Field(..., description="Recipient email address")

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        """Strip and collapse internal whitespace in recipient name."""
        cleaned = re.sub(r"\s+", " ", v.strip())
        if not cleaned:
            raise ValueError("must not be blank")
        if len(cleaned) > 100:
            raise ValueError("must not exceed 100 characters")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Convert email address to lower-case."""
        return v.strip().lower()


class JobCreateRequest(BaseModel):
    """Request payload for submitting a bulk certificate generation job."""

    certificate: CertificateInfoIn
    recipients: list[Any] = Field(..., description="List of recipient objects")

    @field_validator("recipients")
    @classmethod
    def validate_recipients_list(cls, v: list[Any]) -> list[Any]:
        """Validate recipient list presence, size bounds, and non-emptiness."""
        if not isinstance(v, list):
            raise ValueError("recipients must be a list")
        if len(v) == 0:
            raise ValueError("recipients list must not be empty")
        if len(v) > settings.max_recipients:
            raise ValueError(f"recipients list exceeds maximum allowed ({settings.max_recipients})")
        return v


class InvalidRowDetail(BaseModel):
    """Details of a rejected recipient row."""

    row_index: int
    error: str


class JobCreateResponse(BaseModel):
    """202 Accepted response payload returned when a job is created."""

    job_id: uuid.UUID
    status: JobStatus
    total_recipients: int
    accepted: int
    invalid: int
    invalid_rows: list[InvalidRowDetail]
    status_url: str


class CertificateItemResponse(BaseModel):
    """Details of an individual certificate in a job."""

    id: uuid.UUID
    row_index: int
    recipient_name: str | None
    recipient_email: str | None
    status: CertificateStatus
    error_message: str | None
    download_url: str | None = None
    created_at: datetime.datetime
    generated_at: datetime.datetime | None

    model_config = ConfigDict(from_attributes=True)


class PaginatedCertificatesResponse(BaseModel):
    """Paginated list of certificates."""

    total: int
    limit: int
    offset: int
    items: list[CertificateItemResponse]


class JobCounts(BaseModel):
    """Aggregation counts for a job."""

    total: int
    invalid: int
    pending: int
    generated: int
    failed: int


class JobLinks(BaseModel):
    """Resource links for a job."""

    status: str
    certificates: str
    failed: str
    download_all: str


class JobStatusResponse(BaseModel):
    """Response payload for job progress and status polling."""

    job_id: uuid.UUID
    status: JobStatus
    counts: JobCounts
    progress_percent: float
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    links: JobLinks


class CertificateVerificationResponse(BaseModel):
    """Public verification details for a certificate."""

    certificate_id: uuid.UUID
    is_valid: bool
    status: CertificateStatus
    recipient_name: str | None
    title: str | None
    event_name: str | None
    issued_by: str | None
    issue_date: datetime.date | None
