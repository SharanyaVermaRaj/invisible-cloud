"""Generate the fictional sample PDFs used by the demo firm.

Run once:  python scripts/make_sample_docs.py
Output goes to app/seed_files/ and is committed, so the app never needs reportlab at runtime.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "app" / "seed_files"
INK = colors.HexColor("#1B1E24")
MUTED = colors.HexColor("#6B7280")
ACCENT = colors.HexColor("#2F5D50")
RULE = colors.HexColor("#E5E2DA")

DOCS = {
    "acme_tax_return": {
        "title": "Form 1120 Summary: 2025 Corporate Tax Return",
        "client": "Acme Corp", "service": "Tax Preparation", "preparer": "John Okafor",
        "rows": [("Gross receipts", "$2,410,000"), ("Cost of goods sold", "($1,386,500)"),
                 ("Deductions", "($612,300)"), ("Taxable income", "$411,200"),
                 ("Total tax", "$86,352"), ("Estimated payments", "($79,152)"),
                 ("Balance due", "$7,200")],
        "note": "Balance due $7,200. Requires partner sign-off before delivery to client.",
    },
    "acme_w2": {
        "title": "W-2 Summary: Tax Year 2025",
        "client": "Acme Corp", "service": "Payroll", "preparer": "Mike Russo",
        "rows": [("Employees", "42"), ("Wages, tips, other comp.", "$3,118,400"),
                 ("Federal income tax withheld", "$498,944"), ("Social Security wages", "$2,981,000"),
                 ("Medicare wages", "$3,118,400"), ("State wages (CA)", "$3,118,400")],
        "note": "Individual W-2s issued to employees on January 24.",
    },
    "acme_payroll_report": {
        "title": "Payroll Report: Q3 2025",
        "client": "Acme Corp", "service": "Payroll", "preparer": "Mike Russo",
        "rows": [("Pay periods", "6"), ("Gross payroll", "$812,650"), ("Employer taxes", "$62,168"),
                 ("Benefits", "$71,400"), ("Net pay disbursed", "$579,310"),
                 ("Headcount change", "+3")],
        "note": "All filings for the quarter submitted on time.",
    },
    "globex_statement": {
        "title": "Financial Statement: Year Ended Dec 31, 2025",
        "client": "Globex Inc", "service": "Bookkeeping", "preparer": "John Okafor",
        "rows": [("Revenue", "$1,204,900"), ("Operating expenses", "($948,120)"),
                 ("Operating income", "$256,780"), ("Cash and equivalents", "$318,400"),
                 ("Accounts receivable", "$142,050"), ("Total liabilities", "$201,700")],
        "note": "Prepared from client-provided records. Unaudited.",
    },
    "globex_invoice": {
        "title": "Invoice #2025-118: Monthly Bookkeeping",
        "client": "Globex Inc", "service": "Bookkeeping", "preparer": "John Okafor",
        "rows": [("Monthly bookkeeping (Oct)", "$1,450"), ("Payroll reconciliation", "$250"),
                 ("Sales tax filing", "$150"), ("Total due", "$1,850")],
        "note": "Payment due within 30 days.",
    },
    "bluebird_ledger": {
        "title": "General Ledger: September 2025",
        "client": "Bluebird Bakery", "service": "Bookkeeping", "preparer": "Sarah Chen",
        "rows": [("Sales: storefront", "$48,210"), ("Sales: wholesale", "$21,940"),
                 ("Ingredients", "($19,880)"), ("Wages", "($24,600)"), ("Rent", "($6,500)"),
                 ("Net income", "$19,170")],
        "note": "Reconciled to bank statements.",
    },
    "bluebird_tax_return": {
        "title": "Schedule C Summary: 2025 Tax Return",
        "client": "Bluebird Bakery", "service": "Tax Preparation", "preparer": "Sarah Chen",
        "rows": [("Gross receipts", "$812,300"), ("Total expenses", "($701,450)"),
                 ("Net profit", "$110,850"), ("Estimated payments", "($27,600)"),
                 ("Balance due", "$3,400")],
        "note": "Balance due $3,400.",
    },
}


def render(key: str, d: dict) -> None:
    path = OUT / f"{key}.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setTitle(d["title"])
    c.setAuthor("Parkside Accounting (fictional)")

    c.setFillColor(ACCENT)
    c.rect(0, h - 0.18 * inch, w, 0.18 * inch, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(inch, h - 0.8 * inch, "PARKSIDE ACCOUNTING")
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawRightString(w - inch, h - 0.8 * inch, "SAMPLE DOCUMENT: FICTIONAL DATA")

    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(inch, h - 1.5 * inch, d["title"])
    c.setFont("Helvetica", 10)
    c.setFillColor(MUTED)
    meta = f"Client: {d['client']}     Service: {d['service']}     Prepared by: {d['preparer']}"
    c.drawString(inch, h - 1.8 * inch, meta)

    y = h - 2.5 * inch
    c.setStrokeColor(RULE)
    for label, value in d["rows"]:
        c.setFillColor(INK)
        c.setFont("Helvetica", 11)
        c.drawString(inch, y, label)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(w - inch, y, value)
        c.line(inch, y - 0.14 * inch, w - inch, y - 0.14 * inch)
        y -= 0.42 * inch

    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(MUTED)
    c.drawString(inch, y - 0.2 * inch, d["note"])

    c.setFont("Helvetica", 8)
    c.drawString(inch, 0.7 * inch, "Generated for the Invisible Cloud demo. All names and figures are fictional.")
    c.showPage()
    c.save()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for key, d in DOCS.items():
        render(key, d)
    print(f"wrote {len(DOCS)} files to {OUT}")
