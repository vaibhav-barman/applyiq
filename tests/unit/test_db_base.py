"""Constraint names come from the naming convention (AC4). No database needed."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, MetaData, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import NAMING_CONVENTION, Base, TimestampMixin, UUIDPrimaryKeyMixin


class _TestBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class _Parent(UUIDPrimaryKeyMixin, TimestampMixin, _TestBase):
    __tablename__ = "parent"


class _Child(UUIDPrimaryKeyMixin, TimestampMixin, _TestBase):
    __tablename__ = "child"
    __table_args__ = (CheckConstraint("length(code) > 0", name="code_not_empty"),)

    code: Mapped[str] = mapped_column(String(20), unique=True)
    label: Mapped[str] = mapped_column(String(20), index=True)
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parent.id"))


def ddl(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


def test_base_uses_the_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_table_constraints_are_named_by_the_convention() -> None:
    table_ddl = ddl(CreateTable(_Child.__table__))  # type: ignore[arg-type]
    assert "CONSTRAINT pk_child PRIMARY KEY" in table_ddl
    assert "CONSTRAINT uq_child_code UNIQUE" in table_ddl
    assert "CONSTRAINT fk_child_parent_id_parent FOREIGN KEY" in table_ddl
    assert "CONSTRAINT ck_child_code_not_empty CHECK" in table_ddl


def test_index_is_named_by_the_convention() -> None:
    (index,) = _Child.__table__.indexes  # type: ignore[attr-defined]
    assert "CREATE INDEX ix_child_label" in ddl(CreateIndex(index))


def test_mixins_add_uuid_id_and_timezone_aware_timestamps() -> None:
    table_ddl = ddl(CreateTable(_Parent.__table__))  # type: ignore[arg-type]
    assert "id UUID NOT NULL" in table_ddl
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in table_ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in table_ddl
    assert _Parent.__table__.c.updated_at.onupdate is not None  # type: ignore[attr-defined]


def test_timestamp_mixin_turns_on_eager_defaults() -> None:
    # Without it, reading updated_at after an UPDATE raises MissingGreenlet under async.
    assert _Parent.__mapper__.eager_defaults is True
    assert _Child.__mapper__.eager_defaults is True
