from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from skyhaler_processing.config import Config
from skyhaler_processing.grid import OBSERVATION_BAND, window_name

RATIO_BAND = "VH_VV"  # cross-polarisation ratio in dB: VH - VV


def composite_name(start: date, end: date, composite: str) -> str:
    return window_name("s1", start, end, composite)


def planned_exports(config: Config) -> list[tuple[date, date, str]]:
    return [
        (start, end, composite_name(start, end, config.season.composite))
        for start, end in config.periods()
    ]


def has_ratio(polarisations: list[str]) -> bool:
    return "VV" in polarisations and "VH" in polarisations


def output_bands(polarisations: list[str]) -> list[str]:
    bands = list(polarisations)
    if has_ratio(polarisations):
        bands.append(RATIO_BAND)
    return [*bands, OBSERVATION_BAND]


def sar_collection(ee: Any, config: Config, aoi: Any, start: date, end: date) -> Any:
    s1 = config.sentinel1
    first = start.isoformat()
    last_exclusive = (end + timedelta(days=1)).isoformat()  # filterDate end is exclusive
    images = (
        ee.ImageCollection(s1.collection)
        .filterBounds(aoi)
        .filterDate(first, last_exclusive)
        .filter(ee.Filter.eq("instrumentMode", s1.instrument_mode))
    )
    for polarisation in s1.polarisations:
        images = images.filter(
            ee.Filter.listContains("transmitterReceiverPolarisation", polarisation)
        )
    if s1.orbit_pass != "BOTH":
        images = images.filter(ee.Filter.eq("orbitProperties_pass", s1.orbit_pass))
    return images.select(s1.polarisations).map(
        lambda image: image.updateMask(image.gte(s1.noise_floor_db))
    )


def build_composite(ee: Any, config: Config, aoi: Any, start: date, end: date) -> Any:
    s1 = config.sentinel1
    scenes = sar_collection(ee, config, aoi, start, end)
    backscatter = scenes.median()
    composite = backscatter
    if has_ratio(s1.polarisations):
        ratio = backscatter.select("VH").subtract(backscatter.select("VV")).rename(RATIO_BAND)
        composite = composite.addBands(ratio)
    observations = scenes.select(s1.polarisations[0]).count().unmask(0).rename(OBSERVATION_BAND)

    return (
        composite.addBands(observations)
        .toFloat()
        .clip(aoi)
        .set(
            {
                "system:time_start": ee.Date(start.isoformat()).millis(),
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "composite": config.season.composite,
                "instrument_mode": s1.instrument_mode,
                "orbit_pass": s1.orbit_pass,
                "noise_floor_db": s1.noise_floor_db,
                "n_scenes": scenes.size(),
            }
        )
    )
