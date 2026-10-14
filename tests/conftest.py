import os

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.authz import CompanyGraph
from app.db import Base, make_engine
from app.schemas import ChangeProposal
from app.workspaces import create_demo_workspace


@pytest.fixture
def engine():
    """In-memory SQLite by default. Set TEST_DATABASE_URL to run the suite against Postgres."""
    url = os.getenv("TEST_DATABASE_URL")
    eng = make_engine(url) if url else make_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


@pytest.fixture
def firm(session):
    """A fresh copy of the demo firm. Returns its org id."""
    return create_demo_workspace(session).id


def allowed(session, org, person, action, doc):
    return CompanyGraph(session, org).check(person, action, doc).allowed


def proposal(summary, *ops):
    return ChangeProposal.model_validate({"summary": summary, "operations": list(ops)})


HANDOVER = proposal(
    "Mike is no longer handling Acme's payroll. Sarah will handle it.",
    {"op": "unrelate", "subject": "mike", "relation": "assigned_to", "object": "acme_payroll"},
    {"op": "relate", "subject": "sarah", "relation": "assigned_to", "object": "acme_payroll"},
)

EXEMPTION = proposal(
    "Accountants can send tax returns up to $10,000 without approval.",
    {"op": "set_rule", "key": "accountant_tax_exemption",
     "text": "Accountants can send tax returns up to $10,000 without approval.",
     "definition": {"type": "exemption", "role": "accountant", "doc_kind": "tax_return", "max_amount": 10000}},
)

ACCOUNTANTS_SHARE = proposal(
    "Accountants can share documents for their assigned clients.",
    {"op": "set_rule", "key": "accountants_share",
     "text": "Accountants can share documents for their assigned clients.",
     "definition": {"type": "access", "role": "accountant", "actions": ["share"], "scope": "assigned"}},
)
