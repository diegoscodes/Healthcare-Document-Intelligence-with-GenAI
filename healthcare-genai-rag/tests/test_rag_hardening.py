from __future__ import annotations

from app.services.rag_rules import extract_structured_from_context


def test_hardening_dates_and_period_and_unknown_ids() -> None:
    context = """
PRIOR AUTHORIZATION REQUEST (DATE VARIATION TEST)
Patient Name: Carlos Mendes
Member ID: PATIENT-55555
DOB: 12/07/1985
Service Date: March 15, 2026
Admission Date: 10-03-2026
Authorization Period: 15/03/2026 to 15/09/2026
Diagnosis: Hypertension
ICD-10 Codes: I10
Provider: Dr. João Pereira
Decision: Approved
Rationale: Patient meets criteria and requires continuous treatment.
""".strip()

    extracted = extract_structured_from_context(context)

    assert extracted.patient_id == "unknown"
    assert extracted.member_id == "PATIENT-55555"
    assert extracted.member_group == "unknown"

    assert extracted.dob == "1985-07-12"
    assert extracted.service_date == "2026-03-15"
    assert extracted.admission_date == "2026-03-10"
    assert extracted.authorization_period_start == "2026-03-15"
    assert extracted.authorization_period_end == "2026-09-15"

    assert extracted.decision == "approved"
    assert extracted.rationale == "Patient meets criteria and requires continuous treatment."


def test_month_name_date_normalizes_to_iso() -> None:
    context = """
Service Date: March 15, 2026
Decision: Approved
Rationale: OK
""".strip()

    extracted = extract_structured_from_context(context)

    assert extracted.service_date == "2026-03-15"
    assert extracted.decision == "approved"


def test_ireland_default_dd_mm_for_ambiguous_numeric_dates() -> None:
    context = """
DOB: 12/07/1985
Admission Date: 10-03-2026
Decision: Approved
Rationale: OK
""".strip()

    extracted = extract_structured_from_context(context)

    # Ireland/UK default: DD/MM
    assert extracted.dob == "1985-07-12"
    assert extracted.admission_date == "2026-03-10"
    assert extracted.decision == "approved"