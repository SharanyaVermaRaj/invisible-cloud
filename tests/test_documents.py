"""The document vault and the approval workflow."""
import pytest

from app.changes import apply_proposal
from app.documents import Forbidden, decide_delivery, get_file, send_document, upload_document
from tests.conftest import EXEMPTION, HANDOVER, proposal


def test_seed_documents_have_real_files(session, firm):
    blob = get_file(session, firm, "john", "acme_tax_return")
    assert blob.content.startswith(b"%PDF")


def test_reading_a_file_is_enforced(session, firm):
    with pytest.raises(Forbidden, match="No rule gives access"):
        get_file(session, firm, "mike", "acme_tax_return")


def test_access_to_files_follows_reassignment(session, firm):
    get_file(session, firm, "mike", "acme_w2")
    apply_proposal(session, firm, HANDOVER)
    with pytest.raises(Forbidden):
        get_file(session, firm, "mike", "acme_w2")
    assert get_file(session, firm, "sarah", "acme_w2")


def test_large_tax_return_needs_partner_approval(session, firm):
    d = send_document(session, firm, "john", "acme_tax_return")
    assert d.status == "pending" and d.approver_role == "partner"
    with pytest.raises(Forbidden, match="Only a partner"):
        decide_delivery(session, firm, "sarah", d.id, True)
    d = decide_delivery(session, firm, "elena", d.id, True)
    assert d.status == "sent" and d.decided_by == "elena"


def test_small_tax_return_sends_directly(session, firm):
    assert send_document(session, firm, "sarah", "bluebird_tax_return").status == "sent"


def test_partners_send_without_approval(session, firm):
    assert send_document(session, firm, "elena", "acme_tax_return").status == "sent"


def test_cannot_send_without_edit(session, firm):
    with pytest.raises(Forbidden, match="requires edit access"):
        send_document(session, firm, "dana", "acme_tax_return")


def test_no_duplicate_pending_requests(session, firm):
    send_document(session, firm, "john", "acme_tax_return")
    with pytest.raises(Exception, match="already waiting"):
        send_document(session, firm, "john", "acme_tax_return")


def test_exemption_changes_approval_behaviour(session, firm):
    apply_proposal(session, firm, proposal(
        "Accountants can send tax returns up to $5,000 without approval.",
        {"op": "set_rule", "key": "ex", "text": "x",
         "definition": {"type": "exemption", "role": "accountant", "doc_kind": "tax_return", "max_amount": 5000}},
    ))
    assert send_document(session, firm, "john", "acme_tax_return").status == "pending"  # $7,200 > $5,000


def test_rejecting_a_request(session, firm):
    d = send_document(session, firm, "john", "acme_tax_return")
    assert decide_delivery(session, firm, "elena", d.id, False, "Fix line 12").status == "rejected"


def test_upload_is_a_logged_change_and_inherits_rules(session, firm):
    key, change = upload_document(session, firm, "mike", title="Acme Q4 Payroll", client_service="acme_payroll",
                                  kind="payroll_report", amount=None, filename="q4.pdf",
                                  mime="application/pdf", content=b"%PDF-1.4 test")
    assert change.summary.startswith("Upload")
    assert get_file(session, firm, "mike", key).content == b"%PDF-1.4 test"
    assert get_file(session, firm, "dana", key)
    with pytest.raises(Forbidden):
        get_file(session, firm, "john", key)


def test_upload_requires_assignment(session, firm):
    with pytest.raises(Forbidden, match="Only partners or people assigned"):
        upload_document(session, firm, "john", title="x", client_service="acme_payroll", kind="other",
                        amount=None, filename="x.pdf", mime="application/pdf", content=b"x")


def test_upload_rejects_bad_types(session, firm):
    with pytest.raises(Exception, match="file type"):
        upload_document(session, firm, "elena", title="x", client_service="acme_payroll", kind="other",
                        amount=None, filename="x.exe", mime="application/x-msdownload", content=b"MZ")


def test_tax_return_without_amount_needs_approval(session, firm):
    key, _ = upload_document(session, firm, "john", title="Acme extension", client_service="acme_tax",
                             kind="tax_return", amount=None, filename="x.pdf", mime="application/pdf",
                             content=b"%PDF x")
    assert send_document(session, firm, "john", key).status == "pending"
