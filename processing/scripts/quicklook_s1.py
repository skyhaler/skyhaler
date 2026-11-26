"""
Usage (from processing/, after `pip install -e ".[gee]"` and `earthengine authenticate`):

    python scripts/quicklook_s1.py
    python scripts/quicklook_s1.py --period 2025-07-01

Look for: bright or dark stripes along scene borders (border noise), black holes (below the
noise floor), and windows with few observations (noisy speckle). Built-up areas are bright in VV,
water and smooth surfaces are dark. Exit code 0 on success, 1 on any error.
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
from skyhaler_processing.grid import OBSERVATION_BAND, observation_stats
from skyhaler_processing.sentinel1 import build_composite, planned_exports

THUMB_PIXELS = 900  # longest side of the preview images
VV_RANGE = (-20.0, 0.0)  # dB shown from black to white
VH_RANGE = (-28.0, -8.0)
OBS_DISPLAY_MAX = 6  # n_obs value shown as the greenest colour
OBS_PALETTE = ["#d73027", "#fee08b", "#1a9850"]
SOURCE_CREDIT = (
    "Sursa datelor: Copernicus Sentinel-1 (ESA), prin Google Earth Engine. "
    "Conține date Copernicus Sentinel modificate ({year})."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verificare vizuală a compozitelor Sentinel-1.")
    parser.add_argument("--period", metavar="YYYY-MM-DD", help="doar fereastra care începe la dată")
    return parser.parse_args(argv)


def render_html(rows: list[dict[str, Any]], year: int, orbit_pass: str) -> str:
    body = []
    for row in rows:
        previews = "".join(
            f'<td><img src="{html.escape(row["files"][kind])}" alt="{html.escape(kind)}"></td>'
            if kind in row["files"]
            else "<td>–</td>"
            for kind in ("vv", "vh", "nobs")
        )
        body.append(
            f"<tr><td><b>{html.escape(row['start'])} – {html.escape(row['end'])}</b><br>"
            f"{html.escape(row['name'])}<br>Scene în fereastră: {row['n_scenes']}<br>"
            f"Fără observații: {row['gap_fraction'] * 100:.1f}%<br>"
            f"Observații (medie): {row['mean_obs']:.1f}</td>{previews}</tr>"
        )
    credit = html.escape(SOURCE_CREDIT.format(year=year))
    return f"""<!doctype html>
<html lang="ro">
<head>
<meta charset="utf-8">
<title>Compozite Sentinel-1: verificare vizuală</title>
<style>
body {{ font-family: sans-serif; margin: 1.5rem; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; }}
img {{ width: 340px; background: #e8e8e8; }}
</style>
</head>
<body>
<h1>Compozite Sentinel-1 {year} (orbită {html.escape(orbit_pass)}): verificare vizuală</h1>
<p>Retrodifuzare în dB. Căutați dungi luminoase sau întunecate la marginea scenelor (zgomot de
margine), găuri negre (sub pragul de zgomot) și ferestre cu puține observații. Zonele construite
sunt luminoase în VV, apa și suprafețele netede sunt întunecate.</p>
<table>
<tr><th>Perioada</th><th>VV (dB)</th><th>VH (dB)</th>
<th>Observații (roșu = niciuna)</th></tr>
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
                "nobs": composite.select(OBSERVATION_BAND).visualize(
                    min=0, max=OBS_DISPLAY_MAX, palette=OBS_PALETTE
                ),
            }
            if "VV" in config.sentinel1.polarisations:
                previews["vv"] = composite.select("VV").visualize(min=VV_RANGE[0], max=VV_RANGE[1])
            if "VH" in config.sentinel1.polarisations:
                previews["vh"] = composite.select("VH").visualize(min=VH_RANGE[0], max=VH_RANGE[1])
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
                f"{name}: {n_scenes} scene, fără observații "
                f"{stats['gap_fraction'] * 100:.1f}%, observații (medie) {stats['mean_obs']:.1f}"
            )
    except Exception as exc:  # noqa: BLE001 - EE and google-auth raise many exception types
        return _fail(explain_error(str(exc), gee.project))

    index = out_dir / "index_s1.html"
    index.write_text(
        render_html(rows, config.season.year, config.sentinel1.orbit_pass), encoding="utf-8"
    )
    print(f"Gata. Deschide în browser: {index}")
    print(SOURCE_CREDIT.format(year=config.season.year))
    return 0


if __name__ == "__main__":
    sys.exit(main())
