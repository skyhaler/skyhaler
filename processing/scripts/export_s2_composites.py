from __future__ import annotations

import sys

from skyhaler_processing.config import Config
from skyhaler_processing.export_cli import Layer, run, select_plan  # noqa: F401
from skyhaler_processing.sentinel2 import build_composite, planned_exports

SOURCE_CREDIT = (
    "Sursa datelor: Copernicus Sentinel-2 (ESA), prin Google Earth Engine. "
    "Mască de nori: Cloud Score+ (Google)."
)


def _details(config: Config) -> list[str]:
    s2 = config.sentinel2
    return [
        f"Mască de nori: {s2.cloud_score_band} >= {s2.cloud_score_threshold} (Cloud Score+).",
        f"Indici: {', '.join(s2.indices)}.",
    ]


LAYER = Layer(
    description="Exportă compozitele Sentinel-2 fără nori.",
    credit=SOURCE_CREDIT,
    plan=planned_exports,
    build=build_composite,
    details=_details,
)


def main(argv: list[str] | None = None) -> int:
    return run(LAYER, argv)


if __name__ == "__main__":
    sys.exit(main())
