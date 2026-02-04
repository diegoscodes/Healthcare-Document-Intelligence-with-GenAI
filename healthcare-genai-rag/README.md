# Healthcare Document Intelligence with GenAI (MediRAG)

MediRAG is a **Healthcare / Pharma Document Intelligence** system designed to ingest complex documents (e.g., Prior Authorizations, Pharmacy Agreements) and turn them into **structured, reliable, auditable data** using **GenAI + Retrieval-Augmented Generation (RAG)**.

> Current status: Backend MVP is working (API + DB + migrations + PDF upload + inline view/download).

---

## What this project does (today)

### Backend API (FastAPI)
- FastAPI application with automatic OpenAPI/Swagger docs at:
  - `GET /docs`
- Health check endpoint:
  - `GET /health`

### Database (PostgreSQL + SQLAlchemy)
- PostgreSQL running via Docker Compose
- SQLAlchemy ORM models
- Alembic migrations for schema evolution

### Document upload & storage
- Upload a PDF via:
  - `POST /documents` (multipart/form-data)
- The uploaded file is persisted to disk at:
  - `data/uploads/<document_id>/original.pdf`
- Document metadata is stored in PostgreSQL:
  - `id` (UUID)
  - `filename`
  - `content_type`
  - `status` (e.g., `created`, `uploaded`)
  - `storage_path`
  - `created_at`

### Document serving (inline and download)
- Read document metadata:
  - `GET /documents/{document_id}`
- Open inline (when possible, e.g. PDFs):
  - `GET /documents/{document_id}/file`
- Force download:
  - `GET /documents/{document_id}/file/download`

---

## Project structure (high level)


---

## Quickstart (local development)

### 1) Start PostgreSQL (Docker)
From `healthcare-genai-rag/`:


### 2) Configure environment variables
Create a `.env` file at `healthcare-genai-rag/.env`:


> Use the same values defined in `docker-compose.yml`.

### 3) Install dependencies
Activate your virtual environment and run:


### 4) Run database migrations (Alembic)


### 5) Run the API



Open:
- Swagger UI: http://127.0.0.1:8000/docs

---

## Sample PDF (optional)
A small PDF generator is available:

- `data/samples/generate_sample_pdf.py`

It produces:
- `data/samples/sample_prior_authorization.pdf`

You can upload it using `POST /documents` in Swagger.

---

## Roadmap / Next steps

### Document Intelligence
- Extract text from uploaded PDFs (and OCR for scanned documents)
- Chunking with audit-friendly metadata (page, offsets)
- Persist extracted text and chunks in the database

### RAG pipeline
- Embeddings + vector store (e.g., pgvector)
- Retrieval with controlled context
- Q&A / search endpoints with grounded answers

### Structured extraction
- JSON extraction with Pydantic validation
- Evidence tracing (which chunks/pages support each field)
- Prompt + schema versioning for reproducibility

### Quality & Ops
- Automated tests (pytest) for upload + metadata + file serving
- Structured logging and traceability by `document_id`
- Docker Compose setup for running API + DB together (optional)

---

## Security notes
- Do **not** commit `.env` files.
- Avoid using real sensitive patient data in `data/samples/`.