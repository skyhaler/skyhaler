"""Check that Google Earth Engine access works for the configured project.

Loads processing/config.yaml, initialises Earth Engine with GEE_PROJECT and counts the
Sentinel-2 SR harmonized images over the AOI for the configured season.

Usage (from processing/, after `pip install -e ".[gee]"` and `earthengine authenticate`):

    python scripts/check_gee.py

Exit code 0 on success, 1 on any error. Output is in Romanian (project rule).
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any

from skyhaler_processing.config import (
    ENV_GEE_PROJECT,
    ENV_GEE_SERVICE_ACCOUNT_KEY,
    Config,
    GeeConfigError,
    load_config,
)

SOURCE_CREDIT = "Sursa datelor: Copernicus Sentinel-2 (ESA), prin Google Earth Engine."

ROLES_HINT = (
    "Cere administratorului proiectului rolurile IAM 'Earth Engine Resource Writer' și "
    "'Service Usage Consumer' pentru contul tău Google (vezi processing/README.md)."
)


def explain_error(message: str, project: str) -> str:
    """Translate an Earth Engine / Google API error message into a Romanian fix-it hint."""
    text = message.lower()
    if "serviceusage" in text:
        return f"Lipsește rolul 'Service Usage Consumer' pe proiectul '{project}'. {ROLES_HINT}"
    if any(
        s in text
        for s in ("not found", "not registered", "not signed up", "has not been used", "disabled")
    ):
        return (
            f"Proiectul '{project}' nu există, nu este înregistrat pentru Earth Engine sau API-ul "
            f"Earth Engine nu este activat. Verifică {ENV_GEE_PROJECT} în fișierul .env "
            "(valoarea corectă este în .env.example)."
        )
    if any(s in text for s in ("permission", "403", "forbidden", "access denied")):
        return f"Contul tău nu are acces la proiectul '{project}'. {ROLES_HINT}"
    if any(
        s in text
        for s in (
            "authenticate",
            "authorize",
            "credentials",
            "invalid_grant",
            "reauth",
            "token",
            "401",
        )
    ):
        return (
            "Nu ești autentificat în Earth Engine (sau autentificarea a expirat). "
            "Rulează: earthengine authenticate"
        )
    return f"Eroare neașteptată de la Earth Engine: {message}"


def _fail(message: str) -> int:
    print(f"EROARE: {message}", file=sys.stderr)
    return 1


def _aoi_geometry(ee: Any, config: Config) -> Any:
    feature = config.aoi_geojson()["features"][0]
    geometry = ee.Geometry(feature["geometry"])
    if config.aoi.buffer_m > 0:
        geometry = geometry.buffer(config.aoi.buffer_m)
    return geometry


def main() -> int:
    try:
        import ee
    except ImportError:
        return _fail(
            "Pachetul earthengine-api nu este instalat. "
            'Rulează în processing/: pip install -e ".[gee]"'
        )

    try:
        config = load_config()
        gee = config.require_gee()
    except GeeConfigError as exc:
        return _fail(
            f"Configurație Earth Engine incompletă: {exc}\n"
            f"Copiază {ENV_GEE_PROJECT} din .env.example în .env "
            f"({ENV_GEE_SERVICE_ACCOUNT_KEY} este opțional)."
        )
    assert gee.project is not None

    try:
        if gee.service_account_key is not None:
            credentials = ee.ServiceAccountCredentials(key_file=str(gee.service_account_key))
            ee.Initialize(credentials=credentials, project=gee.project)
            auth = f"cont de serviciu ({gee.service_account_key.name})"
        else:
            ee.Initialize(project=gee.project)
            auth = "cont Google personal (earthengine authenticate)"

        start = config.season.start_date
        end_exclusive = config.season.end_date + timedelta(days=1)
        count = (
            ee.ImageCollection(config.sentinel2.collection)
            .filterBounds(_aoi_geometry(ee, config))
            .filterDate(start.isoformat(), end_exclusive.isoformat())
            .size()
            .getInfo()
        )
    except Exception as exc:  # noqa: BLE001 - EE and google-auth raise many exception types
        return _fail(explain_error(str(exc), gee.project))

    print(f"OK: conexiune Earth Engine reușită (proiect '{gee.project}', {auth}).")
    print(
        f"{count} imagini {config.sentinel2.collection} peste zona de studiu "
        f"în perioada {start} – {config.season.end_date}."
    )
    if count == 0:
        print("ATENȚIE: nicio imagine găsită; verifică perioada și zona din config.yaml.")
    print(SOURCE_CREDIT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
