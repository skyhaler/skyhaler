"""Tests for the Sentinel-2 composite helpers; no Earth Engine or network access needed."""

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from pydantic import ValidationError

from skyhaler_processing import sentinel2
from skyhaler_processing.config import (
    DEFAULT_CONFIG_PATH,
    ENV_GEE_PROJECT,
    ENV_GEE_SERVICE_ACCOUNT_KEY,
    Config,
    load_config,
)


class FakeEEException(Exception):
    """Stand-in for ee.EEException."""


def make_ee(existing_assets: set[str] | None = None) -> MagicMock:
    existing = existing_assets if existing_assets is not None else set()
    ee = MagicMock()
    ee.EEException = FakeEEException

    def get_asset(path: str) -> dict[str, str]:
        if path not in existing:
            raise FakeEEException(f"Asset '{path}' not found.")
        return {"name": path}

    ee.data.getAsset.side_effect = get_asset
    ee.data.createFolder.side_effect = lambda path: existing.add(path)
    return ee


@pytest.fixture(autouse=True)
def _clean_gee_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_GEE_PROJECT, raising=False)
    monkeypatch.delenv(ENV_GEE_SERVICE_ACCOUNT_KEY, raising=False)


@pytest.fixture
def config() -> Config:
    return load_config(dotenv_path=None)


@pytest.fixture
def base_raw() -> dict[str, Any]:
    with DEFAULT_CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_modified(tmp_path: Path, raw: dict[str, Any]) -> Config:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_config(path, dotenv_path=None)


# ------------------------------------------------------------------------------- config


def test_real_config_has_sentinel2_and_export_settings(config: Config) -> None:
    assert config.sentinel2.cloud_score_collection == "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
    assert config.sentinel2.cloud_score_band == "cs_cdf"
    assert config.sentinel2.cloud_score_threshold == 0.6
    assert config.sentinel2.indices == ["NDVI", "NDRE", "NDMI", "MNDWI", "BSI"]
    assert config.export.destination == "asset"
    assert config.export.asset_folder == "composites"
    assert config.export.quicklook_dir.is_absolute()
    assert config.export.quicklook_dir.name == "quicklook"


def test_configured_indices_are_all_supported(config: Config) -> None:
    assert set(config.sentinel2.indices) <= set(sentinel2.SUPPORTED_INDICES)


@pytest.mark.parametrize("indices", [["EVI"], [], ["NDVI", "NDVI"]])
def test_bad_indices_fail(tmp_path: Path, base_raw: dict[str, Any], indices: list[str]) -> None:
    base_raw["sentinel2"]["indices"] = indices
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


@pytest.mark.parametrize("destination", ["gcs", "", None])
def test_bad_export_destination_fails(
    tmp_path: Path, base_raw: dict[str, Any], destination: object
) -> None:
    base_raw["export"]["destination"] = destination
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


@pytest.mark.parametrize("folder", ["/composites", "composites/", "a//b", "has space", ""])
def test_bad_asset_folder_fails(tmp_path: Path, base_raw: dict[str, Any], folder: str) -> None:
    base_raw["export"]["asset_folder"] = folder
    with pytest.raises(ValidationError):
        _load_modified(tmp_path, base_raw)


def test_nested_asset_folder_is_accepted(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["export"]["asset_folder"] = "skyhaler/composites_2025"
    assert _load_modified(tmp_path, base_raw).export.asset_folder == "skyhaler/composites_2025"


# ------------------------------------------------------------------------- pure helpers


def test_composite_name() -> None:
    assert sentinel2.composite_name(date(2025, 7, 1), date(2025, 7, 10), "dekad") == (
        "s2_2025_dekad_0701_0710"
    )


def test_planned_exports_cover_every_period_with_unique_names(config: Config) -> None:
    plan = sentinel2.planned_exports(config)
    assert len(plan) == len(config.periods()) == 9
    assert [(start, end) for start, end, _ in plan] == config.periods()
    names = [name for _, _, name in plan]
    assert len(set(names)) == len(names)
    assert names[0] == "s2_2025_dekad_0701_0710"
    assert names[-1] == "s2_2025_dekad_0921_0930"


def test_asset_id() -> None:
    assert sentinel2.asset_id("skyhaler", "composites", "s2_2025_dekad_0701_0710") == (
        "projects/skyhaler/assets/composites/s2_2025_dekad_0701_0710"
    )


def test_snap_grid_is_anchored_at_multiples_of_resolution_and_covers_box() -> None:
    xmin, ymin, xmax, ymax = 399_987.3, 4_912_345.6, 420_012.4, 4_930_001.2
    grid = sentinel2.snap_grid("EPSG:32635", xmin, ymin, xmax, ymax, 10.0)
    res, _, x0, _, neg_res, y0 = grid.transform
    assert (res, neg_res) == (10.0, -10.0)
    assert x0 % 10 == 0 and y0 % 10 == 0
    assert x0 <= xmin and y0 >= ymax
    assert x0 + grid.width * res >= xmax
    assert y0 - grid.height * res <= ymin
    # tight: removing one row or column would no longer cover the box
    assert x0 + (grid.width - 1) * res < xmax
    assert y0 - (grid.height - 1) * res > ymin
    assert grid.crs == "EPSG:32635"


def test_snap_grid_exact_multiples_adds_no_extra_cells() -> None:
    grid = sentinel2.snap_grid("EPSG:32635", 400_000, 4_900_000, 400_100, 4_900_050, 10.0)
    assert (grid.width, grid.height) == (10, 5)
    assert grid.transform == [10.0, 0, 400_000, 0, -10.0, 4_900_050]


# ------------------------------------------------------------- Earth Engine call shapes


def test_apply_cloud_mask_uses_score_band_and_threshold() -> None:
    image = MagicMock()
    result = sentinel2.apply_cloud_mask(image, "cs_cdf", 0.6)
    image.select.assert_called_once_with("cs_cdf")
    image.select.return_value.gte.assert_called_once_with(0.6)
    image.updateMask.assert_called_once_with(image.select.return_value.gte.return_value)
    assert result is image.updateMask.return_value


def test_cloud_masked_collection_links_cloud_score_plus(config: Config) -> None:
    ee = make_ee()
    aoi = MagicMock()
    sentinel2.cloud_masked_collection(ee, config, aoi, date(2025, 7, 1), date(2025, 7, 10))

    loaded = [call.args[0] for call in ee.ImageCollection.call_args_list]
    assert loaded == [config.sentinel2.collection, config.sentinel2.cloud_score_collection]
    # filterDate end is exclusive: the window end date must be included
    for collection in (ee.ImageCollection.return_value.filterBounds.return_value,):
        collection.filterDate.assert_called_with("2025-07-01", "2025-07-11")
    images = ee.ImageCollection.return_value.filterBounds.return_value.filterDate.return_value
    images.linkCollection.assert_called_once()
    assert images.linkCollection.call_args.args[1] == [config.sentinel2.cloud_score_band]
    images.linkCollection.return_value.map.assert_called_once()


def test_add_indices_uses_expected_band_pairs() -> None:
    image = MagicMock()
    image.addBands.return_value = image
    sentinel2.add_indices(image, ["NDVI", "NDRE", "NDMI", "MNDWI"])
    pairs = [call.args[0] for call in image.normalizedDifference.call_args_list]
    assert pairs == [["B8", "B4"], ["B8", "B5"], ["B8", "B11"], ["B3", "B11"]]
    renamed = [
        call.args[0] for call in image.normalizedDifference.return_value.rename.call_args_list
    ]
    assert renamed == ["NDVI", "NDRE", "NDMI", "MNDWI"]
    assert image.addBands.call_count == 4


def test_add_indices_bsi_expression() -> None:
    image = MagicMock()
    image.addBands.return_value = image
    sentinel2.add_indices(image, ["BSI"])
    expression, bands = image.expression.call_args.args
    assert expression == sentinel2.BSI_EXPRESSION
    assert set(bands) == {"swir", "red", "nir", "blue"}
    selected = [call.args[0] for call in image.select.call_args_list]
    assert selected == ["B11", "B4", "B8", "B2"]


def test_bsi_expression_matches_definition() -> None:
    swir, red, nir, blue = 0.3, 0.2, 0.4, 0.05
    value = eval(  # noqa: S307 - fixed expression constant from our own module
        sentinel2.BSI_EXPRESSION, {}, {"swir": swir, "red": red, "nir": nir, "blue": blue}
    )
    assert value == pytest.approx(((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue)))


def test_add_indices_rejects_unknown_index() -> None:
    with pytest.raises(ValueError, match="Unsupported index 'EVI'"):
        sentinel2.add_indices(MagicMock(), ["EVI"])


# ------------------------------------------------------------------------------ assets


def test_asset_exists_true_false_and_other_errors() -> None:
    ee = make_ee({"projects/p/assets/x"})
    assert sentinel2.asset_exists(ee, "projects/p/assets/x") is True
    assert sentinel2.asset_exists(ee, "projects/p/assets/y") is False
    ee.data.getAsset.side_effect = FakeEEException("Permission denied on resource.")
    with pytest.raises(FakeEEException, match="Permission denied"):
        sentinel2.asset_exists(ee, "projects/p/assets/x")


def test_ensure_asset_folders_creates_missing_parents_in_order() -> None:
    ee = make_ee({"projects/p/assets/a"})
    sentinel2.ensure_asset_folders(ee, "p", "a/b/c")
    created = [call.args[0] for call in ee.data.createFolder.call_args_list]
    assert created == ["projects/p/assets/a/b", "projects/p/assets/a/b/c"]
    # second run is a no-op
    sentinel2.ensure_asset_folders(ee, "p", "a/b/c")
    assert ee.data.createFolder.call_count == 2


# ------------------------------------------------------------------------------ export


def _grid() -> sentinel2.Grid:
    return sentinel2.snap_grid("EPSG:32635", 400_000, 4_900_000, 400_100, 4_900_050, 10.0)


def test_start_export_to_asset(config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_GEE_PROJECT, "skyhaler")
    config = load_config(dotenv_path=None)
    ee, image, aoi = make_ee(), MagicMock(), MagicMock()
    task = sentinel2.start_export(ee, config, image, "s2_2025_dekad_0701_0710", aoi, _grid())

    kwargs = ee.batch.Export.image.toAsset.call_args.kwargs
    assert kwargs["image"] is image
    assert kwargs["assetId"] == "projects/skyhaler/assets/composites/s2_2025_dekad_0701_0710"
    assert kwargs["crs"] == "EPSG:32635"
    assert kwargs["crsTransform"] == [10.0, 0, 400_000, 0, -10.0, 4_900_050]
    assert kwargs["region"] is aoi
    ee.batch.Export.image.toDrive.assert_not_called()
    task = ee.batch.Export.image.toAsset.return_value
    task.start.assert_called_once()


def test_start_export_to_drive_fills_nodata(tmp_path: Path, base_raw: dict[str, Any]) -> None:
    base_raw["export"]["destination"] = "drive"
    config = _load_modified(tmp_path, base_raw)
    ee, image = make_ee(), MagicMock()
    sentinel2.start_export(ee, config, image, "s2_2025_dekad_0701_0710", MagicMock(), _grid())

    image.unmask.assert_called_once_with(sentinel2.NODATA)
    kwargs = ee.batch.Export.image.toDrive.call_args.kwargs
    assert kwargs["image"] is image.unmask.return_value
    assert kwargs["folder"] == config.export.drive_folder
    assert kwargs["fileNamePrefix"] == "s2_2025_dekad_0701_0710"
    assert kwargs["fileFormat"] == "GeoTIFF"
    ee.batch.Export.image.toAsset.assert_not_called()
    ee.batch.Export.image.toDrive.return_value.start.assert_called_once()


def test_composite_bands_are_documented_sentinel2_bands() -> None:
    assert sentinel2.REFLECTANCE_BANDS == [
        "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12",
    ]  # fmt: skip
    assert "B4" in sentinel2.REFLECTANCE_BANDS and "B8" in sentinel2.REFLECTANCE_BANDS


def test_observation_stats_reads_gap_fraction_and_mean_obs() -> None:
    ee = make_ee()
    composite = MagicMock()
    n_obs = composite.select.return_value
    reduce_region = n_obs.eq.return_value.rename.return_value.addBands.return_value.reduceRegion
    reduce_region.return_value.getInfo.return_value = {"gap_fraction": 0.125, "mean_obs": 3.0}

    stats = sentinel2.observation_stats(ee, composite, MagicMock())

    composite.select.assert_called_once_with(sentinel2.OBSERVATION_BAND)
    assert stats == {"gap_fraction": 0.125, "mean_obs": 3.0}


def test_observation_stats_handles_empty_result() -> None:
    ee = make_ee()
    composite = MagicMock()
    n_obs = composite.select.return_value
    reduce_region = n_obs.eq.return_value.rename.return_value.addBands.return_value.reduceRegion
    reduce_region.return_value.getInfo.return_value = {"gap_fraction": None}

    assert sentinel2.observation_stats(ee, composite, MagicMock()) == {
        "gap_fraction": 0.0,
        "mean_obs": 0.0,
    }


def test_utm_forward_matches_reference_values():
    # 45 N on the central meridian of zone 35 (27 E): E = 500000, N = 4982950.400 (EPSG:32635)
    easting, northing = sentinel2.utm_forward(27.0, 45.0, 35)
    assert easting == pytest.approx(500_000.0, abs=0.01)
    assert northing == pytest.approx(4_982_950.40, abs=0.05)


def test_grid_from_lonlat_is_metric_and_snapped():
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [[25.97, 44.33], [26.23, 44.33], [26.23, 44.54], [25.97, 44.54], [25.97, 44.33]]
        ],
    }
    grid = sentinel2.grid_from_lonlat("EPSG:32635", polygon, 10)
    _, _, x0, _, _, y0 = grid.transform
    assert 300_000 < x0 < 500_000 and 4_800_000 < y0 < 5_000_000  # metres, not degrees
    assert x0 % 10 == 0 and y0 % 10 == 0
    assert 20_000 < grid.width * 10 < 30_000 and 20_000 < grid.height * 10 < 30_000


def test_utm_zone_rejects_other_crs():
    assert sentinel2.utm_zone("EPSG:32635") == 35
    with pytest.raises(ValueError):
        sentinel2.utm_zone("EPSG:4326")
