"""add geom to periods and model_runs

Revision ID: c4325049ffb1
Revises: 0001_initial_schema
Create Date: 2026-11-25 14:19:23.248482

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4325049ffb1'
down_revision: Union[str, Sequence[str], None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "model_runs",
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
    )
    op.add_column(
        "periods",
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_periods_geom", table_name="periods", postgresql_using="gist")
    op.drop_column("periods", "geom")
    op.drop_index(
        "idx_model_runs_geom", table_name="model_runs", postgresql_using="gist"
    )
    op.drop_column("model_runs", "geom")
