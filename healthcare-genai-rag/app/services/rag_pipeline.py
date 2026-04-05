from __future__ import annotations

import json
import os
import re
from datetime import date

from app.schemas.rag import Evidence, PriorAuthExtraction, RagExtractResponse

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from weaviate.classes.query import Filter

from app.schemas.rag import Evidence, PriorAuthExtraction, RagExtractResponse
from app.services.embeddings import get_embeddings
from app.services.weaviate_client import get_weaviate_client


# -----------------------
# JSON hardening (cheap)
# -----------------------
def _extract_json_candidate(text: str) -> str | None:
    """
    Best-effort extraction of a JSON object from a messy LLM response.
    Cheap and deterministic.
    """
    if not text:
        return None
    s = text.strip()

    # If response is already pure JSON
    if s.startswith("{") and s.endswith("}"):
        return s

    # Try to find the first {...} block
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1].strip()

    return None


def _build_repair_prompt(schema_prompt: str, raw: str) -> str:
    """
    Ask the model to output valid JSON only.
    Keep it short to reduce cost.
    """
    raw_short = (raw or "").strip()
    if len(raw_short) > 3000:
        raw_short = raw_short[:3000] + "\n...[truncated]..."

    return f"""
You previously returned an invalid response.

Return JSON ONLY (no markdown, no commentary), matching the required schema exactly.

{schema_prompt}

Invalid response to fix:
{raw_short}
""".strip()


def parse_llm_json_with_repair(llm: object, *, schema_prompt: str, raw: str) -> tuple[dict, list[str]]:
    """
    Unit-test friendly helper:
    - tries to parse JSON from `raw`
    - if invalid, makes ONE repair call: llm.invoke(repair_prompt).content
    - returns (payload, warnings)
    """
    warnings: list[str] = []

    candidate = _extract_json_candidate(raw) or (raw or "")
    try:
        payload = json.loads(candidate)
        return payload, warnings
    except Exception:
        repair_prompt = _build_repair_prompt(schema_prompt=schema_prompt, raw=raw)
        repaired = getattr(llm, "invoke")(repair_prompt).content

        candidate = _extract_json_candidate(repaired) or (repaired or "")
        payload = json.loads(candidate)

        warnings.append("Model output was invalid JSON; auto-repaired successfully.")
        return payload, warnings


# -----------------------
# Index presence check
# -----------------------
def is_document_indexed(document_id: str) -> bool:
    """
    Returns True if Weaviate has at least one DocumentChunk for the document_id.
    Used by the agentic workflow for auto-remediation (index-if-missing).
    """
    client = get_weaviate_client()
    try:
        collection = client.collections.get("DocumentChunk")
        res = collection.query.fetch_objects(
            limit=1,
            filters=Filter.by_property("document_id").equal(document_id),
            return_properties=["document_id"],
        )
        return bool(res.objects)
    finally:
        client.close()

# -----------------------
# Patterns
# -----------------------
# Basic date token patterns
_DATE_ISO = r"\d{4}-\d{2}-\d{2}"
_DATE_NUM = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
_DATE_MONTHNAME = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},\s*\d{4}"
)
_DATE_TOKEN = rf"(?:{_DATE_ISO}|{_DATE_NUM}|{_DATE_MONTHNAME})"

_DATE_RE = re.compile(rf"\b({_DATE_ISO}|{_DATE_NUM})\b", re.IGNORECASE)
_MONTH_NAME_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(\d{1,2}),\s*(\d{4})\b",
    re.IGNORECASE,
)

_RATIONALE_HINTS = re.compile(
    r"\b(meets criteria|criteria|rationale|reason|because|documentation|eligible|approved|denied|coverage|attestation)\b",
    re.IGNORECASE,
)

_ID_LIKE_RE = re.compile(r"^(?=.*\d)[A-Z0-9\-_]{4,}$", re.IGNORECASE)
_GROUP_LIKE_RE = re.compile(r"^(GRP|GROUP)[\-_ ]?\d+", re.IGNORECASE)

# -----------------------
# Label-based extraction regex
# (capture only a DATE TOKEN, not the entire line)
# -----------------------
_SERVICE_DATE_LABEL_RE = re.compile(rf"\b(?:service date|date of service|dos)\b\s*[:\-]?\s*({_DATE_TOKEN})\b", re.IGNORECASE)
_ADMISSION_DATE_LABEL_RE = re.compile(rf"\badmission date\b\s*[:\-]?\s*({_DATE_TOKEN})\b", re.IGNORECASE)
_DOB_LABEL_RE = re.compile(rf"\b(?:dob|date of birth|birth date)\b(?:\s*\(dob\))?\s*[:\-]?\s*({_DATE_TOKEN})\b", re.IGNORECASE)

# Authorization period: two date tokens
_AUTH_PERIOD_RE = re.compile(
    rf"\bauthorization period\b\s*[:\-]?\s*({_DATE_TOKEN})\s+\bto\b\s+({_DATE_TOKEN})\b",
    re.IGNORECASE,
)

# Fallback "Date: <date>"
_DOCUMENT_DATE_LABEL_RE = re.compile(rf"\bdate\b\s*[:\-]\s*({_DATE_TOKEN})\b", re.IGNORECASE)

# Decision
_DECISION_LABEL_RE = re.compile(r"\bdecision\b\s*[:\-]\s*(approved|denied|pending|in review)\b", re.IGNORECASE)

# Rationale
_RATIONALE_LABEL_RE = re.compile(
    r"\b(?:rationale|reason(?:\s+for\s+denial)?|denial\s+reason)\b\s*[:\-]\s*(.+)",
    re.IGNORECASE,
)

# IDs
_PATIENT_ID_RE = re.compile(r"\bpatient id\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)
_MEMBER_ID_RE = re.compile(r"\bmember id\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)
_SUBSCRIBER_ID_RE = re.compile(r"\bsubscriber id\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)
_MEMBER_GROUP_RE = re.compile(r"\b(?:member group|group id|group number|member group id)\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)


# -----------------------
# LLM
# -----------------------
def _get_llm() -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    if not model:
        raise RuntimeError("OPENAI_MODEL is not set")
    return ChatOpenAI(model=model, api_key=api_key, temperature=0)


def _build_prompt(query: str, context: str) -> str:
    return f"""
You are an information extraction system for healthcare prior authorization documents.

Return JSON ONLY matching this schema:

{{
  "patient_name": "",
  "patient_id": "",
  "member_id": "",
  "member_group": "",
  "dob": "",
  "service_date": "",
  "admission_date": "",
  "authorization_period_start": "",
  "authorization_period_end": "",
  "diagnosis": "",
  "icd10_codes": [],
  "medications": [{{"name": "", "dose": "", "frequency": ""}}],
  "provider": "",
  "decision": "unknown",
  "rationale": ""
}}

Hard rules:
- Output MUST be valid JSON (no markdown, no extra keys).
- If unknown, use "" or [].
- decision must be one of: "approved", "denied", "pending", "unknown".
- Do not invent values.

User question:
{query}

Context (use only this as evidence):
{context}
""".strip()


# -----------------------
# Normalization helpers
# -----------------------
def _distance_to_similarity(distance: float | None) -> float | None:
    if distance is None:
        return None
    d = float(distance)
    if d < 0:
        return None
    return 1.0 / (1.0 + d)


def _normalize_decision(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return "unknown"
    if v in {"approved", "denied", "pending", "unknown"}:
        return v
    if "approv" in v:
        return "approved"
    if "deni" in v:
        return "denied"
    if "pend" in v or "review" in v:
        return "pending"
    return "unknown"


def _normalize_rationale(text: str, max_len: int = 240) -> str:
    t = " ".join((text or "").replace("\n", " ").split()).strip()
    if not t:
        return ""
    if len(t) > max_len:
        return t[: max_len - 1].rstrip() + "…"
    return t


def _unknown_if_empty(value: str) -> str:
    v = (value or "").strip()
    return v if v else "unknown"


def _to_iso_date(y: int, m: int, d: int) -> str:
    return date(y, m, d).isoformat()


def _normalize_date_to_iso(value: str) -> str:
    """
    Best-effort normalization to YYYY-MM-DD.

    Ireland/UK default:
      - If numeric date is ambiguous (both day and month <= 12), assume DD/MM.
    """
    v = (value or "").strip()
    if not v:
        return ""

    m = _MONTH_NAME_RE.search(v)
    if m:
        month_name, day_s, year_s = m.groups()
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        }
        month = month_map[month_name.lower()]
        day = int(day_s)
        year = int(year_s)
        try:
            return _to_iso_date(year, month, day)
        except ValueError:
            return v

    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        y, mo, da = map(int, m.groups())
        try:
            return _to_iso_date(y, mo, da)
        except ValueError:
            return v

    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})", v)
    if not m:
        return v

    a, b, y = m.groups()
    a = int(a)
    b = int(b)
    y = int(y)
    if y < 100:
        y += 2000

    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        month, day = a, b
    else:
        day, month = a, b  # DD/MM default for Ireland/UK

    try:
        return _to_iso_date(y, month, day)
    except ValueError:
        return v


def _normalize_payload_before_validation(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    if "decision" in payload:
        payload["decision"] = _normalize_decision(str(payload.get("decision") or ""))
    return payload


# -----------------------
# Rule-based extraction
# -----------------------
def _rule_based_service_date(context: str) -> str:
    ctx = context or ""
    m = _SERVICE_DATE_LABEL_RE.search(ctx)
    if m:
        return m.group(1).strip()
    m = _DOCUMENT_DATE_LABEL_RE.search(ctx)
    if m:
        return m.group(1).strip()
    return ""


def _rule_based_admission_date(context: str) -> str:
    ctx = context or ""
    m = _ADMISSION_DATE_LABEL_RE.search(ctx)
    if m:
        return m.group(1).strip()
    return ""


def _rule_based_auth_period(context: str) -> tuple[str, str]:
    ctx = context or ""
    m = _AUTH_PERIOD_RE.search(ctx)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _rule_based_dob(context: str) -> str:
    ctx = context or ""
    m = _DOB_LABEL_RE.search(ctx)
    if m:
        return m.group(1).strip()
    return ""


def _rule_based_decision(context: str) -> str:
    ctx = context or ""
    m = _DECISION_LABEL_RE.search(ctx)
    if m:
        return _normalize_decision(m.group(1))

    c = ctx.lower()
    if "denied" in c or "denial" in c or "not approved" in c:
        return "denied"
    if "approved" in c or "approval" in c or "authorized" in c:
        return "approved"
    if "pending" in c or "in review" in c or "under review" in c:
        return "pending"
    return "unknown"


def _rule_based_rationale(context: str) -> str:
    ctx = context or ""
    for line in ctx.splitlines():
        ln = line.strip()
        if not ln:
            continue
        m = _RATIONALE_LABEL_RE.search(ln)
        if m:
            return _normalize_rationale(m.group(1))
    return ""


def _rule_based_ids(context: str) -> dict[str, str]:
    ctx = context or ""
    out: dict[str, str] = {}

    m = _PATIENT_ID_RE.search(ctx)
    if m:
        out["patient_id"] = m.group(1).strip()

    m = _MEMBER_ID_RE.search(ctx)
    if m:
        out["member_id"] = m.group(1).strip()
    else:
        m = _SUBSCRIBER_ID_RE.search(ctx)
        if m:
            out["member_id"] = m.group(1).strip()

    m = _MEMBER_GROUP_RE.search(ctx)
    if m:
        out["member_group"] = m.group(1).strip()

    return out


# -----------------------
# Vector retrieval
# -----------------------
def _score_chunk_text(text: str) -> int:
    t = (text or "").lower()
    score = 0
    if _DATE_RE.search(t):
        score += 2
    if "service date" in t or "date of service" in t or "dos" in t:
        score += 3
    if "admission date" in t:
        score += 3
    if "authorization period" in t:
        score += 3
    if "dob" in t or "date of birth" in t or "birth date" in t:
        score += 3
    if "decision" in t:
        score += 2
    if "rationale" in t or "reason" in t:
        score += 2
    return score


def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
    seen: set[tuple[int | None, int | None]] = set()
    out: list[dict] = []
    for ch in chunks:
        key = (ch.get("page_number"), ch.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ch)
    return out


def _query_weaviate(document_id: str, query: str, limit: int) -> list[dict]:
    embeddings = get_embeddings()
    client = get_weaviate_client()
    try:
        collection = client.collections.get("DocumentChunk")
        query_vector = embeddings.embed_query(query)

        result = collection.query.near_vector(
            near_vector=query_vector,
            limit=limit,
            filters=Filter.by_property("document_id").equal(document_id),
            return_metadata=["distance"],
            return_properties=["document_id", "page_number", "chunk_index", "text"],
        )

        items: list[dict] = []
        for obj in result.objects:
            props = obj.properties or {}
            distance = getattr(obj.metadata, "distance", None)
            text = props.get("text") or ""
            items.append(
                {
                    "document_id": props.get("document_id"),
                    "page_number": props.get("page_number"),
                    "chunk_index": props.get("chunk_index"),
                    "text": text,
                    "distance": distance,
                    "similarity": _distance_to_similarity(distance),
                    "boost": _score_chunk_text(text),
                }
            )
        return items
    finally:
        client.close()


def _build_context(chunks: list[dict], max_context_chars: int) -> tuple[str, list[dict]]:
    chunks = sorted(
        chunks,
        key=lambda x: (
            x.get("similarity") is not None,
            x.get("similarity") or 0.0,
            x.get("boost") or 0,
        ),
        reverse=True,
    )

    lines: list[str] = []
    used: list[dict] = []
    total = 0

    for it in chunks:
        pn = it.get("page_number")
        ci = it.get("chunk_index")
        txt = (it.get("text") or "").strip().replace("\n", " ")
        line = f"[page={pn} chunk={ci}] {txt}".strip()
        if not line:
            continue

        extra = len(line) + 1
        if lines and (total + extra) > max_context_chars:
            break

        lines.append(line)
        used.append(it)
        total += extra

        if total >= max_context_chars:
            break

    return "\n".join(lines), used


def _pick_rationale_sentence(text: str, max_len: int = 240) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.replace("\n", " ").split()).strip()
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[\.\!\?])\s+|;\s+|\s+-\s+", cleaned)
    candidates = [p.strip() for p in parts if p.strip() and _RATIONALE_HINTS.search(p)]
    if not candidates:
        return ""
    candidates.sort(key=len)
    return _normalize_rationale(candidates[0], max_len=max_len)


# -----------------------
# Postprocess
# -----------------------
def _postprocess_extraction(extraction: PriorAuthExtraction) -> PriorAuthExtraction:
    patient_name = (extraction.patient_name or "").strip()
    if patient_name and _ID_LIKE_RE.match(patient_name):
        extraction.patient_name = ""

    extraction.patient_id = _unknown_if_empty(extraction.patient_id)
    extraction.member_id = _unknown_if_empty(extraction.member_id)
    extraction.member_group = _unknown_if_empty(extraction.member_group)

    extraction.dob = _normalize_date_to_iso(extraction.dob)
    extraction.service_date = _normalize_date_to_iso(extraction.service_date)
    extraction.admission_date = _normalize_date_to_iso(extraction.admission_date)
    extraction.authorization_period_start = _normalize_date_to_iso(extraction.authorization_period_start)
    extraction.authorization_period_end = _normalize_date_to_iso(extraction.authorization_period_end)

    extraction.rationale = _normalize_rationale(extraction.rationale)
    extraction.decision = _normalize_decision(extraction.decision)

    if extraction.member_id and _GROUP_LIKE_RE.match(extraction.member_id) and extraction.member_group == "unknown":
        extraction.member_group = extraction.member_id
        extraction.member_id = "unknown"

    return extraction


def extract_structured_from_context(context: str) -> PriorAuthExtraction:
    """
    Deterministic extraction for tests (no LLM, no vector DB).
    Applies rule-based extraction + normalization + postprocess.
    """
    extraction = PriorAuthExtraction()

    extraction.decision = _rule_based_decision(context)

    sd = _rule_based_service_date(context)
    if sd:
        extraction.service_date = _normalize_date_to_iso(sd)

    ad = _rule_based_admission_date(context)
    if ad:
        extraction.admission_date = _normalize_date_to_iso(ad)

    ap_start, ap_end = _rule_based_auth_period(context)
    if ap_start:
        extraction.authorization_period_start = _normalize_date_to_iso(ap_start)
    if ap_end:
        extraction.authorization_period_end = _normalize_date_to_iso(ap_end)

    dob = _rule_based_dob(context)
    if dob:
        extraction.dob = _normalize_date_to_iso(dob)

    ids = _rule_based_ids(context)
    if ids.get("patient_id"):
        extraction.patient_id = ids["patient_id"]
    if ids.get("member_id"):
        extraction.member_id = ids["member_id"]
    if ids.get("member_group"):
        extraction.member_group = ids["member_group"]

    rat = _rule_based_rationale(context)
    if rat:
        extraction.rationale = rat

    return _postprocess_extraction(extraction)


# -----------------------
# Main
# -----------------------
def extract_structured_json(
    document_id: str,
    query: str,
    top_k: int = 12,
    max_evidence: int = 5,
    max_context_chars: int = 8000,
) -> RagExtractResponse:
    chunks_main = _query_weaviate(document_id=document_id, query=query, limit=top_k)
    chunks_dates = _query_weaviate(
        document_id=document_id,
        query="service date date of service dos admission date authorization period date",
        limit=max(8, top_k // 2),
    )
    chunks_ids = _query_weaviate(
        document_id=document_id,
        query="patient name patient id member id subscriber id member group group id group number dob date of birth",
        limit=max(8, top_k // 2),
    )
    chunks_decision = _query_weaviate(
        document_id=document_id,
        query="decision approved denied pending in review rationale reason",
        limit=max(8, top_k // 2),
    )

    merged = _dedupe_chunks(chunks_main + chunks_dates + chunks_ids + chunks_decision)
    context, used_chunks = _build_context(merged, max_context_chars=max_context_chars)

    llm = _get_llm()
    prompt = _build_prompt(query=query, context=context)
    raw = llm.invoke(prompt).content

    warnings: list[str] = []

    try:
        payload = json.loads(raw)
        payload = _normalize_payload_before_validation(payload)
        extraction = PriorAuthExtraction.model_validate(payload)
    except Exception as e:
        extraction = _postprocess_extraction(PriorAuthExtraction())
        warnings.append(f"Model output invalid; returning empty extraction: {e!s}")
        return RagExtractResponse(
            document_id=document_id,
            query=query,
            extracted=extraction,
            evidence=[],
            warnings=warnings,
        )

    # Rule overrides
    extraction.decision = _rule_based_decision(context)

    sd = _rule_based_service_date(context)
    if sd:
        extraction.service_date = _normalize_date_to_iso(sd)

    ad = _rule_based_admission_date(context)
    if ad:
        extraction.admission_date = _normalize_date_to_iso(ad)

    ap_start, ap_end = _rule_based_auth_period(context)
    if ap_start:
        extraction.authorization_period_start = _normalize_date_to_iso(ap_start)
    if ap_end:
        extraction.authorization_period_end = _normalize_date_to_iso(ap_end)

    dob = _rule_based_dob(context)
    if dob:
        extraction.dob = _normalize_date_to_iso(dob)

    ids = _rule_based_ids(context)
    if ids.get("patient_id"):
        extraction.patient_id = ids["patient_id"]
    if ids.get("member_id"):
        extraction.member_id = ids["member_id"]
    if ids.get("member_group"):
        extraction.member_group = ids["member_group"]

    rat = _rule_based_rationale(context)
    if rat:
        extraction.rationale = rat
    elif used_chunks:
        picked = _pick_rationale_sentence(used_chunks[0].get("text") or "")
        if picked:
            extraction.rationale = picked

    extraction = _postprocess_extraction(extraction)

    evidence_models = [
        Evidence(
            document_id=document_id,
            page_number=it.get("page_number"),
            chunk_index=it.get("chunk_index"),
            snippet=(it.get("text") or "")[:2000],
            similarity=it.get("similarity"),
        )
        for it in used_chunks
    ]
    evidence_models.sort(key=lambda e: (e.similarity is not None, e.similarity or 0.0), reverse=True)
    evidence_models = evidence_models[:max_evidence]

    return RagExtractResponse(
        document_id=document_id,
        query=query,
        extracted=extraction,
        evidence=evidence_models,
        warnings=warnings,
    )