"""The business stories from the problem statement, as executable tests."""
from sqlalchemy import select

from app.changes import apply_proposal, preview_proposal
from app.models import Change, Rule
from tests.conftest import HANDOVER, allowed, proposal


def test_accountants_only_see_assigned_client_services(session, firm):
    assert allowed(session, firm, "john", "read", "acme_tax_return")
    assert allowed(session, firm, "john", "read", "globex_statement")
    assert not allowed(session, firm, "john", "read", "acme_payroll_report")
    assert allowed(session, firm, "mike", "read", "acme_payroll_report")
    assert not allowed(session, firm, "mike", "read", "acme_tax_return")
    assert not allowed(session, firm, "sarah", "read", "acme_payroll_report")


def test_only_partners_share(session, firm):
    assert allowed(session, firm, "john", "edit", "acme_tax_return")
    assert not allowed(session, firm, "john", "share", "acme_tax_return")
    assert allowed(session, firm, "elena", "share", "acme_tax_return")


def test_partners_see_everything(session, firm):
    for doc in ["acme_tax_return", "acme_w2", "globex_statement", "bluebird_ledger"]:
        assert allowed(session, firm, "elena", "read", doc)


def test_clients_only_see_their_own_documents(session, firm):
    assert allowed(session, firm, "dana", "read", "acme_tax_return")
    assert allowed(session, firm, "dana", "read", "acme_w2")
    assert not allowed(session, firm, "dana", "edit", "acme_tax_return")
    assert not allowed(session, firm, "dana", "read", "globex_statement")
    assert allowed(session, firm, "leo", "read", "bluebird_ledger")
    assert not allowed(session, firm, "leo", "read", "acme_w2")


def test_send_requires_edit(session, firm):
    assert allowed(session, firm, "john", "send", "acme_tax_return")
    assert not allowed(session, firm, "dana", "send", "acme_tax_return")


def test_reassignment_moves_access(session, firm):
    apply_proposal(session, firm, HANDOVER)
    assert not allowed(session, firm, "mike", "read", "acme_payroll_report")
    assert not allowed(session, firm, "mike", "read", "acme_w2")
    assert allowed(session, firm, "sarah", "read", "acme_payroll_report")
    assert allowed(session, firm, "sarah", "edit", "acme_w2")


def test_preview_shows_exact_diff_and_changes_nothing(session, firm):
    diff = preview_proposal(session, firm, HANDOVER)
    lost = {(x["person"], x["action"], x["resource"]) for x in diff["lost"]}
    gained = {(x["person"], x["action"], x["resource"]) for x in diff["gained"]}
    docs = ("acme_payroll_report", "acme_w2")
    assert lost == {("mike", a, d) for a in ("read", "edit", "send") for d in docs}
    assert gained == {("sarah", a, d) for a in ("read", "edit", "send") for d in docs}
    assert diff["operations"] == ["Unassign Mike Russo from Acme – Payroll",
                                  "Assign Sarah Chen to Acme – Payroll"]
    assert diff["conflicts"] == []
    assert allowed(session, firm, "mike", "read", "acme_payroll_report")  # nothing applied


def test_promotion_to_partner(session, firm):
    apply_proposal(session, firm, proposal(
        "Sarah is now a partner.",
        {"op": "unrelate", "subject": "sarah", "relation": "member_of", "object": "accountant"},
        {"op": "relate", "subject": "sarah", "relation": "member_of", "object": "partner"},
    ))
    assert allowed(session, firm, "sarah", "share", "globex_statement")


def test_offboarding_removes_all_access(session, firm):
    diff = preview_proposal(session, firm, proposal("Mike has left the firm.",
                                                    {"op": "remove_person", "key": "mike"}))
    assert diff["operations"] == ["Remove Mike Russo from the firm (and 1 assignment)"]
    assert {x["person"] for x in diff["lost"]} == {"mike"}
    apply_proposal(session, firm, proposal("Mike has left the firm.", {"op": "remove_person", "key": "mike"}))
    assert not allowed(session, firm, "mike", "read", "acme_w2")


def test_new_hire_with_assignment(session, firm):
    apply_proposal(session, firm, proposal(
        "We hired Priya as an accountant on Globex bookkeeping.",
        {"op": "add_person", "key": "priya", "name": "Priya Nair", "title": "Accountant"},
        {"op": "relate", "subject": "priya", "relation": "member_of", "object": "accountant"},
        {"op": "relate", "subject": "priya", "relation": "assigned_to", "object": "globex_books"},
    ))
    assert allowed(session, firm, "priya", "read", "globex_statement")
    assert not allowed(session, firm, "priya", "read", "acme_w2")


def test_rule_edit_creates_new_version_and_applies_everywhere(session, firm):
    apply_proposal(session, firm, proposal(
        "Clients can also download (share) their documents.",
        {"op": "set_rule", "key": "clients_own", "text": "Clients can read and edit their own documents.",
         "definition": {"type": "access", "role": "client", "actions": ["read", "edit"], "scope": "own_client"}},
    ))
    versions = session.scalars(select(Rule).where(Rule.org_id == firm, Rule.key == "clients_own")).all()
    assert sorted((r.version, r.active) for r in versions) == [(1, False), (2, True)]
    assert allowed(session, firm, "dana", "edit", "acme_w2")


def test_every_change_is_logged(session, firm):
    apply_proposal(session, firm, HANDOVER, actor="elena")
    log = session.scalars(select(Change).where(Change.org_id == firm).order_by(Change.id)).all()
    assert [c.summary for c in log] == ["Set up Parkside Accounting", HANDOVER.summary]
    assert log[0].inverse is None          # the setup itself isn't undoable
    assert log[-1].inverse is not None


def test_new_client_service_on_the_fly(session, firm):
    apply_proposal(session, firm, proposal(
        "John will also handle Globex's tax preparation.",
        {"op": "add_entity", "key": "globex_tax", "type": "client_service", "name": "Globex – Tax Preparation"},
        {"op": "relate", "subject": "globex_tax", "relation": "of_client", "object": "globex"},
        {"op": "relate", "subject": "globex_tax", "relation": "of_service", "object": "tax_prep"},
        {"op": "relate", "subject": "john", "relation": "assigned_to", "object": "globex_tax"},
    ))
    from app.authz import CompanyGraph
    assert "globex_tax" in CompanyGraph(session, firm).objs("john", "assigned_to")
