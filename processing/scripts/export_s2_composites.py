from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date
from typing import Any

from skyhaler_processing.config import (
    ENV_GEE_PROJECT,
    ENV_GEE_SERVICE_ACCOUNT_KEY,
    Config,
    GeeConfigError,
    load_config,
)
from skyhaler_processing.gee import aoi_geometry, explain_error, initialise
from skyhaler_processing.sentinel2 import (
    analysis_grid,
    asset_exists,
    asset_id,
    build_composite,
    ensure_asset_folders,
    planned_exports,
    start_export,
)

SOURCE_CREDIT = (
    "Sursa datelor: Copernicus Sentinel-2 (ESA), prin Google Earth Engine. "
    "Mască de nori: Cloud Score+ (Google)."
)
FINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
TASKS_URL = "https://code.earthengine.google.com/tasks"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exportă compozitele Sentinel-2 fără nori.")
    parser.add_argument("--dry-run", action="store_true", help="doar listează, fără Earth Engine")
    parser.add_argument("--period", metavar="YYYY-MM-DD", help="doar fereastra care începe la dată")
    parser.add_argument(
        "--overwrite", action="store_true", help="înlocuiește asset-urile existente"
    )
    parser.add_argument("--wait", action="store_true", help="așteaptă terminarea exporturilor")
    parser.add_argument("--poll-seconds", type=int, default=30, help="interval de verificare")
    return parser.parse_args(argv)


def select_plan(
    plan: list[tuple[date, date, str]], period: str | None
) -> list[tuple[date, date, str]]:
    if period is None:
        return plan
    selected = [item for item in plan if item[0].isoformat() == period]
    if not selected:
        starts = ", ".join(item[0].isoformat() for item in plan)
        raise ValueError(f"Nicio fereastră nu începe la {period}. Ferestre disponibile: {starts}")
    return selected


def _fail(message: str) -> int:
    print(f"EROARE: {message}", file=sys.stderr)
    return 1


def _describe(config: Config, plan: list[tuple[date, date, str]]) -> None:
    s2 = config.sentinel2
    if config.export.destination == "asset":
        target = f"asset Earth Engine (…/assets/{config.export.asset_folder}/)"
    else:
        target = f"Google Drive (folder '{config.export.drive_folder}')"
    print(f"Anul {config.season.year}, {len(plan)} ferestre ({config.season.composite}).")
    print(f"Mască de nori: {s2.cloud_score_band} >= {s2.cloud_score_threshold} (Cloud Score+).")
    print(f"Indici: {', '.join(s2.indices)}. Grilă: {config.grid_resolution_m:g} m.")
    print(f"Destinație: {target}.")
    for start, end, name in plan:
        print(f"  {name}  ({start} – {end})")


def _wait(tasks: dict[str, Any], poll_seconds: int) -> bool:
    while True:
        statuses = {name: task.status() for name, task in tasks.items()}
        counts = Counter(status["state"] for status in statuses.values())
        print(
            "Stare exporturi: " + ", ".join(f"{state}={n}" for state, n in sorted(counts.items()))
        )
        if all(status["state"] in FINAL_STATES for status in statuses.values()):
            break
        time.sleep(poll_seconds)
    failed = {name: s for name, s in statuses.items() if s["state"] != "COMPLETED"}
    for name, status in failed.items():
        print(f"EȘUAT: {name}: {status.get('error_message', status['state'])}", file=sys.stderr)
    return not failed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config()
        plan = select_plan(planned_exports(config), args.period)
    except ValueError as exc:
        return _fail(str(exc))

    _describe(config, plan)
    if args.dry_run:
        print("Dry-run: nu s-a exportat nimic.")
        return 0

    try:
        import ee
    except ImportError:
        return _fail(
            "Pachetul earthengine-api nu este instalat. "
            'Rulează în processing/: pip install -e ".[gee]"'
        )
    try:
        gee = config.require_gee()
    except GeeConfigError as exc:
        return _fail(
            f"Configurație Earth Engine incompletă: {exc}\n"
            f"Copiază {ENV_GEE_PROJECT} din .env.example în .env "
            f"({ENV_GEE_SERVICE_ACCOUNT_KEY} este opțional)."
        )
    assert gee.project is not None

    tasks: dict[str, Any] = {}
    try:
        print(f"Autentificare: {initialise(ee, gee)}.")
        aoi = aoi_geometry(ee, config)
        grid = analysis_grid(ee, config, aoi)
        print(
            f"Grilă de export: {grid.width} × {grid.height} celule, origine {grid.transform[2]:g}, "
            f"{grid.transform[5]:g} ({grid.crs})."
        )
        use_assets = config.export.destination == "asset"
        if use_assets:
            ensure_asset_folders(ee, gee.project, config.export.asset_folder)

        for start, end, name in plan:
            if use_assets:
                target = asset_id(gee.project, config.export.asset_folder, name)
                if asset_exists(ee, target):
                    if not args.overwrite:
                        print(f"Sar peste {name}: există deja (folosește --overwrite).")
                        continue
                    ee.data.deleteAsset(target)
            composite = build_composite(ee, config, aoi, start, end)
            tasks[name] = start_export(ee, config, composite, name, aoi, grid)
            print(f"Pornit: {name}")
    except Exception as exc:  # noqa: BLE001 - EE and google-auth raise many exception types
        return _fail(explain_error(str(exc), gee.project))

    print(f"{len(tasks)} exporturi pornite. Urmărește-le la {TASKS_URL}")
    print(SOURCE_CREDIT)
    if args.wait and tasks:
        return 0 if _wait(tasks, args.poll_seconds) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
