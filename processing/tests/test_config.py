from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from skyhaler_processing.config import (
    DEFAULT_CONFIG_PATH,
    ENV_GEE_PROJECT,
    ENV_GEE_SERVICE_ACCOUNT_KEY,
    Config,
    GeeConfigError,
    load_config,
)


@pytest.fixture(autouse=True)
def _clean_gee_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_GEE_PROJECT, raising=False)
    monkeypatch.delenv(ENV_GEE_SERVICE_ACCOUNT_KEY, raising=False)


@pytest.fixture
def base_raw() -> dict[str, Any]:
    with DEFAULT_CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_modified(tmp_path: Path, raw: dict[str, Any]) -> Config:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_config(path, dotenv_path=None)


def test_real_config_loads() -> None:
    config = load_config(dotenv_path=None)
    assert config.aoi.file.is_file()
    assert config.crs.storage == "EPSG:4326"
    assert config.crs.metric == "EPSG:32635"
    assert config.risk.thresholds == (0.33, 0.66)
    assert config.sentinel1.polarisations == ["VV", "VH"]


def test_load_is_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config(dotenv_path=None).aoi.file.is_file()


def test_default_periods() -> None:
    config = load_config(dotenv_path=None)
    periods = config.periods()
    # 1 Jul - 30 Sep 2025 = 92 days -> 9 full 10-day windows + one 2-day window.
    assert len(periods) == 10
    assert periods[0] == (date(2025, 7, 1), date(2025, 7, 10))
    assert periods[-1] == (date(2025, 9, 29), date(2025, 9, 30))
    assert periods[-1][1] == config.season.end_date


def test_periods_are_contiguous_and_cover_season() -> None:
    config = load_config(dotenv_path=None)
    periods = config.periods()
    assert periods[0][0] == config.season.start_date
    assert periods[-1][1] == config.season.end_date
    for (_, prev_end), (next_start, _) in zip(periods, periods[1:]):
        assert (next_start - prev_end).days == 1


def test_aoi_geojson_is_bucharest_polygon() -> None:
    geojson = load_config(dotenv_path=None).aoi_geojson()
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["geometry"]["type"] in {"Polygon", "MultiPolygon"}


def test_reversed_season_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["season"]["start"], base_raw["season"]["end"] = "09-30", "07-01"
    with pytest.raises(ValidationError, match="before season end"):
        _load_modified(tmp_path, base_raw)


def test_invalid_season_date_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["season"]["end"] = "02-30"
    with pytest.raises(ValidationError, match="not a valid date"):
        _load_modified(tmp_path, base_raw)


def test_zero_composite_days_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["season"]["composite_days"] = 0
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


def test_negative_k_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["risk"]["k"] = -0.1
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


@pytest.mark.parametrize("thresholds", [[0.66, 0.33], [0.5, 0.5]])
def test_unsorted_thresholds_fail(
    tmp_path: Path, base_raw: dict[str, Any], thresholds: list[float]
) -> None:
    base_raw["risk"]["thresholds"] = thresholds
    with pytest.raises(ValidationError, match="strictly increasing"):
        _load_modified(tmp_path, base_raw)


@pytest.mark.parametrize("thresholds", [[0.0, 0.5], [0.5, 1.0]])
def test_thresholds_outside_unit_interval_fail(
    tmp_path: Path, base_raw: dict[str, Any], thresholds: list[float]
) -> None:
    base_raw["risk"]["thresholds"] = thresholds
    with pytest.raises(ValidationError, match=r"inside \(0, 1\)"):
        _load_modified(tmp_path, base_raw)


def test_qa_min_out_of_range_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["sentinel5p"]["qa_min"] = 1.5
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


@pytest.mark.parametrize("percentiles", [[95, 5], [-1, 95], [5, 101]])
def test_bad_percentiles_fail(
    tmp_path: Path, base_raw: dict[str, Any], percentiles: list[float]
) -> None:
    base_raw["sentinel5p"]["normalise_percentiles"] = percentiles
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


@pytest.mark.parametrize("crs", ["4326", "EPSG:", "epsg:4326", "EPSG:43a6"])
def test_bad_crs_fails(tmp_path: Path, base_raw: dict[str, Any], crs: str) -> None:
    base_raw["crs"]["metric"] = crs
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


def test_missing_aoi_file_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["aoi"]["file"] = str(tmp_path / "does_not_exist.geojson")
    with pytest.raises(ValidationError, match="AOI file not found"):
        _load_modified(tmp_path, base_raw)


def test_unknown_key_fails(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["risk"]["kk"] = 1.0
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


def test_gee_in_yaml_is_rejected(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["gee"] = {"project": "should-not-be-here"}
    with pytest.raises(ValueError, match="environment"):
        _load_modified(tmp_path, base_raw)


def test_missing_config_file_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml", dotenv_path=None)


def test_gee_optional_at_load_time() -> None:
    config = load_config(dotenv_path=None)
    assert config.gee.project is None
    assert config.gee.service_account_key is None


def test_require_gee_raises_when_env_missing() -> None:
    config = load_config(dotenv_path=None)
    with pytest.raises(GeeConfigError, match=f"{ENV_GEE_PROJECT}.*{ENV_GEE_SERVICE_ACCOUNT_KEY}"):
        config.require_gee()


def test_require_gee_raises_when_one_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_GEE_PROJECT, "test-project")
    config = load_config(dotenv_path=None)
    with pytest.raises(GeeConfigError, match=ENV_GEE_SERVICE_ACCOUNT_KEY):
        config.require_gee()


def test_require_gee_returns_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(ENV_GEE_PROJECT, "test-project")
    monkeypatch.setenv(ENV_GEE_SERVICE_ACCOUNT_KEY, str(key))
    gee = load_config(dotenv_path=None).require_gee()
    assert gee.project == "test-project"
    assert gee.service_account_key == key


def test_env_values_loaded_from_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{ENV_GEE_PROJECT}=from-dotenv\n", encoding="utf-8")
    config = load_config(dotenv_path=dotenv)
    assert config.gee.project == "from-dotenv"
