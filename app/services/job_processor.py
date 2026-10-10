"""Background job worker and failure isolation service."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
import app.database as db_module
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.services.certificate_generator import generate_certificate

logger = logging.getLogger(__name__)


def build_certificate_data(job: Job, cert: Certificate) -> dict[str, Any]:
    """Build the dictionary expected by generate_certificate from DB entities."""
    return {
        "certificate_id": str(cert.id),
        "recipient_name": cert.recipient_name or "",
        "title": job.title,
        "event_name": job.event_name,
        "issue_date": job.issue_date.isoformat(),
        "issued_by": job.issued_by,
    }


def get_certificate_output_path(job_id: uuid.UUID, cert_id: uuid.UUID) -> Path:
    """Generate the target file path on disk for a certificate."""
    return Path(settings.storage_dir) / str(job_id) / f"{cert_id}.pdf"


def determine_final_job_status(db: Session, job_id: uuid.UUID) -> JobStatus:
    """Determine final job status according to specification rules.

    Rules:
    - Every valid row generated and none invalid -> COMPLETED
    - At least one generated, and some failed or invalid -> COMPLETED_WITH_ERRORS
    - Zero generated -> FAILED
    """
    stmt = (
        select(Certificate.status, func.count(Certificate.id))
        .where(Certificate.job_id == job_id)
        .group_by(Certificate.status)
    )
    results = db.execute(stmt).all()
    counts = {status: count for status, count in results}

    generated_count = counts.get(CertificateStatus.GENERATED, 0)
    failed_count = counts.get(CertificateStatus.FAILED, 0)
    invalid_count = counts.get(CertificateStatus.INVALID, 0)
    total_valid = generated_count + failed_count

    if total_valid > 0 and generated_count == total_valid and invalid_count == 0:
        return JobStatus.COMPLETED
    elif generated_count > 0:
        return JobStatus.COMPLETED_WITH_ERRORS
    else:
        return JobStatus.FAILED


def process_job(
    job_id: uuid.UUID,
    session_factory: Callable[[], Session] | sessionmaker | None = None,
    generator: Callable[[dict[str, Any], Path | str], Path] | None = None,
) -> None:
    """Execute background certificate generation with row-level failure isolation.

    Args:
        job_id: The UUID of the Job to process.
        session_factory: Optional callable yielding a DB session (defaults to db_module.SessionLocal).
        generator: Pure function that produces the certificate file (defaults to generate_certificate).
    """
    if session_factory is None:
        session_factory = db_module.SessionLocal
    if generator is None:
        generator = generate_certificate

    logger.info("Starting background processing for job %s", job_id)

    with session_factory() as db:
        job = db.get(Job, job_id)
        if not job:
            logger.error("Job %s not found for processing", job_id)
            return

        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            pending_certs = db.scalars(
                select(Certificate)
                .where(
                    Certificate.job_id == job_id,
                    Certificate.status == CertificateStatus.PENDING,
                )
                .order_by(Certificate.row_index)
            ).all()

            for cert in pending_certs:
                try:
                    data = build_certificate_data(job, cert)
                    out_path = get_certificate_output_path(job.id, cert.id)
                    generator(data, out_path)

                    cert.status = CertificateStatus.GENERATED
                    cert.file_path = f"{job.id}/{cert.id}.pdf"
                    cert.generated_at = datetime.now(timezone.utc)
                    cert.error_message = None
                except Exception as exc:
                    logger.exception("Certificate generation failed for certificate %s", cert.id)
                    cert.status = CertificateStatus.FAILED
                    cert.error_message = str(exc)[:500]

                db.commit()

            job.status = determine_final_job_status(db, job_id)

        except Exception as exc:
            logger.exception("Fatal error occurred during job processing %s: %s", job_id, exc)
            job.status = JobStatus.FAILED

        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Finished processing job %s with final status %s", job_id, job.status.value)
