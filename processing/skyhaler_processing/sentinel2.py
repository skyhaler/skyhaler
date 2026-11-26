from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from skyhaler_processing.config import Config
from skyhaler_processing.grid import (  # noqa: F401  (re-exported for backward compatibility)
    MAX_PIXELS,
    NODATA,
    OBSERVATION_BAND,
    Grid,
    analysis_grid,
    asset_exists,
    asset_id,
    ensure_asset_folders,
    grid_from_lonlat,
    observation_stats,
    snap_grid,
    start_export,
    utm_forward,
    utm_zone,
    window_name,
)

# Sentinel-2 surface reflectance bands kept in every composite: 10 m (B2-B4, B8),
# 20 m red edge / NIR narrow / SWIR (B5-B7, B8A, B11, B12), all resampled to the analysis grid.
REFLECTANCE_BANDS: list[str] = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
SR_SCALE = 10_000  # Level-2A digital numbers -> reflectance 0..1

# Normalised-difference indices: (a - b) / (a + b) for the band pair (a, b).
NORMALISED_DIFFERENCES: dict[str, tuple[str, str]] = {
    "NDVI": ("B8", "B4"),  # vegetation greenness
    "NDRE": ("B8", "B5"),  # red edge, sensitive to chlorophyll / canopy density
    "NDMI": ("B8", "B11"),  # vegetation moisture
    "MNDWI": ("B3", "B11"),  # open water
}
# Bare Soil Index: ((SWIR1 + Red) - (NIR + Blue)) / ((SWIR1 + Red) + (NIR + Blue)).
BSI_EXPRESSION = "((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue))"
SUPPORTED_INDICES = [*NORMALISED_DIFFERENCES, "BSI"]


def composite_name(start: date, end: date, composite: str) -> str:
    return window_name("s2", start, end, composite)


def planned_exports(config: Config) -> list[tuple[date, date, str]]:
    return [
        (start, end, composite_name(start, end, config.season.composite))
        for start, end in config.periods()
    ]


def apply_cloud_mask(image: Any, band: str, threshold: float) -> Any:
    return image.updateMask(image.select(band).gte(threshold))


def cloud_masked_collection(ee: Any, config: Config, aoi: Any, start: date, end: date) -> Any:
    s2 = config.sentinel2
    first = start.isoformat()
    last_exclusive = (end + timedelta(days=1)).isoformat()  # filterDate end is exclusive
    images = ee.ImageCollection(s2.collection).filterBounds(aoi).filterDate(first, last_exclusive)
    scores = (
        ee.ImageCollection(s2.cloud_score_collection)
        .filterBounds(aoi)
        .filterDate(first, last_exclusive)
    )
    linked = images.linkCollection(scores, [s2.cloud_score_band])
    return linked.map(
        lambda image: apply_cloud_mask(image, s2.cloud_score_band, s2.cloud_score_threshold)
    )


def add_indices(image: Any, names: list[str]) -> Any:
    for name in names:
        if name in NORMALISED_DIFFERENCES:
            first, second = NORMALISED_DIFFERENCES[name]
            index = image.normalizedDifference([first, second]).rename(name)
        elif name == "BSI":
            index = image.expression(
                BSI_EXPRESSION,
                {
                    "swir": image.select("B11"),
                    "red": image.select("B4"),
                    "nir": image.select("B8"),
                    "blue": image.select("B2"),
                },
            ).rename(name)
        else:
            raise ValueError(f"Unsupported index '{name}'; supported: {SUPPORTED_INDICES}")
        image = image.addBands(index)
    return image


def build_composite(ee: Any, config: Config, aoi: Any, start: date, end: date) -> Any:
    masked = cloud_masked_collection(ee, config, aoi, start, end)
    reflectance = masked.select(REFLECTANCE_BANDS).median().divide(SR_SCALE)
    observations = masked.select("B4").count().unmask(0).rename(OBSERVATION_BAND)

    composite = add_indices(reflectance, config.sentinel2.indices).addBands(observations)
    return (
        composite.toFloat()
        .clip(aoi)
        .set(
            {
                "system:time_start": ee.Date(start.isoformat()).millis(),
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "composite": config.season.composite,
                "cloud_score_band": config.sentinel2.cloud_score_band,
                "cloud_score_threshold": config.sentinel2.cloud_score_threshold,
                "n_scenes": masked.size(),
            }
        )
    )
