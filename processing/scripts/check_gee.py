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

from skyhaler_processing.config import (
    ENV_GEE_PROJECT,
    ENV_GEE_SERVICE_ACCOUNT_KEY,
    GeeConfigError,
    load_config,
)
from skyhaler_processing.gee import aoi_geometry, explain_error, initialise

SOURCE_CREDIT = "Sursa datelor: Copernicus Sentinel-2 (ESA), prin Google Earth Engine."


def _fail(message: str) -> int:
    print(f"EROARE: {message}", file=sys.stderr)
    return 1


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
        auth = initialise(ee, gee)

        start = config.season.start_date
        end_exclusive = config.season.end_date + timedelta(days=1)
        count = (
            ee.ImageCollection(config.sentinel2.collection)
            .filterBounds(aoi_geometry(ee, config))
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
