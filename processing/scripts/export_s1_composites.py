from __future__ import annotations

import sys

from skyhaler_processing.config import Config
from skyhaler_processing.export_cli import Layer, run
from skyhaler_processing.sentinel1 import build_composite, output_bands, planned_exports

SOURCE_CREDIT = (
    "Sursa datelor: Copernicus Sentinel-1 (ESA), prin Google Earth Engine. "
    "Conține date Copernicus Sentinel modificate."
)


def _details(config: Config) -> list[str]:
    s1 = config.sentinel1
    return [
        f"Mod {s1.instrument_mode}, orbită {s1.orbit_pass}, prag zgomot {s1.noise_floor_db:g} dB.",
        f"Benzi: {', '.join(output_bands(s1.polarisations))}.",
    ]


LAYER = Layer(
    description="Exportă compozitele Sentinel-1 (SAR).",
    credit=SOURCE_CREDIT,
    plan=planned_exports,
    build=build_composite,
    details=_details,
)


def main(argv: list[str] | None = None) -> int:
    return run(LAYER, argv)


if __name__ == "__main__":
    sys.exit(main())
