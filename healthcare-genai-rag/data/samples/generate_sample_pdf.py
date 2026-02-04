from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def generate_prior_auth_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(output_path), pagesize=LETTER)
    width, height = LETTER

    y = height - 72
    line_height = 14

    def write_line(text: str) -> None:
        nonlocal y
        c.drawString(72, y, text)
        y -= line_height

    # Page 1
    c.setFont("Helvetica-Bold", 14)
    write_line("PRIOR AUTHORIZATION REQUEST (SAMPLE)")
    c.setFont("Helvetica", 10)
    write_line(f"Document Version: 1.0")
    write_line(f"Date: {date.today().isoformat()}")
    write_line("")

    c.setFont("Helvetica-Bold", 11)
    write_line("Patient & Plan (DE-IDENTIFIED)")
    c.setFont("Helvetica", 10)
    write_line("Patient ID: PATIENT-0001")
    write_line("Plan: Sample Health Plan PPO")
    write_line("Member Group: GRP-100")
    write_line("")

    c.setFont("Helvetica-Bold", 11)
    write_line("Medication Request")
    c.setFont("Helvetica", 10)
    write_line("Requested Drug: Examplemab 150 mg/mL injection (brand: EXAMPLEBIO)")
    write_line("NDC: 00000-0000-00")
    write_line("Dose/Frequency: 150 mg SC every 4 weeks")
    write_line("Quantity: 1 syringe per 28 days")
    write_line("Route: Subcutaneous")
    write_line("Site of Care: Outpatient")
    write_line("")

    c.setFont("Helvetica-Bold", 11)
    write_line("Clinical Information")
    c.setFont("Helvetica", 10)
    write_line("Diagnosis: Condition X (ICD-10: X00.0)")
    write_line("Previous therapies tried: Therapy A (failed), Therapy B (intolerant)")
    write_line("Baseline labs: Provided (see attached)")
    write_line("Provider Attestation: Patient meets criteria as documented.")
    write_line("")

    c.setFont("Helvetica-Bold", 11)
    write_line("Coverage Criteria (SAMPLE)")
    c.setFont("Helvetica", 10)
    write_line("Eligibility requirements:")
    write_line("- Age >= 18 years")
    write_line("- Confirmed diagnosis of Condition X")
    write_line("- Documentation of inadequate response to at least 1 standard therapy")
    write_line("")
    write_line("Approval rules:")
    write_line("- Initial approval: 6 months")
    write_line("- Renewal requires evidence of clinical benefit and adherence")
    write_line("- Quantity limit: 1 per 28 days")
    write_line("")
    write_line("Administrative notes:")
    write_line("- Step therapy may apply")
    write_line("- Prior authorization required")
    write_line("- Specialty pharmacy only")
    write_line("")

    c.showPage()

    # Page 2
    y = height - 72
    c.setFont("Helvetica-Bold", 12)
    write_line("PHARMACY AGREEMENT (SAMPLE EXCERPT)")
    c.setFont("Helvetica", 10)
    write_line("This sample excerpt simulates terms commonly found in pharmacy agreements.")
    write_line("")
    write_line("Dispensing pharmacy: Sample Specialty Pharmacy")
    write_line("Shipping: Temperature-controlled packaging required")
    write_line("Refills: Not automatic; provider confirmation required for renewals")
    write_line("")
    write_line("Auditability:")
    write_line("- All approvals must reference evidence in submitted documentation.")
    write_line("- Decisions must be reproducible and logged.")
    write_line("")
    write_line("Signatures: (sample)")
    write_line("Provider Name: SAMPLE PROVIDER")
    write_line("Signature Date: ____________________")
    write_line("")

    c.save()


if __name__ == "__main__":
    out = Path(__file__).parent / "sample_prior_authorization.pdf"
    generate_prior_auth_pdf(out)
    print(f"Generated: {out}")