from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Document, DocumentPage
from app.schemas.agentic_qa import (
    AgenticQAPlan,
    AgenticQARequest,
    AgenticQAResponse,
    Citation,
    LLMStructuredAnswer,
    PlanStep,
    RetrievedChunk,
    VerificationResult,
    WorkflowStep,
)
from app.services.rag_pipeline import is_document_indexed
from app.services.retriever import retrieve_document_chunks
from app.services.vector_store import index_document_pages_to_weaviate


def _get_llm() -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    if not model:
        raise RuntimeError("OPENAI_MODEL is not set")
    return ChatOpenAI(model=model, api_key=api_key, temperature=0)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int | None, int | None]] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        key = (it.get("page_number"), it.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _build_context(chunks: list[dict[str, Any]], max_context_chars: int) -> str:
    chunks = sorted(
        chunks,
        key=lambda x: (x.get("similarity") is not None, x.get("similarity") or 0.0),
        reverse=True,
    )

    lines: list[str] = []
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
        total += extra

        if total >= max_context_chars:
            break

    return "\n".join(lines)


def _extract_json_candidate(text: str) -> str | None:
    if not text:
        return None
    s = text.strip()

    if s.startswith("{") and s.endswith("}"):
        return s

    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1].strip()

    return None


def _build_repair_prompt(raw: str) -> str:
    raw_short = (raw or "").strip()
    if len(raw_short) > 3000:
        raw_short = raw_short[:3000] + "\n...[truncated]..."

    return f"""
You returned an invalid response.

Return JSON ONLY (no markdown, no extra keys), matching exactly:

{{
  "answer": "string",
  "citations": [{{"page_number": 1, "chunk_index": 1}}]
}}

Hard rules:
- citations can be [] only if answer is exactly: "Insufficient evidence."
- Do not invent citations.

Invalid response to fix:
{raw_short}
""".strip()


def parse_llm_structured_answer_with_repair(llm: ChatOpenAI, raw: str) -> tuple[LLMStructuredAnswer, list[str]]:
    warnings: list[str] = []

    candidate = _extract_json_candidate(raw) or (raw or "")
    try:
        payload = json.loads(candidate)
        parsed = LLMStructuredAnswer.model_validate(payload)
        return parsed, warnings
    except Exception:
        repair_prompt = _build_repair_prompt(raw)
        repaired = llm.invoke(repair_prompt).content

        candidate2 = _extract_json_candidate(repaired) or (repaired or "")
        payload2 = json.loads(candidate2)
        parsed2 = LLMStructuredAnswer.model_validate(payload2)

        warnings.append("Model output was invalid; auto-repaired to valid JSON.")
        return parsed2, warnings


def _tokenize(s: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in (s or ""))
    return {t for t in cleaned.split() if len(t) >= 3}


def _infer_decision(answer: str) -> str | None:
    a = (answer or "").lower()
    if "approved" in a:
        return "approved"
    if "denied" in a:
        return "denied"
    if "pending" in a or "in review" in a:
        return "pending"
    return None


def _verify_groundedness(
    *,
    answer: str,
    question: str,
    citations: list[Citation],
    retrieved_chunks: list[dict[str, Any]],
    allow_insufficient: bool,
) -> VerificationResult:
    """
    Groundedness verifier:
    1) basic checks (answer non-empty, citations present unless Insufficient evidence.)
    2) citations must exist in retrieved chunks
    3) cheap content checks against cited text
    """
    issues: list[str] = []
    a = (answer or "").strip()
    q = (question or "").strip().lower()

    if not a:
        issues.append("Empty answer")

    if a == "Insufficient evidence.":
        if not allow_insufficient:
            issues.append("Answer was 'Insufficient evidence.' but allow_insufficient=false (eval mode).")
            return VerificationResult(ok=False, issues=issues)
        return VerificationResult(ok=not issues, issues=issues)

    if not citations:
        issues.append("Missing citations for a non-empty answer.")

    retrieved_map: dict[tuple[int, int], dict[str, Any]] = {}
    for ch in retrieved_chunks:
        pn = ch.get("page_number")
        ci = ch.get("chunk_index")
        if pn is None or ci is None:
            continue
        retrieved_map[(int(pn), int(ci))] = ch

    cited_texts: list[str] = []
    missing: list[str] = []

    for c in citations:
        if c.page_number is None or c.chunk_index is None:
            continue
        key = (int(c.page_number), int(c.chunk_index))
        hit = retrieved_map.get(key)
        if not hit:
            missing.append(f"(page={c.page_number}, chunk={c.chunk_index})")
            continue
        cited_texts.append(hit.get("text") or "")

    if missing:
        issues.append(f"Citations not present in retrieved context: {', '.join(missing)}")

    cited_blob = "\n".join(cited_texts).lower()

    # Trigger groundedness checks if either the QUESTION or the ANSWER suggests it.
    answer_lc = a.lower()

    wants_decision = (
            any(k in q for k in ["decision", "approved", "denied", "pending"])
            or any(k in answer_lc for k in ["approved", "denied", "pending"])
    )

    wants_rationale = (
            any(k in q for k in ["rationale", "reason", "why"])
            or any(k in answer_lc for k in ["rationale", "reason", "because"])
    )

    if wants_decision:
        decision = _infer_decision(a)
        if decision and decision not in cited_blob:
            issues.append(f"Decision '{decision}' not found in cited evidence text.")

    if wants_rationale:
        # Cheap overlap check (avoid being too strict)
        answer_tokens = _tokenize(a)
        weak_stop = {
            "patient",
            "meets",
            "clinical",
            "coverage",
            "criteria",
            "failed",
            "standard",
            "therapies",
            "approved",
            "denied",
            "pending",
            "decision",
            "rationale",
            "reason",
        }
        answer_tokens = {t for t in answer_tokens if t not in weak_stop}

        cited_tokens = _tokenize(cited_blob)
        hits = len(answer_tokens.intersection(cited_tokens))

        # heuristic thresholds
        if answer_tokens and hits < 1:
            issues.append("Rationale does not appear to be supported by cited evidence (no keyword overlap).")

    return VerificationResult(ok=not issues, issues=issues)


@dataclass(frozen=True)
class Planner:
    def plan(self, question: str) -> AgenticQAPlan:
        steps = [
            PlanStep(name="main", query=question),
            PlanStep(name="dates", query="service date admission date authorization period date"),
            PlanStep(name="ids", query="patient name patient id member id subscriber id member group dob date of birth"),
            PlanStep(name="decision", query="decision approved denied pending in review rationale reason"),
        ]
        return AgenticQAPlan(strategy="multi_query", steps=steps)


class AgenticQAService:
    def __init__(self) -> None:
        self.llm = _get_llm()
        self.planner = Planner()
        self.steps: list[WorkflowStep] = []

    def _step(self, name: str, **meta: Any) -> None:
        self.steps.append(WorkflowStep(name=name, meta=meta))

    def _auto_index_if_missing(self, db: Session, document_id: str) -> int:
        if is_document_indexed(document_id):
            return 0

        doc = db.get(Document, document_id)
        if doc is None:
            raise RuntimeError("Document not found")

        pages = (
            db.query(DocumentPage)
            .filter(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number.asc())
            .all()
        )
        if not pages:
            raise RuntimeError("Document has no parsed pages. Run /documents/{document_id}/process first.")

        return index_document_pages_to_weaviate(
            document_id=document_id,
            filename=doc.filename,
            content_type=doc.content_type,
            pages=pages,
        )



    def answer(self, req: AgenticQARequest) -> AgenticQAResponse:
        warnings: list[str] = []
        self._step("plan:start", document_id=req.document_id, top_k=req.top_k, retries=req.retries)

        db = next(get_db())
        chunks_indexed = 0
        try:
            self._step("tool:auto_index_if_missing")
            chunks_indexed = self._auto_index_if_missing(db, req.document_id)
            self._step("tool:auto_index_if_missing:done", chunks_indexed=chunks_indexed)
        finally:
            db.close()

        if chunks_indexed > 0:
            warnings.append(f"Auto-index executed: {chunks_indexed} chunks indexed for this document.")

        plan = self.planner.plan(req.question)
        self._step("plan:done", strategy=plan.strategy, steps=len(plan.steps))

        attempt = 0
        top_k = req.top_k
        last_resp: AgenticQAResponse | None = None

        while attempt <= req.retries:
            self._step("retrieve:start", attempt=attempt, top_k=top_k)

            retrieved_raw: list[dict[str, Any]] = []
            for step in plan.steps:
                if not step.query:
                    continue
                retrieved_raw.extend(
                    retrieve_document_chunks(document_id=req.document_id, query=step.query, top_k=top_k)
                )

            retrieved_raw = _dedupe(retrieved_raw)
            self._step("retrieve:done", attempt=attempt, chunks=len(retrieved_raw))

            context = _build_context(retrieved_raw, max_context_chars=req.max_context_chars)

            prompt = (
                "Return JSON ONLY (no markdown, no commentary) with exactly these keys:\n"
                '{ "answer": "string", "citations": [{"page_number": 1, "chunk_index": 1}] }\n\n'
                "Rules:\n"
                "- Use ONLY the provided context.\n"
                '- If context is insufficient, set answer exactly to: "Insufficient evidence." and citations to [].\n'
                "- Otherwise, citations must include the sources you used.\n"
                "- Do not invent.\n\n"
                f"Question:\n{req.question}\n\n"
                f"Context:\n{context}\n"
            )

            self._step("llm:invoke", attempt=attempt, context_chars=len(context))
            raw = self.llm.invoke(prompt).content

            self._step("llm:parse", attempt=attempt)
            structured, parse_warnings = parse_llm_structured_answer_with_repair(self.llm, raw)
            warnings.extend(parse_warnings)

            sim_map: dict[tuple[int, int], float | None] = {}
            for ch in retrieved_raw:
                pn = ch.get("page_number")
                ci = ch.get("chunk_index")
                if pn is None or ci is None:
                    continue
                sim_map[(int(pn), int(ci))] = ch.get("similarity")

            citations = [
                Citation(
                    document_id=req.document_id,
                    page_number=c.page_number,
                    chunk_index=c.chunk_index,
                    similarity=sim_map.get((int(c.page_number), int(c.chunk_index))),
                )
                for c in structured.citations
            ]

            verification = _verify_groundedness(
                answer=structured.answer,
                question=req.question,
                citations=citations,
                retrieved_chunks=retrieved_raw,
                allow_insufficient=req.allow_insufficient,
            )
            self._step("verify", attempt=attempt, ok=verification.ok, issues=len(verification.issues))

            resp = AgenticQAResponse(
                document_id=req.document_id,
                question=req.question,
                answer=structured.answer,
                citations=citations,
                verification=verification,
                retrieved=[
                    RetrievedChunk(
                        document_id=it.get("document_id") or req.document_id,
                        page_number=it.get("page_number"),
                        chunk_index=it.get("chunk_index"),
                        text=it.get("text") or "",
                        similarity=it.get("similarity"),
                    )
                    for it in retrieved_raw[: min(len(retrieved_raw), 12)]
                ],
                plan=plan,
                steps=self.steps,
                warnings=warnings,
            )

            last_resp = resp
            if verification.ok:
                self._step("done", attempt=attempt)
                return resp

            top_k = min(top_k * 2, 30)
            self._step("retry", next_top_k=top_k)
            attempt += 1

        self._step("done", attempt=attempt, result="return_last_failed")
        return last_resp or AgenticQAResponse(
            document_id=req.document_id,
            question=req.question,
            answer="Insufficient evidence.",
            citations=[],
            verification=VerificationResult(ok=False, issues=["Unknown failure"]),
            retrieved=[],
            plan=plan,
            steps=self.steps,
            warnings=warnings,
        )

def verify_groundedness_for_test(
    *,
    answer: str,
    question: str,
    citations: list[Citation],
    retrieved_chunks: list[dict[str, Any]],
    allow_insufficient: bool = True,
) -> VerificationResult:
    return _verify_groundedness(
        answer=answer,
        question=question,
        citations=citations,
        retrieved_chunks=retrieved_chunks,
        allow_insufficient=allow_insufficient,
    )