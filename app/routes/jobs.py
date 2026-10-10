"""Job and certificate endpoints."""

import os
import re
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.config import settings
from app.database import get_db
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import (
    CertificateItemResponse,
    CertificateVerificationResponse,
    InvalidRowDetail,
    JobCounts,
    JobCreateRequest,
    JobCreateResponse,
    JobLinks,
    JobStatusResponse,
    PaginatedCertificatesResponse,
)
from app.services.job_processor import process_job
from app.services.validation import validate_recipients

router = APIRouter(tags=["Jobs & Certificates"])


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filenames across all operating systems."""
    return re.sub(r'[\\/*?:"<>| ]+', "_", name).strip("_") or "certificate"


# ---------------------------------------------------------------------------
# 1. Submit Bulk Certificate Generation Job
# ---------------------------------------------------------------------------
@router.post(
    "/api/v1/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
    summary="Submit bulk certificate generation job",
    description="Accepts bulk recipient list, validates rows, saves job, and initiates background generation.",
)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Submit a bulk certificate generation job."""
    # Level 2 validation: validate individual rows
    valid_rows, invalid_rows = validate_recipients(payload.recipients)

    # If all rows are invalid, return 422 Unprocessable Entity
    if len(valid_rows) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "All recipient rows in the request are invalid. No job was created.",
                "invalid_rows": [
                    {"row_index": row.row_index, "error": row.error}
                    for row in invalid_rows
                ],
            },
        )

    # Create Job record
    job = Job(
        title=payload.certificate.title,
        event_name=payload.certificate.event_name,
        issued_by=payload.certificate.issued_by,
        issue_date=payload.certificate.issue_date,
        total_recipients=len(payload.recipients),
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.flush()

    # Create Certificate records in bulk
    certificates_to_add: list[Certificate] = []

    for v_row in valid_rows:
        certificates_to_add.append(
            Certificate(
                job_id=job.id,
                row_index=v_row.row_index,
                recipient_name=v_row.name,
                recipient_email=v_row.email,
                raw_data=v_row.raw_data,
                status=CertificateStatus.PENDING,
            )
        )

    for inv_row in invalid_rows:
        raw_dict = inv_row.raw_data if isinstance(inv_row.raw_data, dict) else {"raw": inv_row.raw_data}
        name_val = inv_row.raw_data.get("name") if isinstance(inv_row.raw_data, dict) else None
        email_val = inv_row.raw_data.get("email") if isinstance(inv_row.raw_data, dict) else None
        certificates_to_add.append(
            Certificate(
                job_id=job.id,
                row_index=inv_row.row_index,
                recipient_name=name_val,
                recipient_email=email_val,
                raw_data=raw_dict,
                status=CertificateStatus.INVALID,
                error_message=inv_row.error,
            )
        )

    db.add_all(certificates_to_add)
    db.commit()

    # Schedule background worker in thread pool
    background_tasks.add_task(process_job, job.id)

    invalid_details = [
        InvalidRowDetail(row_index=inv.row_index, error=inv.error)
        for inv in invalid_rows
    ]

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_recipients=job.total_recipients,
        accepted=len(valid_rows),
        invalid=len(invalid_rows),
        invalid_rows=invalid_details,
        status_url=f"/api/v1/jobs/{job.id}",
    )


# ---------------------------------------------------------------------------
# 2. Get Job Status and Live Progress
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and progress",
    description="Retrieve live progress metrics, status breakdown, and resource links for a job.",
)
def get_job_status(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Retrieve job progress and status."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    # Compute status counts using GROUP BY
    stmt = (
        select(Certificate.status, func.count(Certificate.id))
        .where(Certificate.job_id == job_id)
        .group_by(Certificate.status)
    )
    counts_map = dict(db.execute(stmt).all())

    invalid_cnt = counts_map.get(CertificateStatus.INVALID, 0)
    pending_cnt = counts_map.get(CertificateStatus.PENDING, 0)
    generated_cnt = counts_map.get(CertificateStatus.GENERATED, 0)
    failed_cnt = counts_map.get(CertificateStatus.FAILED, 0)
    total_cnt = job.total_recipients

    valid_attempted = generated_cnt + failed_cnt
    valid_total = total_cnt - invalid_cnt

    if valid_total <= 0:
        progress = 100.0
    else:
        progress = round((valid_attempted / valid_total) * 100.0, 1)

    counts = JobCounts(
        total=total_cnt,
        invalid=invalid_cnt,
        pending=pending_cnt,
        generated=generated_cnt,
        failed=failed_cnt,
    )

    links = JobLinks(
        status=f"/api/v1/jobs/{job.id}",
        certificates=f"/api/v1/jobs/{job.id}/certificates",
        failed=f"/api/v1/jobs/{job.id}/certificates?status=failed",
        download_all=f"/api/v1/jobs/{job.id}/download",
    )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        counts=counts,
        progress_percent=progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        links=links,
    )


# ---------------------------------------------------------------------------
# 3. List Certificates for a Job (with filter & pagination)
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/jobs/{job_id}/certificates",
    response_model=PaginatedCertificatesResponse,
    summary="List certificates for a job",
    description="Retrieve recipient certificates for a job, optionally filtered by status (e.g. failed, invalid).",
)
def list_job_certificates(
    job_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending, generated, failed, invalid"),
    limit: int = Query(50, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
) -> PaginatedCertificatesResponse:
    """List certificates for a job."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    query = select(Certificate).where(Certificate.job_id == job_id)

    if status_filter:
        valid_statuses = [s.value for s in CertificateStatus]
        if status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status filter '{status_filter}'. Allowed values: {valid_statuses}",
            )
        query = query.where(Certificate.status == CertificateStatus(status_filter))

    # Total matching count
    count_query = select(func.count()).select_from(query.subquery())
    total_matching = db.scalar(count_query) or 0

    # Paginated results ordered by original row index
    certs = db.scalars(
        query.order_by(Certificate.row_index).offset(offset).limit(limit)
    ).all()

    items = []
    for cert in certs:
        download_url = None
        if cert.status == CertificateStatus.GENERATED:
            download_url = f"/api/v1/jobs/{job_id}/certificates/{cert.id}/download"

        items.append(
            CertificateItemResponse(
                id=cert.id,
                row_index=cert.row_index,
                recipient_name=cert.recipient_name,
                recipient_email=cert.recipient_email,
                status=cert.status,
                error_message=cert.error_message,
                download_url=download_url,
                created_at=cert.created_at,
                generated_at=cert.generated_at,
            )
        )

    return PaginatedCertificatesResponse(
        total=total_matching,
        limit=limit,
        offset=offset,
        items=items,
    )


# ---------------------------------------------------------------------------
# 4. Download Single Certificate PDF
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/jobs/{job_id}/certificates/{certificate_id}/download",
    summary="Download single certificate PDF",
    description="Download the generated PDF for an individual certificate.",
)
def download_certificate(
    job_id: uuid.UUID,
    certificate_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Download single certificate PDF."""
    cert = db.get(Certificate, certificate_id)
    if not cert or cert.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found for job '{job_id}'.",
        )

    if cert.status == CertificateStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Certificate is pending generation.",
        )
    elif cert.status in (CertificateStatus.FAILED, CertificateStatus.INVALID):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Certificate generation {cert.status.value}: {cert.error_message or 'validation error'}",
        )

    pdf_path = Path(settings.storage_dir) / str(job_id) / f"{certificate_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing on storage.",
        )

    safe_name = sanitize_filename(cert.recipient_name or "recipient")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{safe_name}_certificate.pdf",
    )


# ---------------------------------------------------------------------------
# 5. Bulk Download All Generated Certificates as ZIP
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/jobs/{job_id}/download",
    summary="Download all generated certificates as ZIP",
    description="Package and download all successfully generated certificates for a job in a ZIP archive.",
)
def download_all_certificates(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Download all generated certificates for a job as a single ZIP archive."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is still processing. Bulk ZIP archive is only available once processing finishes.",
        )

    # Fetch all generated certificates
    generated_certs = db.scalars(
        select(Certificate)
        .where(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.GENERATED,
        )
        .order_by(Certificate.row_index)
    ).all()

    if not generated_certs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No generated certificates found for this job to package into a ZIP archive.",
        )

    # Create temporary zip archive
    tmp_zip = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp_zip_path = tmp_zip.name
    tmp_zip.close()

    try:
        with zipfile.ZipFile(tmp_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for cert in generated_certs:
                pdf_path = Path(settings.storage_dir) / str(job_id) / f"{cert.id}.pdf"
                if pdf_path.exists():
                    safe_name = sanitize_filename(cert.recipient_name or "certificate")
                    arcname = f"{cert.row_index + 1:03d}_{safe_name}.pdf"
                    zip_file.write(pdf_path, arcname=arcname)
    except Exception:
        if os.path.exists(tmp_zip_path):
            os.unlink(tmp_zip_path)
        raise

    safe_event = sanitize_filename(job.event_name)
    return FileResponse(
        path=tmp_zip_path,
        media_type="application/zip",
        filename=f"{safe_event}_certificates.zip",
        background=BackgroundTask(lambda: os.unlink(tmp_zip_path) if os.path.exists(tmp_zip_path) else None),
    )


# ---------------------------------------------------------------------------
# 6. Public Certificate Authenticity Verification
# ---------------------------------------------------------------------------
@router.get(
    "/api/v1/certificates/{certificate_id}/verify",
    response_model=CertificateVerificationResponse,
    summary="Verify certificate authenticity",
    description="Public endpoint to verify whether a given certificate ID is genuine and valid.",
)
def verify_certificate(
    certificate_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> CertificateVerificationResponse:
    """Verify certificate authenticity."""
    cert = db.get(Certificate, certificate_id)
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found.",
        )

    job = cert.job
    is_valid = cert.status == CertificateStatus.GENERATED

    return CertificateVerificationResponse(
        certificate_id=cert.id,
        is_valid=is_valid,
        status=cert.status,
        recipient_name=cert.recipient_name,
        title=job.title if job else None,
        event_name=job.event_name if job else None,
        issued_by=job.issued_by if job else None,
        issue_date=job.issue_date if job else None,
    )
