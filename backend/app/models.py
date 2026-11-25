from datetime import date, datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    risk_cells: Mapped[list["RiskCell"]] = relationship(back_populates="period")
    no2_cells: Mapped[list["No2Cell"]] = relationship(back_populates="period")


class ModelRun(Base):
    __tablename__ = "model_runs"

    version: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    k: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    risk_cells: Mapped[list["RiskCell"]] = relationship(back_populates="model_run")


class RiskCell(Base):
    __tablename__ = "risk_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("periods.id"), index=True, nullable=False
    )
    ambrosia_score: Mapped[float] = mapped_column(Float, nullable=False)
    no2_normalized: Mapped[float] = mapped_column(Float, nullable=False)
    risk_value: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(
        String, ForeignKey("model_runs.version"), index=True, nullable=False
    )

    period: Mapped["Period"] = relationship(back_populates="risk_cells")
    model_run: Mapped["ModelRun"] = relationship(back_populates="risk_cells")


class No2Cell(Base):
    __tablename__ = "no2_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("periods.id"), index=True, nullable=False
    )
    no2_mol_m2: Mapped[float] = mapped_column(Float, nullable=False)
    no2_normalized: Mapped[float] = mapped_column(Float, nullable=False)

    period: Mapped["Period"] = relationship(back_populates="no2_cells")


class TrainingPolygon(Base):
    __tablename__ = "training_polygons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    source_image: Mapped[str] = mapped_column(String, nullable=False)
    acquired_on: Mapped[date] = mapped_column(Date, nullable=False)
    labelled_by: Mapped[str] = mapped_column(String, nullable=False)
    split: Mapped[str] = mapped_column(String, nullable=False)


class ValidationPoint(Base):
    __tablename__ = "validation_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    observed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    coord_uncertainty_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )
