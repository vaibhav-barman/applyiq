"""What Alembic's autogenerate may look at. Outside env.py so it can be imported and tested."""

from alembic.runtime.environment import NameFilterParentNames, NameFilterType

# The tables `langgraph-checkpoint-postgres` creates for itself (3.2.1). They live in the
# `langgraph` schema; Alembic must never create, alter or drop them.
CHECKPOINT_TABLES: frozenset[str] = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)


def include_name(
    name: str | None, type_: NameFilterType, parent_names: NameFilterParentNames
) -> bool:
    """Reflect only the default schema (`None`), and never the checkpoint tables."""
    if type_ == "schema":
        return name is None
    if type_ == "table":
        return name not in CHECKPOINT_TABLES
    return True
