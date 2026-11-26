"""Processing configuration: one source of truth for study area, periods and parameters.

Non-secret parameters live in ``processing/config.yaml`` (tracked in git). Secrets and
per-person values (``GEE_PROJECT``, ``GEE_SERVICE_ACCOUNT_KEY``) are read from the environment,
optionally populated from the repo-root ``.env`` file.
"""

from __future__ import annotations

import calendar
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROCESSING_DIR: Path = Path(__file__).resolve().parent.parent
REPO_ROOT: Path = PROCESSING_DIR.parent
DEFAULT_CONFIG_PATH: Path = PROCESSING_DIR / "config.yaml"
DEFAULT_DOTENV_PATH: Path = REPO_ROOT / ".env"

ENV_GEE_PROJECT = "GEE_PROJECT"
ENV_GEE_SERVICE_ACCOUNT_KEY = "GEE_SERVICE_ACCOUNT_KEY"

EpsgCode = Annotated[str, Field(pattern=r"^EPSG:\d+$")]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
Sentinel2Index = Literal["NDVI", "NDRE", "NDMI", "MNDWI", "BSI"]

# Earth Engine asset folder below projects/<GEE_PROJECT>/assets/, e.g. "composites" or "a/b".
ASSET_FOLDER_PATTERN = r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$"


class GeeConfigError(RuntimeError):
    """Raised when Google Earth Engine credentials are required but not configured."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AoiConfig(_Section):
    file: Path
    buffer_m: float = Field(ge=0.0)

    @field_validator("file")
    @classmethod
    def _resolve_and_check_exists(cls, value: Path) -> Path:
        path = value.expanduser()
        if not path.is_absolute():
            path = PROCESSING_DIR / path
        path = path.resolve()
        if not path.is_file():
            raise ValueError(f"AOI file not found: {path}")
        return path


class SeasonConfig(_Section):
    year: int = Field(ge=2015, le=2100)
    start: str = Field(pattern=r"^\d{2}-\d{2}$", description="MM-DD")
    end: str = Field(pattern=r"^\d{2}-\d{2}$", description="MM-DD, inclusive")
    composite: Literal["dekad", "month"] = Field(
        description="calendar composite windows: dekad (1-10, 11-20, 21-end) or month"
    )

    @model_validator(mode="after")
    def _check_dates(self) -> SeasonConfig:
        start = self._to_date(self.start, "start")
        end = self._to_date(self.end, "end")
        if start >= end:
            raise ValueError(f"season start ({start}) must be before season end ({end})")
        return self

    def _to_date(self, month_day: str, field: str) -> date:
        month, day = (int(part) for part in month_day.split("-"))
        try:
            return date(self.year, month, day)
        except ValueError as exc:
            raise ValueError(
                f"season {field} '{month_day}' is not a valid date in {self.year}"
            ) from exc

    @property
    def start_date(self) -> date:
        return self._to_date(self.start, "start")

    @property
    def end_date(self) -> date:
        return self._to_date(self.end, "end")


class CrsConfig(_Section):
    storage: EpsgCode
    metric: EpsgCode


class Sentinel2Config(_Section):
    collection: str = Field(min_length=1)
    cloud_score_collection: str = Field(min_length=1)
    cloud_score_band: str = Field(min_length=1)
    cloud_score_threshold: UnitInterval
    indices: list[Sentinel2Index] = Field(min_length=1)

    @field_validator("indices")
    @classmethod
    def _check_unique_indices(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError(f"indices must not contain duplicates, got {value}")
        return value


class Sentinel1Config(_Section):
    collection: str = Field(min_length=1)
    polarisations: list[Literal["VV", "VH", "HH", "HV"]] = Field(min_length=1)
    instrument_mode: Literal["IW", "EW"]
    orbit_pass: Literal["ASCENDING", "DESCENDING", "BOTH"]
    noise_floor_db: float = Field(le=0.0, description="backscatter (dB) below this is masked")

    @field_validator("polarisations")
    @classmethod
    def _unique_polarisations(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError(f"polarisations must be unique, got {value}")
        return value


class Sentinel5pConfig(_Section):
    collection: str = Field(min_length=1)
    qa_min: UnitInterval
    normalise_percentiles: tuple[float, float]

    @field_validator("normalise_percentiles")
    @classmethod
    def _check_percentiles(cls, value: tuple[float, float]) -> tuple[float, float]:
        low, high = value
        if not (0.0 <= low < high <= 100.0):
            raise ValueError(f"percentiles must be increasing and within [0, 100], got {value}")
        return value


class ExportConfig(_Section):
    destination: Literal["asset", "drive"] = Field(
        description="where composites are exported: a shared Earth Engine asset or Google Drive"
    )
    asset_folder: str = Field(
        pattern=ASSET_FOLDER_PATTERN,
        description="folder below projects/<GEE_PROJECT>/assets/ (destination: asset)",
    )
    drive_folder: str = Field(min_length=1, description="Drive folder name (destination: drive)")
    quicklook_dir: Path = Field(description="local output folder of the visual check (git-ignored)")

    @field_validator("quicklook_dir")
    @classmethod
    def _resolve_against_processing_dir(cls, value: Path) -> Path:
        path = value.expanduser()
        if not path.is_absolute():
            path = PROCESSING_DIR / path
        return path.resolve()


class RiskConfig(_Section):
    k: float = Field(ge=0.0)
    thresholds: tuple[float, float] = Field(description="low/medium and medium/high class breaks")

    @field_validator("thresholds")
    @classmethod
    def _check_thresholds(cls, value: tuple[float, float]) -> tuple[float, float]:
        if any(not (0.0 < t < 1.0) for t in value):
            raise ValueError(f"thresholds must lie strictly inside (0, 1), got {value}")
        if any(a >= b for a, b in zip(value, value[1:])):
            raise ValueError(f"thresholds must be strictly increasing, got {value}")
        return value


class GeeCredentials(_Section):
    """Earth Engine settings read from the environment, never from config.yaml."""

    project: str | None = None
    service_account_key: Path | None = None


class Config(_Section):
    aoi: AoiConfig
    season: SeasonConfig
    crs: CrsConfig
    grid_resolution_m: float = Field(gt=0.0)
    sentinel2: Sentinel2Config
    sentinel1: Sentinel1Config
    sentinel5p: Sentinel5pConfig
    export: ExportConfig
    risk: RiskConfig
    gee: GeeCredentials = GeeCredentials()

    def periods(self) -> list[tuple[date, date]]:
        """Calendar composite windows covering the season, as inclusive (start, end) dates.

        ``dekad``: days 1-10, 11-20 and 21-last day of each month. ``month``: whole months.
        The first and last windows are clipped to the season start and end, so windows are
        contiguous, with no gaps or overlaps.
        """
        season_end = self.season.end_date
        windows: list[tuple[date, date]] = []
        current = self.season.start_date
        while current <= season_end:
            window_end = min(_calendar_window_end(current, self.season.composite), season_end)
            windows.append((current, window_end))
            current = window_end + timedelta(days=1)
        return windows

    def aoi_geojson(self) -> dict[str, Any]:
        """Parsed AOI GeoJSON (EPSG:4326)."""
        with self.aoi.file.open(encoding="utf-8") as fh:
            return json.load(fh)

    def require_gee(self) -> GeeCredentials:
        """Return GEE settings, raising a clear error if they are unusable.

        ``GEE_PROJECT`` is required. ``GEE_SERVICE_ACCOUNT_KEY`` is optional: when unset, Earth
        Engine uses personal credentials from ``earthengine authenticate``; when set, the key
        file must exist.
        """
        if not self.gee.project:
            raise GeeConfigError(
                f"Missing Earth Engine setting: {ENV_GEE_PROJECT}. "
                "Set it in the repo-root .env file (see .env.example) or in the environment."
            )
        key = self.gee.service_account_key
        if key is not None and not key.is_file():
            raise GeeConfigError(f"{ENV_GEE_SERVICE_ACCOUNT_KEY} points to a missing file: {key}")
        return self.gee


def _calendar_window_end(day: date, composite: str) -> date:
    """Last day of the calendar dekad or month that contains ``day``."""
    month_end = date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])
    if composite == "month" or day.day > 20:
        return month_end
    return day.replace(day=10 if day.day <= 10 else 20)


def _read_gee_from_env() -> GeeCredentials:
    project = os.environ.get(ENV_GEE_PROJECT, "").strip() or None
    key = os.environ.get(ENV_GEE_SERVICE_ACCOUNT_KEY, "").strip() or None
    key_path: Path | None = None
    if key is not None:
        key_path = Path(key).expanduser()
        if not key_path.is_absolute():
            key_path = REPO_ROOT / key_path
    return GeeCredentials(project=project, service_account_key=key_path)


def load_config(
    path: str | Path | None = None,
    dotenv_path: str | Path | None = DEFAULT_DOTENV_PATH,
) -> Config:
    """Load and validate the processing configuration.

    Args:
        path: YAML config file; defaults to ``processing/config.yaml``. Relative paths inside
            the file (e.g. the AOI) are resolved against the ``processing/`` folder.
        dotenv_path: ``.env`` file to load into the environment (existing variables win);
            defaults to the repo-root ``.env``. Pass ``None`` to skip loading it.

    Raises:
        FileNotFoundError: the config file does not exist.
        pydantic.ValidationError: the config content is invalid.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    if dotenv_path is not None:
        load_dotenv(dotenv_path, override=False)

    with config_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file must contain a mapping at top level: {config_path}")
    if "gee" in raw:
        raise ValueError("GEE settings must come from the environment, not from config.yaml")

    return Config.model_validate({**raw, "gee": _read_gee_from_env()})
