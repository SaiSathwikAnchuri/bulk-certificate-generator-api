# Bulk Certificate Generator API

A high-performance, resilient backend API built with **FastAPI**, **PostgreSQL** (SQLAlchemy 2.0), and **ReportLab** to generate, track, and retrieve certificates in bulk with per-row failure isolation.

---

## 🌟 Key Features

- **Asynchronous Bulk Processing**: Accepts jobs with up to 1,000+ recipients, persists the job immediately, returns `202 Accepted` with a job ID, and offloads rendering to the background.
- **Two-Tier Validation Strategy**:
  - **Level 1 (Request Schema)**: Pydantic v2 rejects malformed payloads, invalid dates, and oversized batches with `422 Unprocessable Entity`.
  - **Level 2 (Row-Level Partial Acceptance)**: Individual recipient records with invalid emails, duplicate emails, or empty names are flagged as `invalid` without aborting the job. Valid recipients proceed to PDF generation.
- **Fault-Tolerant Failure Isolation**: Each certificate is generated and committed in an isolated try/except block. If rendering fails for one row, the error is recorded, and remaining certificates continue processing.
- **Deterministic Job Status Lifecyle**:
  - `pending` ➔ `processing` ➔ `completed` (all succeeded)
  - `completed_with_errors` (some succeeded, some failed or invalid)
  - `failed` (all failed or fatal error)
- **Flexible Retrieval & Verification**:
  - Single certificate PDF download (`Content-Disposition: inline`)
  - Bulk ZIP archive generation with streaming cleanup
  - Public certificate verification endpoint (`/api/v1/verify/{certificate_id}`)
- **Full Test Coverage**: 39 automated pytest tests covering API contracts, PDF output, edge cases, failure isolation, and retrieval.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **API Framework** | FastAPI + Uvicorn | High throughput, async support, auto-generated OpenAPI docs at `/docs` |
| **Relational Database** | PostgreSQL via SQLAlchemy 2.0 | Transactional integrity, ACID guarantees, relational integrity for Jobs & Certificates |
| **Database Driver** | psycopg 3 (binary) | Modern Python 3.12+ compatible PostgreSQL driver |
| **Validation** | Pydantic v2 + email-validator | Strongly-typed validation with granular error reporting |
| **PDF Generation** | ReportLab | Pure Python vector rendering without external binary dependencies |
| **Testing** | Pytest + Starlette TestClient + pypdf | Unit and integration testing with isolated SQLite test fixtures |

---

## 📂 Project Structure

```text
bulk-certificate-generator/
├── app/
│   ├── __init__.py
│   ├── config.py                 # Pydantic Settings & environment variables
│   ├── database.py               # SQLAlchemy engine, sessionmaker, and Base
│   ├── main.py                   # FastAPI application factory & lifespan
│   ├── models.py                 # SQLAlchemy ORM models (Job, Certificate)
│   ├── schemas.py                # Pydantic v2 request/response schemas
│   ├── routes/
│   │   ├── __init__.py
│   │   └── jobs.py               # REST endpoints for jobs and certificates
│   └── services/
│       ├── __init__.py
│       ├── certificate_generator.py # ReportLab PDF canvas drawing service
│       ├── job_processor.py      # Background worker with failure isolation
│       └── validation.py         # Two-tier recipient validation logic
├── examples/
│   └── sample_request.json       # Example payload for testing
├── tests/
│   ├── conftest.py               # Test fixtures (SQLite test DB, isolated client)
│   ├── test_create_job.py        # POST /api/v1/jobs integration tests
│   ├── test_failures.py          # Failure isolation & partial success tests
│   ├── test_generator.py         # ReportLab PDF rendering tests
│   ├── test_job_status.py        # Status polling & filtering tests
│   ├── test_retrieval.py         # Single download, ZIP, and verification tests
│   └── test_validation.py        # Request & row-level validation tests
├── storage/                      # Generated certificate PDFs (git-ignored)
├── requirements.txt              # Production & test dependencies
├── .env.example                  # Environment variable template
└── README.md                     # Documentation
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 14+** (optional for running tests, which use isolated SQLite by default)

### 1. Clone & Set Up Virtual Environment

```bash
cd "bulk-certificate generator"
python -m venv .venv

# On Windows (PowerShell)
.venv\Scripts\Activate.ps1

# On macOS/Linux
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` to match your database credentials:

```ini
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/certificates
STORAGE_DIR=storage/certificates
MAX_RECIPIENTS=1000
```

### 4. Create PostgreSQL Database

```sql
CREATE DATABASE certificates;
```

*(Tables are created automatically when the FastAPI application starts via the lifespan handler).*

### 5. Run the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Reference & Endpoints

### 1. Submit Bulk Certificate Job
- **`POST /api/v1/jobs`**
- **Status Code**: `202 Accepted`

#### Request Body
```json
{
  "certificate": {
    "title": "Certificate of Completion",
    "event_name": "Full Stack AI Bootcamp 2026",
    "issue_date": "2026-10-10",
    "issued_by": "DeepMind Academy"
  },
  "recipients": [
    {
      "name": "Alice Smith",
      "email": "alice@example.com"
    },
    {
      "name": "Bob Jones",
      "email": "invalid-email"
    }
  ]
}
```

#### Response (`202 Accepted`)
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "total_recipients": 2,
  "accepted": 1,
  "invalid": 1,
  "invalid_rows": [
    {
      "row_index": 1,
      "error": "Invalid email address format: invalid-email"
    }
  ],
  "status_url": "/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

---

### 2. Poll Job Status
- **`GET /api/v1/jobs/{job_id}`**
- Returns aggregate progress, timestamps, and resource links.

#### Response (`200 OK`)
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed_with_errors",
  "total_recipients": 2,
  "counts": {
    "generated": 1,
    "failed": 0,
    "invalid": 1,
    "pending": 0
  },
  "created_at": "2026-10-10T05:00:00Z",
  "started_at": "2026-10-10T05:00:01Z",
  "completed_at": "2026-10-10T05:00:02Z",
  "_links": {
    "certificates": "/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/certificates",
    "download_all": "/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/download"
  }
}
```

---

### 3. List Job Certificates (with Pagination & Filtering)
- **`GET /api/v1/jobs/{job_id}/certificates?status=generated&limit=50&offset=0`**
- Supported `status` filters: `pending`, `generated`, `failed`, `invalid`

#### Response (`200 OK`)
```json
{
  "total": 1,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": "e4eaaaf2-d142-11e1-b3e4-080027620cdd",
      "row_index": 0,
      "recipient_name": "Alice Smith",
      "recipient_email": "alice@example.com",
      "status": "generated",
      "error_message": null,
      "download_url": "/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/certificates/e4eaaaf2-d142-11e1-b3e4-080027620cdd/download"
    }
  ]
}
```

---

### 4. Download Single Certificate PDF
- **`GET /api/v1/jobs/{job_id}/certificates/{certificate_id}/download`**
- **Response**: `application/pdf` binary stream with filename `Alice_Smith_Certificate.pdf`.
- **Status Codes**:
  - `200 OK`: File downloaded successfully
  - `404 Not Found`: Certificate or file does not exist
  - `409 Conflict`: Certificate is `pending` (not ready yet) or `failed`

---

### 5. Download All Certificates as ZIP Archive
- **`GET /api/v1/jobs/{job_id}/download`**
- **Response**: `application/zip` bundle with background cleanup of temporary archive.
- Returns `409 Conflict` if the job is still `pending` or `processing`.

---

### 6. Public Certificate Verification
- **`GET /api/v1/verify/{certificate_id}`**
- Public endpoint (no job ID required) to independently verify authenticity.

#### Response (`200 OK`)
```json
{
  "certificate_id": "e4eaaaf2-d142-11e1-b3e4-080027620cdd",
  "recipient_name": "Alice Smith",
  "title": "Certificate of Completion",
  "event_name": "Full Stack AI Bootcamp 2026",
  "issue_date": "2026-10-10",
  "issued_by": "DeepMind Academy",
  "generated_at": "2026-10-10T05:00:02Z",
  "is_valid": true
}
```

---

## 🧪 Running the Test Suite

The test suite runs against an isolated SQLite test database with automated schema creation and cleanup.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=term-missing
```

### Test Coverage Highlights (39 Tests)
- **`test_create_job.py`**: Job submission, validation rules, database record creation.
- **`test_validation.py`**: Malformed JSON, required fields, invalid emails, empty strings, duplicates.
- **`test_generator.py`**: PDF rendering, typography, long recipient names, text extraction via pypdf.
- **`test_failures.py`**: Per-row failure isolation, ensuring one error doesn't halt subsequent generation.
- **`test_job_status.py`**: Status polling, count calculation, query parameter filtering.
- **`test_retrieval.py`**: PDF stream verification, ZIP archive validation, public verification endpoint.

---

## 🛡️ Resilience & Security Design

1. **Failure Isolation**: Generation of each PDF runs inside a per-item transaction so transient errors (e.g., rendering bugs) are recorded on that row without crashing the job.
2. **Safe Filenames**: Content-Disposition headers sanitize recipient names with `re.sub(r'[\/*?:"<>| ]+', '_', name)` to prevent directory traversal or header injection.
3. **Atomic File Writes**: ReportLab renders PDFs to a temporary buffer and writes to destination paths with directory auto-creation (`parents=True, exist_ok=True`).
4. **Temporary ZIP Cleanup**: The bulk ZIP download utilizes FastAPI's `BackgroundTask` to safely delete temporary archives from disk immediately after streaming to the client.
