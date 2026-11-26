from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from pydantic import ValidationError

from skyhaler_processing import sentinel1
from skyhaler_processing.config import DEFAULT_CONFIG_PATH, Config, load_config


@pytest.fixture
def config() -> Config:
    return load_config(dotenv_path=None)


def _with_s1(tmp_path: Path, **changes: Any) -> Config:
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["sentinel1"].update(changes)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_config(path, dotenv_path=None)


def test_real_config_has_sentinel1_settings(config: Config) -> None:
    s1 = config.sentinel1
    assert s1.instrument_mode == "IW"
    assert s1.orbit_pass in {"ASCENDING", "DESCENDING", "BOTH"}
    assert s1.noise_floor_db < 0


@pytest.mark.parametrize(
    "change",
    [
        {"orbit_pass": "SIDEWAYS"},
        {"instrument_mode": "SM"},
        {"noise_floor_db": 5.0},
        {"polarisations": ["VV", "VV"]},
    ],
)
def test_invalid_sentinel1_settings_are_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _with_s1(tmp_path, **change)


def test_names_and_plan_follow_the_season(config: Config) -> None:
    assert sentinel1.composite_name(date(2025, 7, 1), date(2025, 7, 10), "dekad") == (
        "s1_2025_dekad_0701_0710"
    )
    plan = sentinel1.planned_exports(config)
    assert len(plan) == 9
    assert plan[0][2] == "s1_2025_dekad_0701_0710"
    assert plan[-1][2] == "s1_2025_dekad_0921_0930"


def test_output_bands_include_ratio_only_with_both_polarisations() -> None:
    assert sentinel1.output_bands(["VV", "VH"]) == ["VV", "VH", "VH_VV", "n_obs"]
    assert sentinel1.output_bands(["VV"]) == ["VV", "n_obs"]
    assert sentinel1.output_bands(["HH", "HV"]) == ["HH", "HV", "n_obs"]


def test_sar_collection_filters_mode_polarisations_and_pass(config: Config) -> None:
    ee = MagicMock()
    sentinel1.sar_collection(ee, config, MagicMock(), date(2025, 7, 1), date(2025, 7, 10))

    ee.ImageCollection.assert_called_once_with("COPERNICUS/S1_GRD")
    collection = ee.ImageCollection.return_value
    collection.filterBounds.return_value.filterDate.assert_called_once_with(
        "2025-07-01",
        "2025-07-11",  # end date is exclusive in Earth Engine
    )
    ee.Filter.eq.assert_any_call("instrumentMode", "IW")
    ee.Filter.eq.assert_any_call("orbitProperties_pass", config.sentinel1.orbit_pass)
    ee.Filter.listContains.assert_any_call("transmitterReceiverPolarisation", "VV")
    ee.Filter.listContains.assert_any_call("transmitterReceiverPolarisation", "VH")


def test_both_orbit_passes_skip_the_pass_filter(tmp_path: Path) -> None:
    config = _with_s1(tmp_path, orbit_pass="BOTH")
    ee = MagicMock()
    sentinel1.sar_collection(ee, config, MagicMock(), date(2025, 7, 1), date(2025, 7, 10))
    assert all(call.args[0] != "orbitProperties_pass" for call in ee.Filter.eq.call_args_list)


def test_build_composite_adds_ratio_observations_and_metadata(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenes = MagicMock()
    monkeypatch.setattr(sentinel1, "sar_collection", lambda *args: scenes)
    ee = MagicMock()
    aoi = MagicMock()

    sentinel1.build_composite(ee, config, aoi, date(2025, 7, 1), date(2025, 7, 10))

    backscatter = scenes.median.return_value
    # VH - VV, renamed to VH_VV
    backscatter.select.assert_any_call("VH")
    backscatter.select.assert_any_call("VV")
    ratio = backscatter.select.return_value.subtract.return_value.rename
    ratio.assert_called_once_with("VH_VV")
    # observation counter from the first polarisation; gaps are 0, not masked
    scenes.select.assert_called_once_with("VV")
    scenes.select.return_value.count.return_value.unmask.assert_called_once_with(0)
    scenes.select.return_value.count.return_value.unmask.return_value.rename.assert_called_once_with(
        "n_obs"
    )
    # float32, clipped to the AOI, with the period metadata attached
    with_ratio = backscatter.addBands.return_value
    final = with_ratio.addBands.return_value.toFloat.return_value.clip
    final.assert_called_once_with(aoi)
    properties = final.return_value.set.call_args.args[0]
    assert properties["period_start"] == "2025-07-01"
    assert properties["period_end"] == "2025-07-10"
    assert properties["instrument_mode"] == "IW"
    assert properties["orbit_pass"] == config.sentinel1.orbit_pass
    assert properties["noise_floor_db"] == config.sentinel1.noise_floor_db


def test_build_composite_without_ratio_for_cross_pol_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_s1(tmp_path, polarisations=["VV"])
    scenes = MagicMock()
    monkeypatch.setattr(sentinel1, "sar_collection", lambda *args: scenes)

    sentinel1.build_composite(MagicMock(), config, MagicMock(), date(2025, 7, 1), date(2025, 7, 10))

    # no VH - VV band: the median goes straight into the observation-counter addBands
    scenes.median.return_value.addBands.assert_called_once()
    assert scenes.median.return_value.addBands.call_args.args[0] is (
        scenes.select.return_value.count.return_value.unmask.return_value.rename.return_value
    )


# ------------------------------------------------------------------------------- scripts

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_script(name: str) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_dry_run_lists_s1_windows(capsys: pytest.CaptureFixture[str]) -> None:
    script = _load_script("export_s1_composites")
    assert script.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "s1_2025_dekad_0701_0710" in out
    assert "s1_2025_dekad_0921_0930" in out
    assert "VH_VV" in out
    assert "Dry-run" in out


def test_export_unknown_period_fails(capsys: pytest.CaptureFixture[str]) -> None:
    script = _load_script("export_s1_composites")
    assert script.main(["--dry-run", "--period", "2025-07-02"]) == 1
    assert "Nicio fereastră" in capsys.readouterr().err


def test_quicklook_html_is_romanian_and_credits_copernicus() -> None:
    script = _load_script("quicklook_s1")
    rows = [
        {
            "name": "s1_2025_dekad_0701_0710",
            "start": "2025-07-01",
            "end": "2025-07-10",
            "n_scenes": 2,
            "gap_fraction": 0.0,
            "mean_obs": 2.0,
            "files": {"vv": "a_vv.png", "vh": "a_vh.png", "nobs": "a_nobs.png"},
        }
    ]
    page = script.render_html(rows, 2025, "DESCENDING")
    assert 'lang="ro"' in page
    assert "a_vv.png" in page and "a_nobs.png" in page
    assert "Copernicus Sentinel-1" in page
    assert "DESCENDING" in page
