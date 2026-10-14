"""The demo firm every visitor gets: Parkside Accounting (all names fictional)."""
from app.schemas import ChangeProposal

FIRM_NAME = "Parkside Accounting"
OWNER_KEY = "elena"
ADMIN_ROLE = "partner"  # V0: partners manage the firm's rules


def _p(key, name, title):
    return {"op": "add_person", "key": key, "name": name, "title": title,
            "email": f"{key}@parkside.example"}


def _e(key, type_, name, data=None):
    op = {"op": "add_entity", "key": key, "type": type_, "name": name}
    if data:
        op["data"] = data
    return op


def _r(s, rel, o):
    return {"op": "relate", "subject": s, "relation": rel, "object": o}


def _doc(key, name, kind, cs, amount=None):
    data = {"kind": kind, "filename": f"{key}.pdf", "mime": "application/pdf"}
    if amount is not None:
        data["amount"] = amount
    return [_e(key, "document", name, data), _r(key, "belongs_to", cs)]


def _cs(key, name, client, service):
    return [_e(key, "client_service", name), _r(key, "of_client", client), _r(key, "of_service", service)]


def _rule(key, text, definition):
    return {"op": "set_rule", "key": key, "text": text, "definition": definition}


DEMO_FIRM = ChangeProposal.model_validate({
    "summary": f"Set up {FIRM_NAME}",
    "operations": [
        _e("partner", "role", "Partner"),
        _e("accountant", "role", "Accountant"),
        _e("client", "role", "Client"),
        _e("tax_prep", "service", "Tax Preparation"),
        _e("payroll", "service", "Payroll"),
        _e("bookkeeping", "service", "Bookkeeping"),
        _e("acme", "client", "Acme Corp"),
        _e("globex", "client", "Globex Inc"),
        _e("bluebird", "client", "Bluebird Bakery"),
        *_cs("acme_tax", "Acme – Tax Preparation", "acme", "tax_prep"),
        *_cs("acme_payroll", "Acme – Payroll", "acme", "payroll"),
        *_cs("globex_books", "Globex – Bookkeeping", "globex", "bookkeeping"),
        *_cs("bluebird_books", "Bluebird – Bookkeeping", "bluebird", "bookkeeping"),
        *_cs("bluebird_tax", "Bluebird – Tax Preparation", "bluebird", "tax_prep"),
        *_doc("acme_tax_return", "Acme 2025 Tax Return", "tax_return", "acme_tax", 7200),
        *_doc("acme_w2", "Acme W-2 Summary", "w2", "acme_payroll"),
        *_doc("acme_payroll_report", "Acme Q3 Payroll Report", "payroll_report", "acme_payroll"),
        *_doc("globex_statement", "Globex Financial Statement", "financial_statement", "globex_books"),
        *_doc("globex_invoice", "Globex Bookkeeping Invoice", "invoice", "globex_books", 1850),
        *_doc("bluebird_ledger", "Bluebird General Ledger", "financial_statement", "bluebird_books"),
        *_doc("bluebird_tax_return", "Bluebird 2025 Tax Return", "tax_return", "bluebird_tax", 3400),
        _p("elena", "Elena Park", "Managing Partner"),
        _p("sarah", "Sarah Chen", "Accountant"),
        _p("john", "John Okafor", "Accountant"),
        _p("mike", "Mike Russo", "Accountant"),
        _p("dana", "Dana Whitfield", "CFO, Acme Corp"),
        _p("leo", "Leo Martins", "Owner, Bluebird Bakery"),
        _r("elena", "member_of", "partner"),
        _r("sarah", "member_of", "accountant"),
        _r("john", "member_of", "accountant"),
        _r("mike", "member_of", "accountant"),
        _r("dana", "member_of", "client"),
        _r("leo", "member_of", "client"),
        _r("dana", "client_contact", "acme"),
        _r("leo", "client_contact", "bluebird"),
        _r("john", "assigned_to", "acme_tax"),
        _r("mike", "assigned_to", "acme_payroll"),
        _r("john", "assigned_to", "globex_books"),
        _r("sarah", "assigned_to", "bluebird_books"),
        _r("sarah", "assigned_to", "bluebird_tax"),
        _rule("partners_all", "Partners can see and do everything.",
              {"type": "access", "role": "partner", "actions": ["*"], "scope": "all"}),
        _rule("accountants_assigned",
              "Accountants can only access documents for the client services they're assigned to.",
              {"type": "access", "role": "accountant", "actions": ["read", "edit"], "scope": "assigned"}),
        _rule("clients_own", "Clients can only see their own documents.",
              {"type": "access", "role": "client", "actions": ["read"], "scope": "own_client"}),
        _rule("only_partners_share", "Only partners can share documents outside the firm.",
              {"type": "restriction", "action": "share", "roles": ["partner"]}),
        _rule("tax_return_approval", "Tax returns over $5,000 need partner approval before they're sent.",
              {"type": "approval", "doc_kind": "tax_return", "min_amount": 5000, "approver_role": "partner"}),
    ],
})

SUGGESTIONS = [
    "Mike is no longer handling Acme's payroll. Sarah will handle it.",
    "Sarah is now a partner.",
    "Accountants can send tax returns up to $10,000 without approval.",
    "We hired Priya Nair as an accountant. She'll work on Globex's bookkeeping with John.",
    "Mike has left the firm.",
    "Who can see Acme's W-2?",
]
