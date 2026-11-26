"""
Usage (from processing/, after `pip install -e ".[gee]"` and `earthengine authenticate`):

    python scripts/quicklook_s2.py
    python scripts/quicklook_s2.py --period 2025-07-01

Look for: bright blocky patches or dark shadows in the true-colour image (missed clouds), NDVI
holes, and red areas in the observation map (windows too short for this cloud score threshold).
Exit code 0 on success, 1 on any error.
"""

from __future__ import annotations

import argparse
import html
import sys
import urllib.request
from pathlib import Path
from typing import Any

from skyhaler_processing.config import GeeConfigError, load_config
from skyhaler_processing.gee import aoi_geometry, explain_error, initialise
from skyhaler_processing.sentinel2 import (
    OBSERVATION_BAND,
    build_composite,
    observation_stats,
    planned_exports,
)

THUMB_PIXELS = 900  # longest side of the preview images
OBS_DISPLAY_MAX = 6  # n_obs value shown as the greenest colour
NDVI_PALETTE = ["#a50026", "#f46d43", "#fee08b", "#a6d96a", "#1a9850", "#006837"]
OBS_PALETTE = ["#d73027", "#fee08b", "#1a9850"]
SOURCE_CREDIT = (
    "Sursa datelor: Copernicus Sentinel-2 (ESA), prin Google Earth Engine. "
    "Conține date Copernicus Sentinel modificate ({year}). Mască de nori: Cloud Score+ (Google)."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verificare vizuală a compozitelor Sentinel-2.")
    parser.add_argument("--period", metavar="YYYY-MM-DD", help="doar fereastra care începe la dată")
    return parser.parse_args(argv)


def render_html(rows: list[dict[str, Any]], year: int, threshold: float) -> str:
    body = []
    for row in rows:
        previews = "".join(
            f'<td><img src="{html.escape(row["files"][kind])}" alt="{html.escape(kind)}"></td>'
            if kind in row["files"]
            else "<td>–</td>"
            for kind in ("rgb", "ndvi", "nobs")
        )
        body.append(
            f"<tr><td><b>{html.escape(row['start'])} – {html.escape(row['end'])}</b><br>"
            f"{html.escape(row['name'])}<br>Scene în fereastră: {row['n_scenes']}<br>"
            f"Fără observații valide: {row['gap_fraction'] * 100:.1f}%<br>"
            f"Observații valide (medie): {row['mean_obs']:.1f}</td>{previews}</tr>"
        )
    credit = html.escape(SOURCE_CREDIT.format(year=year))
    return f"""<!doctype html>
<html lang="ro">
<head>
<meta charset="utf-8">
<title>Compozite Sentinel-2: verificare vizuală</title>
<style>
body {{ font-family: sans-serif; margin: 1.5rem; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; }}
img {{ width: 340px; background: #e8e8e8; }}
</style>
</head>
<body>
<h1>Compozite Sentinel-2 {year}: verificare vizuală a norilor</h1>
<p>Mască de nori Cloud Score+ cu prag {threshold}. Căutați în imaginea în culori reale zone
luminoase cu margini drepte (nori ratați) sau umbre întunecate, găuri în NDVI și zone roșii în
harta observațiilor (nicio observație validă în fereastră).</p>
<table>
<tr><th>Perioada</th><th>Culori reale (B4-B3-B2)</th><th>NDVI</th>
<th>Observații valide (roșu = niciuna)</th></tr>
{"".join(body)}
</table>
<p><small>{credit}</small></p>
</body>
</html>
"""


def _download(url: str, path: Path) -> None:
    with urllib.request.urlopen(url, timeout=180) as response:  # noqa: S310 - EE thumbnail URL
        path.write_bytes(response.read())


def _fail(message: str) -> int:
    print(f"EROARE: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
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
        return _fail(f"Configurație Earth Engine incompletă: {exc}")
    assert gee.project is not None

    plan = planned_exports(config)
    if args.period:
        plan = [item for item in plan if item[0].isoformat() == args.period]
        if not plan:
            return _fail(f"Nicio fereastră nu începe la {args.period}.")

    out_dir = config.export.quicklook_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    try:
        print(f"Autentificare: {initialise(ee, gee)}.")
        aoi = aoi_geometry(ee, config)
        thumb = {
            "region": aoi,
            "dimensions": THUMB_PIXELS,
            "format": "png",
            "crs": config.crs.metric,
        }
        for start, end, name in plan:
            composite = build_composite(ee, config, aoi, start, end)
            stats = observation_stats(ee, composite, aoi)
            previews = {
                "rgb": composite.visualize(bands=["B4", "B3", "B2"], min=0.0, max=0.3),
                "nobs": composite.select(OBSERVATION_BAND).visualize(
                    min=0, max=OBS_DISPLAY_MAX, palette=OBS_PALETTE
                ),
            }
            if "NDVI" in config.sentinel2.indices:
                previews["ndvi"] = composite.select("NDVI").visualize(
                    min=0.0, max=0.9, palette=NDVI_PALETTE
                )
            files: dict[str, str] = {}
            for kind, image in previews.items():
                files[kind] = f"{name}_{kind}.png"
                _download(image.getThumbURL(thumb), out_dir / files[kind])
            n_scenes = int(composite.get("n_scenes").getInfo())
            rows.append(
                {
                    "name": name,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "n_scenes": n_scenes,
                    "files": files,
                    **stats,
                }
            )
            print(
                f"{name}: {n_scenes} scene, fără observații valide "
                f"{stats['gap_fraction'] * 100:.1f}%, observații valide (medie) "
                f"{stats['mean_obs']:.1f}"
            )
    except Exception as exc:  # noqa: BLE001 - EE and google-auth raise many exception types
        return _fail(explain_error(str(exc), gee.project))

    index = out_dir / "index.html"
    index.write_text(
        render_html(rows, config.season.year, config.sentinel2.cloud_score_threshold),
        encoding="utf-8",
    )
    print(f"Gata. Deschide în browser: {index}")
    print(SOURCE_CREDIT.format(year=config.season.year))
    return 0


if __name__ == "__main__":
    sys.exit(main())
