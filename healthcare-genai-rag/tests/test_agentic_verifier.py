import pytest

from app.schemas.agentic_qa import Citation
from app.services.agentic_qa import verify_groundedness_for_test


DOC_ID = "<DOC_ID>"


def _chunks():
    return [
        {
            "document_id": DOC_ID,
            "page_number": 2,
            "chunk_index": 1,
            "text": "Decision: Approved\nRationale: Patient meets criteria.",
            "similarity": 0.6,
        },
        {
            "document_id": DOC_ID,
            "page_number": 3,
            "chunk_index": 1,
            "text": "Auditability: All approvals must be traceable to evidence.",
            "similarity": 0.55,
        },
    ]


def test_allows_insufficient_evidence_without_citations():
    res = verify_groundedness_for_test(
        answer="Insufficient evidence.",
        question="Confirm the decision is denied.",
        citations=[],
        retrieved_chunks=_chunks(),
    )
    assert res.ok is True
    assert res.issues == []


def test_disallows_insufficient_evidence_in_eval_mode():
    res = verify_groundedness_for_test(
        answer="Insufficient evidence.",
        question="Confirm the decision is denied.",
        citations=[],
        retrieved_chunks=_chunks(),
        allow_insufficient=False,
    )
    assert res.ok is False
    assert any("allow_insufficient=false" in msg for msg in res.issues)


def test_passes_when_decision_supported_by_cited_chunk():
    citations = [Citation(document_id=DOC_ID, page_number=2, chunk_index=1, similarity=0.6)]
    res = verify_groundedness_for_test(
        answer="Approved",
        question="Answer in one word only.",
        citations=citations,
        retrieved_chunks=_chunks(),
    )
    assert res.ok is True


def test_fails_when_denied_not_in_cited_evidence():
    citations = [Citation(document_id=DOC_ID, page_number=2, chunk_index=1, similarity=0.6)]
    res = verify_groundedness_for_test(
        answer="Denied",
        question="Answer in one word only.",
        citations=citations,
        retrieved_chunks=_chunks(),
    )
    assert res.ok is False
    assert any("decision" in msg.lower() and "denied" in msg.lower() for msg in res.issues)


def test_fails_when_citation_not_in_retrieved_context():
    citations = [Citation(document_id=DOC_ID, page_number=99, chunk_index=1, similarity=None)]
    res = verify_groundedness_for_test(
        answer="Approved",
        question="What is the decision?",
        citations=citations,
        retrieved_chunks=_chunks(),
    )
    assert res.ok is False
    assert any("retrieved context" in msg.lower() for msg in res.issues)


def test_traceable_not_treated_as_decision():
    citations = [Citation(document_id=DOC_ID, page_number=3, chunk_index=1, similarity=0.55)]
    res = verify_groundedness_for_test(
        answer="traceable",
        question="Answer in one word only. Cite evidence about approvals traceability.",
        citations=citations,
        retrieved_chunks=_chunks(),
    )
    assert res.ok is True
