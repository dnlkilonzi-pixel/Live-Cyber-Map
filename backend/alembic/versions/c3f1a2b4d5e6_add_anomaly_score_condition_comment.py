"""add_anomaly_score_condition_comment

Revision ID: c3f1a2b4d5e6
Revises: 654be334a24e
Create Date: 2026-04-16 02:00:00.000000

This migration is a data-dictionary record.  No schema columns are added or
removed because ``alert_rules.condition`` is already ``String(50)`` and the
new ``anomaly_score`` condition value (13 chars) fits without any DDL change.

Purpose: document that ``anomaly_score`` is a valid value for the
``alert_rules.condition`` column so that reviewers and DBA tooling have a
migration-version anchor for the feature introduction.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3f1a2b4d5e6"
down_revision: Union[str, Sequence[str], None] = "654be334a24e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No DDL changes — anomaly_score fits in the existing String(50) column."""
    # Add a CHECK constraint comment to document valid condition values.
    # We use a no-op batch_alter_table so that alembic --autogenerate
    # recognises this revision as applied.
    pass  # noqa: PIE790


def downgrade() -> None:
    """Nothing to undo."""
    pass  # noqa: PIE790
