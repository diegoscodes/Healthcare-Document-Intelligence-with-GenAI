# Healthcare Document Intelligence with GenAI (MediRAG)

MediRAG is a **Healthcare / Pharma Document Intelligence** system designed to ingest complex documents (e.g., Prior Authorizations, Pharmacy Agreements) and turn them into **structured, reliable, auditable data** using **GenAI + Retrieval-Augmented Generation (RAG)**.

> Current status: Backend MVP is working (API + DB + migrations + PDF upload + processing + pages API + inline view/download).

---

## Business problem (why this exists)
Reviewing Prior Authorization / Pharmacy documents is slow and error-prone. Teams spend significant time reading PDFs, extracting fields manually, and justifying decisions.

This project aims to reduce review time and increase auditability by:
- extracting text per page,
- storing evidence (pages now, chunks next),
- enabling structured extraction with traceable citations,
- providing a UI for human review and fallback when AI fails.

## ROI (what we measure)
Define baseline and track improvements over time:
- **Time-to-review (TTR)** per document (minutes)
- **Docs/day per reviewer** (throughput)
- **Field-level correction rate** (quality)
- **Evidence coverage** (% extracted fields linked to page/chunk) — target 100%
- **Operational metrics** (p95 latency, failure rate)

## Operational risks & contingency (AI failure modes)
- Parsing failures (scanned PDFs, corrupted files) → manual review mode + clear errors.
- Large documents → pagination + payload controls.
- AI downtime/low quality → fallback layers:
  - keyword search (FTS) and manual review UI
  - retries / queue for async jobs (planned)
  - circuit breaker to disable AI features (planned)

---

## What this project does (today)

### Backend API (FastAPI)
- OpenAPI/Swagger docs:
  - `GET /docs`
- Health check:
  - `GET /health`

### Database (PostgreSQL + SQLAlchemy)
- PostgreSQL via Docker Compose
- SQLAlchemy ORM models
- Alembic migrations

### Document upload, processing & evidence (pages)
- Upload a PDF:
  - `POST /documents` (multipart/form-data)
- File is persisted to disk at:
  - `data/uploads/<document_id>/original.pdf`
- Process a document (extract text per page and persist to DB):
  - `POST /documents/{document_id}/process`
- List pages (supports pagination and optional text):
  - `GET /documents/{document_id}/pages?include_text=false&limit=50&offset=0`
- Read a single page:
  - `GET /documents/{document_id}/pages/{page_number}`

### Document serving (inline and download)
- Read document metadata:
  - `GET /documents/{document_id}`
- Open inline:
  - `GET /documents/{document_id}/file`
- Force download:
  - `GET /documents/{document_id}/file/download`

---

## Quickstart (local development)

    ## Quickstart (local development)

    ### 1) Start PostgreSQL (Docker)
    From `healthcare-genai-rag/`:

    ```bash
    docker compose up -d
    ```

    ### 2) Configure environment variables
    Create a `.env` file at `healthcare-genai-rag/.env` (use values matching your `docker-compose.yml`):

    ```env
    DATABASE_URL=postgresql+psycopg://<DB_USER>:<DB_PASSWORD>@127.0.0.1:5432/<DB_NAME>
    ```

    ### 3) Install dependencies
    Create/activate your virtualenv, then:

    ```bash
    pip install -r requirements.txt
    ```

    ### 4) Run database migrations (Alembic)
    ```bash
    alembic upgrade head
    ```

    ### 5) Run the API
    ```bash
    uvicorn app.main:app --reload
    ```

    Open:
    - Swagger UI: http://127.0.0.1:8000/docs

    ---

    ## Manual test (Swagger)
    1) `POST /documents` → upload a PDF → copy `document_id`
    2) `POST /documents/{document_id}/process` → expect `status="parsed"`
    3) `GET /documents/{document_id}/pages?include_text=false&limit=1&offset=0`
    4) `GET /documents/{document_id}/file` (inline) or `/file/download`

    ---

    ## Sample PDF (optional)
    A small PDF generator is available:
    - `data/samples/generate_sample_pdf.py`

    It produces:
    - `data/samples/sample_prior_authorization.pdf`

    ---

    ## Roadmap (MVP → Scale)
    ### MVP
    - Chunking with audit-friendly metadata (page + offsets)
    - Keyword search (Postgres FTS) over chunks
    - Structured extraction (Pydantic-validated JSON) with evidence
    - Minimal frontend for PDF + extracted JSON + evidence + human review

    ### Scale
    - pgvector embeddings + hybrid retrieval
    - Async job queue for processing/chunking/indexing/extraction
    - Observability (structured logs, metrics, tracing)
    - CI tests (unit + integration)

    ---

    ## Security notes
    - Do **not** commit `.env` files.
    - Avoid using real sensitive data in local samples.

    ## Notes
    - PDF text extraction currently uses `pdfplumber` (works best with text-based PDFs).