"""Create the internal admin V1 schema.

Revision ID: 20260710_0001
Revises: None
"""

from alembic import op

from app.admin.db import Base
from app.admin import models  # noqa: F401


revision = "20260710_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
