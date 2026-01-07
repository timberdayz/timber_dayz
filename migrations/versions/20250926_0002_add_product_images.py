"""add product images to dim_products

Revision ID: 20250926_0002
Revises: 20250925_0001
Create Date: 2025-09-26 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20250926_0002"
down_revision: Union[str, None] = "20250925_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("dim_products") as batch_op:
        batch_op.add_column(sa.Column("image_url", sa.String(length=1024), nullable=True))
        batch_op.add_column(sa.Column("image_path", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("image_last_fetched_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("dim_products") as batch_op:
        batch_op.drop_column("image_last_fetched_at")
        batch_op.drop_column("image_path")
        batch_op.drop_column("image_url")

