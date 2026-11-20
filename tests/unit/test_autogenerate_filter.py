"""Alembic's name filter keeps the checkpoint tables and other schemas out (AC10)."""

import pytest

from app.db.autogenerate import CHECKPOINT_TABLES, include_name


def test_default_schema_is_included() -> None:
    assert include_name(None, "schema", {})


@pytest.mark.parametrize("schema", ["langgraph", "public", "other"])
def test_other_schemas_are_excluded(schema: str) -> None:
    assert not include_name(schema, "schema", {})


def test_the_four_checkpoint_tables_are_listed() -> None:
    assert CHECKPOINT_TABLES == {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }


@pytest.mark.parametrize("table", sorted(CHECKPOINT_TABLES))
def test_checkpoint_tables_are_excluded(table: str) -> None:
    assert not include_name(table, "table", {"schema_name": None})


@pytest.mark.parametrize("table", ["users", "alembic_version", "checkpoint"])
def test_ordinary_tables_are_included(table: str) -> None:
    assert include_name(table, "table", {"schema_name": None})


def test_columns_are_included() -> None:
    assert include_name("id", "column", {"table_name": "users"})
