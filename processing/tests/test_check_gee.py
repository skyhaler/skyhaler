"""Tests for scripts/check_gee.py that do not need Earth Engine or network access."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_gee.py"


@pytest.fixture(scope="module")
def check_gee() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_gee", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Please authorize access to your Earth Engine account by running\n\n"
            "earthengine authenticate",
            "earthengine authenticate",
        ),
        ("invalid_grant: Bad Request", "earthengine authenticate"),
        (
            "Caller does not have required permission to use project skyhaler. Grant the caller "
            "the roles/serviceusage.serviceUsageConsumer role",
            "Service Usage Consumer",
        ),
        ("Permission denied on resource project skyhaler.", "Earth Engine Resource Writer"),
        ("Project 'projects/skyhalr' not found or deleted.", "GEE_PROJECT"),
        ("Not signed up for Earth Engine or project is not registered.", "GEE_PROJECT"),
        ("something else entirely", "Eroare neașteptată"),
    ],
)
def test_explain_error(check_gee: ModuleType, message: str, expected: str) -> None:
    assert expected in check_gee.explain_error(message, "skyhaler")


def test_main_fails_cleanly_without_project(
    check_gee: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pytest.importorskip("ee")
    real_load = check_gee.load_config
    monkeypatch.delenv("GEE_PROJECT", raising=False)
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_KEY", raising=False)
    monkeypatch.setattr(check_gee, "load_config", lambda: real_load(dotenv_path=None))
    assert check_gee.main() == 1
    assert "GEE_PROJECT" in capsys.readouterr().err
