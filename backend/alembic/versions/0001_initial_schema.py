"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-25 00:00:00.000000

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    op.create_table(
        "periods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "model_runs",
        sa.Column("version", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("k", sa.Float(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )

    op.create_table(
        "risk_cells",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("ambrosia_score", sa.Float(), nullable=False),
        sa.Column("no2_normalized", sa.Float(), nullable=False),
        sa.Column("risk_value", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["model_version"], ["model_runs.version"]),
        sa.ForeignKeyConstraint(["period_id"], ["periods.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_cells_model_version"),
        "risk_cells",
        ["model_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_risk_cells_period_id"),
        "risk_cells",
        ["period_id"],
        unique=False,
    )

    op.create_table(
        "no2_cells",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("no2_mol_m2", sa.Float(), nullable=False),
        sa.Column("no2_normalized", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["period_id"], ["periods.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_no2_cells_period_id"),
        "no2_cells",
        ["period_id"],
        unique=False,
    )

    op.create_table(
        "training_polygons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("source_image", sa.String(), nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("labelled_by", sa.String(), nullable=False),
        sa.Column("split", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "validation_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=True),
        sa.Column("coord_uncertainty_m", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_index("idx_sectors_geom", table_name="sectors", postgresql_using="gist")
    op.drop_table("sectors")

    op.drop_index(
        "idx_validation_points_geom",
        table_name="validation_points",
        postgresql_using="gist",
    )
    op.drop_table("validation_points")

    op.drop_index(
        "idx_training_polygons_geom",
        table_name="training_polygons",
        postgresql_using="gist",
    )
    op.drop_table("training_polygons")

    op.drop_index(op.f("ix_no2_cells_period_id"), table_name="no2_cells")
    op.drop_index(
        "idx_no2_cells_geom", table_name="no2_cells", postgresql_using="gist"
    )
    op.drop_table("no2_cells")

    op.drop_index(op.f("ix_risk_cells_period_id"), table_name="risk_cells")
    op.drop_index(op.f("ix_risk_cells_model_version"), table_name="risk_cells")
    op.drop_index(
        "idx_risk_cells_geom", table_name="risk_cells", postgresql_using="gist"
    )
    op.drop_table("risk_cells")

    op.drop_table("model_runs")
    op.drop_table("periods")
