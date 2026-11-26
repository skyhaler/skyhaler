from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from skyhaler_processing.config import Config

# Sentinel-2 surface reflectance bands kept in every composite: 10 m (B2-B4, B8),
# 20 m red edge / NIR narrow / SWIR (B5-B7, B8A, B11, B12), all resampled to the analysis grid.
REFLECTANCE_BANDS: list[str] = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
SR_SCALE = 10_000  # Level-2A digital numbers -> reflectance 0..1
OBSERVATION_BAND = "n_obs"  # number of cloud-free observations behind each composite pixel
NODATA = -9999.0  # fill value of Drive (GeoTIFF) exports; asset exports keep real masks
MAX_PIXELS = 1e10  # export safety limit; Bucharest at 10 m is only a few million pixels

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


@dataclass(frozen=True)
class Grid:
    crs: str
    transform: list[float]
    width: int
    height: int


# --------------------------------------------------------------------------- pure helpers


def composite_name(start: date, end: date, composite: str) -> str:
    return f"s2_{start.year}_{composite}_{start:%m%d}_{end:%m%d}"


def planned_exports(config: Config) -> list[tuple[date, date, str]]:
    return [
        (start, end, composite_name(start, end, config.season.composite))
        for start, end in config.periods()
    ]


def asset_id(project: str, folder: str, name: str) -> str:
    return f"projects/{project}/assets/{folder}/{name}"


def snap_grid(crs: str, xmin: float, ymin: float, xmax: float, ymax: float, res: float) -> Grid:
    x0 = math.floor(xmin / res) * res
    y0 = math.ceil(ymax / res) * res
    width = math.ceil((xmax - x0) / res)
    height = math.ceil((y0 - ymin) / res)
    return Grid(crs=crs, transform=[res, 0, x0, 0, -res, y0], width=width, height=height)


# --------------------------------------------------------------------- Earth Engine pieces


def utm_forward(lon: float, lat: float, zone: int) -> tuple[float, float]:
    a = 6378137.0
    f = 1 / 298.257223563
    k0 = 0.9996
    n = f / (2 - f)
    big_a = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    alpha = [
        n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16,
        13 * n**2 / 48 - 3 * n**3 / 5,
        61 * n**3 / 240,
    ]
    lon0 = math.radians(zone * 6 - 183)
    phi = math.radians(lat)
    dlam = math.radians(lon) - lon0
    e = math.sqrt(f * (2 - f))
    t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
    xi = math.atan2(t, math.cos(dlam))
    eta = math.atanh(math.sin(dlam) / math.sqrt(1 + t * t))
    easting = eta + sum(
        alpha[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3)
    )
    northing = xi + sum(
        alpha[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3)
    )
    return 500000.0 + k0 * big_a * easting, k0 * big_a * northing


def _positions(coords: Any) -> list[tuple[float, float]]:
    if coords and isinstance(coords[0], (int, float)):
        return [(float(coords[0]), float(coords[1]))]
    return [pair for part in coords for pair in _positions(part)]


def utm_zone(crs: str) -> int:
    match = re.fullmatch(r"EPSG:326(\d{2})", crs)
    if not match:
        raise ValueError(f"Expected a northern-hemisphere UTM CRS (EPSG:326xx), got {crs!r}")
    return int(match.group(1))


def grid_from_lonlat(crs: str, geojson: dict, res: float) -> Grid:
    zone = utm_zone(crs)
    points = [utm_forward(lon, lat, zone) for lon, lat in _positions(geojson["coordinates"])]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return snap_grid(crs, min(xs), min(ys), max(xs), max(ys), res)


def analysis_grid(ee: Any, config: Config, aoi: Any) -> Grid:
    return grid_from_lonlat(config.crs.metric, aoi.getInfo(), config.grid_resolution_m)


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
    """Append the requested spectral indices (computed from a 0..1 reflectance image)."""
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


def observation_stats(ee: Any, composite: Any, aoi: Any) -> dict[str, float]:
    n_obs = composite.select(OBSERVATION_BAND)
    stats = (
        n_obs.eq(0)
        .rename("gap_fraction")
        .addBands(n_obs.rename("mean_obs"))
        .reduceRegion(ee.Reducer.mean(), aoi, 60, bestEffort=True, maxPixels=MAX_PIXELS)
        .getInfo()
    )
    return {
        "gap_fraction": float(stats.get("gap_fraction") or 0.0),
        "mean_obs": float(stats.get("mean_obs") or 0.0),
    }


# ------------------------------------------------------------------------------ exporting


def asset_exists(ee: Any, asset: str) -> bool:
    try:
        ee.data.getAsset(asset)
    except ee.EEException as exc:
        message = str(exc).lower()
        if "not found" in message or "does not exist" in message:
            return False
        raise
    return True


def ensure_asset_folders(ee: Any, project: str, folder: str) -> None:
    path = f"projects/{project}/assets"
    for part in folder.split("/"):
        path = f"{path}/{part}"
        if not asset_exists(ee, path):
            ee.data.createFolder(path)


def start_export(ee: Any, config: Config, image: Any, name: str, aoi: Any, grid: Grid) -> Any:
    export = config.export
    common: dict[str, Any] = {
        "description": name,
        "region": aoi,
        "crs": grid.crs,
        "crsTransform": grid.transform,
        "maxPixels": MAX_PIXELS,
    }
    if export.destination == "asset":
        project = config.require_gee().project
        assert project is not None
        task = ee.batch.Export.image.toAsset(
            image=image,
            assetId=asset_id(project, export.asset_folder, name),
            pyramidingPolicy={".default": "mean"},
            **common,
        )
    else:
        task = ee.batch.Export.image.toDrive(
            image=image.unmask(NODATA),
            folder=export.drive_folder,
            fileNamePrefix=name,
            fileFormat="GeoTIFF",
            **common,
        )
    task.start()
    return task
