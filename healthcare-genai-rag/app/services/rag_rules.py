from __future__ import annotations

import re
from datetime import date

from app.schemas.rag import PriorAuthExtraction


_DATE_ISO = r"\d{4}-\d{2}-\d{2}"
_DATE_NUM = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
_DATE_MONTHNAME = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},\s*\d{4}"
)
_DATE_TOKEN = rf"(?:{_DATE_ISO}|{_DATE_NUM}|{_DATE_MONTHNAME})"

_MONTH_NAME_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(\d{1,2}),\s*(\d{4})\b",
    re.IGNORECASE,
)

_SERVICE_DATE_LABEL_RE = re.compile(rf"\b(?:service date|date of service|dos)\b\s*[:\-]?\s*({_DATE_TOKEN})\b", re.IGNORECASE)
_ADMISSION_DATE_LABEL_RE = re.compile(rf"\badmission date\b\s*[:\-]?\s*({_DATE_TOKEN})\b", re.IGNORECASE)
_DOB_LABEL_RE = re.compile(rf"\b(?:dob|date of birth|birth date)\b(?:\s*\(dob\))?\s*[:\-]?\s*({_DATE_TOKEN})\b", re.IGNORECASE)

_AUTH_PERIOD_RE = re.compile(
    rf"\bauthorization period\b\s*[:\-]?\s*({_DATE_TOKEN})\s+\bto\b\s+({_DATE_TOKEN})\b",
    re.IGNORECASE,
)

_DECISION_LABEL_RE = re.compile(r"\bdecision\b\s*[:\-]\s*(approved|denied|pending|in review)\b", re.IGNORECASE)
_RATIONALE_LABEL_RE = re.compile(
    r"\b(?:rationale|reason(?:\s+for\s+denial)?|denial\s+reason)\b\s*[:\-]\s*(.+)",
    re.IGNORECASE,
)

_PATIENT_ID_RE = re.compile(r"\bpatient id\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)
_MEMBER_ID_RE = re.compile(r"\bmember id\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)
_SUBSCRIBER_ID_RE = re.compile(r"\bsubscriber id\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)
_MEMBER_GROUP_RE = re.compile(r"\b(?:member group|group id|group number|member group id)\b\s*[:\-]\s*([A-Z0-9\-_]+)\b", re.IGNORECASE)


def _to_iso_date(y: int, m: int, d: int) -> str:
    return date(y, m, d).isoformat()


def normalize_date_to_iso(value: str) -> str:
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
        try:
            return _to_iso_date(int(year_s), month_map[month_name.lower()], int(day_s))
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

    # Ireland/UK default: DD/MM on ambiguity
    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        month, day = a, b
    else:
        day, month = a, b

    try:
        return _to_iso_date(y, month, day)
    except ValueError:
        return v


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


def extract_structured_from_context(context: str) -> PriorAuthExtraction:
    ctx = context or ""
    out = PriorAuthExtraction()

    # decision
    m = _DECISION_LABEL_RE.search(ctx)
    if m:
        out.decision = _normalize_decision(m.group(1))
    else:
        out.decision = "unknown"

    # dates
    m = _DOB_LABEL_RE.search(ctx)
    if m:
        out.dob = normalize_date_to_iso(m.group(1))

    m = _SERVICE_DATE_LABEL_RE.search(ctx)
    if m:
        out.service_date = normalize_date_to_iso(m.group(1))

    m = _ADMISSION_DATE_LABEL_RE.search(ctx)
    if m:
        out.admission_date = normalize_date_to_iso(m.group(1))

    m = _AUTH_PERIOD_RE.search(ctx)
    if m:
        out.authorization_period_start = normalize_date_to_iso(m.group(1))
        out.authorization_period_end = normalize_date_to_iso(m.group(2))

    # ids
    m = _PATIENT_ID_RE.search(ctx)
    out.patient_id = m.group(1).strip() if m else "unknown"

    m = _MEMBER_ID_RE.search(ctx) or _SUBSCRIBER_ID_RE.search(ctx)
    out.member_id = m.group(1).strip() if m else "unknown"

    m = _MEMBER_GROUP_RE.search(ctx)
    out.member_group = m.group(1).strip() if m else "unknown"

    # rationale
    for line in ctx.splitlines():
        ln = line.strip()
        if not ln:
            continue
        m = _RATIONALE_LABEL_RE.search(ln)
        if m:
            out.rationale = " ".join(m.group(1).split()).strip()
            break

    return out