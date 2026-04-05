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


## 🛠️ Local Setup Guide

### 1️⃣ Start PostgreSQL (Docker)

From the project root:

```bash
cd healthcare-genai-rag
docker compose up -d
```

Verify container:

```bash
docker ps
```

---

### 2️⃣ Configure Environment Variables

Create a `.env` file in:

```
healthcare-genai-rag/.env
```

Example:

```env
DATABASE_URL=postgresql+psycopg://<DB_USER>:<DB_PASSWORD>@127.0.0.1:5432/<DB_NAME>
```

Replace:
- `postgres` → DB user  
- `postgres` → DB password  
- `healthcare_db` → Database name  

Values must match your `docker-compose.yml`.

---

### 3️⃣ Install Dependencies

Activate virtual environment:

**Windows**
```bash
.venv\Scripts\activate
```

**Mac/Linux**
```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Run Database Migrations (Alembic)

Ensure:
- PostgreSQL container is running
- `.env` is correctly configured

Run:

```bash
alembic upgrade head
```

---

### 5️⃣ Run the API

Since `main.py` is inside `app/`, run:

```bash
uvicorn app.main:app --reload
```

Or:

```bash
python -m uvicorn app.main:app --reload
```

---

## 🌐 Access the API

Swagger UI:

```
http://127.0.0.1:8000/docs
```

---

# 🧪 Manual API Testing (Swagger)

### 1. Upload Document
`POST /documents`

- Upload a PDF
- Copy returned `document_id`

---

### 2. Process Document
`POST /documents/{document_id}/process`

Expected:
```json
{
  "status": "parsed"
}
```

---

### 3. Retrieve Pages
`GET /documents/{document_id}/pages`

Example query params:

```
include_text=false
limit=1
offset=0
```

---

### 4. View File
`GET /documents/{document_id}/file`

Inline preview.

---

### 5. Download File
`GET /documents/{document_id}/file/download`

---

# 📄 Sample PDF Generator (Optional)

Generate a test PDF:

```bash
python data/samples/generate_sample_pdf.py
```

Output:

```
data/samples/sample_prior_authorization.pdf
```

---

# 🧭 Roadmap

## MVP
- Page-based chunking with audit-friendly metadata
- PostgreSQL Full-Text Search (FTS)
- Structured extraction with Pydantic validation
- Minimal review UI

## Scale
- `pgvector` embeddings
- Hybrid retrieval (FTS + semantic)
- Async processing (queue-based architecture)
- Observability (structured logs, metrics)
- CI testing (unit + integration)

---

# 🔐 Security Notes

- Do **NOT** commit `.env` files
- Avoid real sensitive healthcare data locally
- Rotate secrets regularly

---

# 📌 Technical Notes

- PDF text extraction uses **pdfplumber**
- Works best with text-based PDFs
- Scanned PDFs require OCR (e.g., Tesseract)
