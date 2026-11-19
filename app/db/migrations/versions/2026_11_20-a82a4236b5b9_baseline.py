"""baseline: the start of the revision chain. No tables yet.

Revision ID: a82a4236b5b9
Revises:
Create Date: 2026-11-20 04:22:16.585732
"""

from collections.abc import Sequence

revision: str = "a82a4236b5b9"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
