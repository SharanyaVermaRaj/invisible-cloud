"""The company model: the single source of truth for how a business operates.

People, entities, relationships and rules are never edited directly.
Every change goes through app.changes.apply_proposal, which validates it,
checks it for conflicts and records it (with its inverse) in `changes`.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("org_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))       # stable handle, e.g. "sarah"
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), default="")
    title: Mapped[str] = mapped_column(String(200), default="")


class Entity(Base):
    """Anything that isn't a person: roles, clients, services, client services, documents."""
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("org_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # documents: kind, amount, file info


class Relationship(Base):
    """Zanzibar-style tuple: subject --relation--> object (both are keys)."""
    __tablename__ = "relationships"
    __table_args__ = (UniqueConstraint("org_id", "subject", "relation", "object"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    subject: Mapped[str] = mapped_column(String(64))
    relation: Mapped[str] = mapped_column(String(32))
    object: Mapped[str] = mapped_column(String(64))


class Rule(Base):
    """A typed business rule. Editing creates a new version; old versions stay (active=False)."""
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(String(1000))   # the owner's words
    definition: Mapped[dict] = mapped_column(JSON)    # the compiled, typed form
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Change(Base):
    """Append-only log of every applied change: the version history of the business."""
    __tablename__ = "changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(500))
    proposal: Mapped[dict] = mapped_column(JSON)
    diff: Mapped[dict] = mapped_column(JSON)
    inverse: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ops that undo this change
    reverts: Mapped[int | None] = mapped_column(Integer, nullable=True)      # change this one undid
    reverted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # change that undid this one
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FileBlob(Base):
    """The bytes of an uploaded document. Kept even if the document is removed, so undo restores it."""
    __tablename__ = "file_blobs"
    __table_args__ = (UniqueConstraint("org_id", "document_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_key: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    content: Mapped[bytes] = mapped_column(LargeBinary)


class Delivery(Base):
    """A request to send a document to its client, with its approval status."""
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_key: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # pending | sent | rejected
    approval_rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approver_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiCall(Base):
    """One row per AI request, used for rate limiting."""
    __tablename__ = "ai_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


ORG_TABLES = [Delivery, FileBlob, Change, Rule, Relationship, Entity, Person]
