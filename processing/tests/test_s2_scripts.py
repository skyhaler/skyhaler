"""Tests for the Sentinel-2 export and quick-look scripts that need no Earth Engine access."""

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def export_script() -> ModuleType:
    return _load("export_s2_composites")


@pytest.fixture(scope="module")
def quicklook_script() -> ModuleType:
    return _load("quicklook_s2")


PLAN = [
    (date(2025, 7, 1), date(2025, 7, 10), "s2_2025_dekad_0701_0710"),
    (date(2025, 7, 11), date(2025, 7, 20), "s2_2025_dekad_0711_0720"),
]


def test_select_plan_all_and_single(export_script: ModuleType) -> None:
    assert export_script.select_plan(PLAN, None) == PLAN
    assert export_script.select_plan(PLAN, "2025-07-11") == [PLAN[1]]


def test_select_plan_unknown_period_lists_options(export_script: ModuleType) -> None:
    with pytest.raises(ValueError, match="2025-07-01, 2025-07-11"):
        export_script.select_plan(PLAN, "2025-08-01")


def test_dry_run_needs_no_earth_engine(
    export_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert export_script.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "s2_2025_dekad_0701_0710" in out
    assert "s2_2025_dekad_0921_0930" in out
    assert "Cloud Score+" in out
    assert "Dry-run" in out


def test_dry_run_single_period(
    export_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert export_script.main(["--dry-run", "--period", "2025-08-11"]) == 0
    out = capsys.readouterr().out
    assert "s2_2025_dekad_0811_0820" in out
    assert "s2_2025_dekad_0701_0710" not in out


def test_unknown_period_exits_with_error(
    export_script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert export_script.main(["--dry-run", "--period", "2030-01-01"]) == 1
    assert "Nicio fereastră" in capsys.readouterr().err


def test_render_html_contains_rows_credit_and_escapes(quicklook_script: ModuleType) -> None:
    rows = [
        {
            "name": "s2_2025_dekad_0701_0710",
            "start": "2025-07-01",
            "end": "2025-07-10",
            "n_scenes": 12,
            "gap_fraction": 0.034,
            "mean_obs": 2.5,
            "files": {"rgb": "a_rgb.png", "ndvi": "a_ndvi.png", "nobs": "a<b>_nobs.png"},
        }
    ]
    page = quicklook_script.render_html(rows, 2025, 0.6)
    assert '<html lang="ro">' in page
    assert "2025-07-01 – 2025-07-10" in page
    assert "Fără observații valide: 3.4%" in page
    assert "Scene în fereastră: 12" in page
    assert "Copernicus Sentinel" in page and "Cloud Score+" in page
    assert "a<b>_nobs.png" not in page and "a&lt;b&gt;_nobs.png" in page


def test_render_html_without_ndvi_shows_dash(quicklook_script: ModuleType) -> None:
    rows = [
        {
            "name": "n",
            "start": "2025-07-01",
            "end": "2025-07-10",
            "n_scenes": 1,
            "gap_fraction": 0.0,
            "mean_obs": 1.0,
            "files": {"rgb": "n_rgb.png", "nobs": "n_nobs.png"},
        }
    ]
    assert "<td>–</td>" in quicklook_script.render_html(rows, 2025, 0.6)
