from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
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
from skyhaler_processing.grid import (
    analysis_grid,
    asset_exists,
    asset_id,
    ensure_asset_folders,
    start_export,
)

FINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
TASKS_URL = "https://code.earthengine.google.com/tasks"

Plan = list[tuple[date, date, str]]


@dataclass(frozen=True)
class Layer:
    description: str  # argparse description (Romanian)
    credit: str  # data credit line printed after the export starts
    plan: Callable[[Config], Plan]  # (start, end, name) per window
    build: Callable[[Any, Config, Any, date, date], Any]  # (ee, config, aoi, start, end) -> image
    details: Callable[[Config], list[str]]  # layer-specific header lines


def parse_args(description: str, argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dry-run", action="store_true", help="doar listează, fără Earth Engine")
    parser.add_argument("--period", metavar="YYYY-MM-DD", help="doar fereastra care începe la dată")
    parser.add_argument(
        "--overwrite", action="store_true", help="înlocuiește asset-urile existente"
    )
    parser.add_argument("--wait", action="store_true", help="așteaptă terminarea exporturilor")
    parser.add_argument("--poll-seconds", type=int, default=30, help="interval de verificare")
    return parser.parse_args(argv)


def select_plan(plan: Plan, period: str | None) -> Plan:
    if period is None:
        return plan
    selected = [item for item in plan if item[0].isoformat() == period]
    if not selected:
        starts = ", ".join(item[0].isoformat() for item in plan)
        raise ValueError(f"Nicio fereastră nu începe la {period}. Ferestre disponibile: {starts}")
    return selected


def fail(message: str) -> int:
    print(f"EROARE: {message}", file=sys.stderr)
    return 1


def describe(config: Config, plan: Plan, details: list[str]) -> None:
    if config.export.destination == "asset":
        target = f"asset Earth Engine (…/assets/{config.export.asset_folder}/)"
    else:
        target = f"Google Drive (folder '{config.export.drive_folder}')"
    print(f"Anul {config.season.year}, {len(plan)} ferestre ({config.season.composite}).")
    for line in details:
        print(line)
    print(f"Grilă: {config.grid_resolution_m:g} m.")
    print(f"Destinație: {target}.")
    for start, end, name in plan:
        print(f"  {name}  ({start} – {end})")


def wait_for(tasks: dict[str, Any], poll_seconds: int) -> bool:
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


def run(layer: Layer, argv: list[str] | None = None) -> int:
    args = parse_args(layer.description, argv)
    try:
        config = load_config()
        plan = select_plan(layer.plan(config), args.period)
    except ValueError as exc:
        return fail(str(exc))

    describe(config, plan, layer.details(config))
    if args.dry_run:
        print("Dry-run: nu s-a exportat nimic.")
        return 0

    try:
        import ee
    except ImportError:
        return fail(
            "Pachetul earthengine-api nu este instalat. "
            'Rulează în processing/: pip install -e ".[gee]"'
        )
    try:
        gee = config.require_gee()
    except GeeConfigError as exc:
        return fail(
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
            image = layer.build(ee, config, aoi, start, end)
            tasks[name] = start_export(ee, config, image, name, aoi, grid)
            print(f"Pornit: {name}")
    except Exception as exc:  # noqa: BLE001 - EE and google-auth raise many exception types
        return fail(explain_error(str(exc), gee.project))

    print(f"{len(tasks)} exporturi pornite. Urmărește-le la {TASKS_URL}")
    print(layer.credit)
    if args.wait and tasks:
        return 0 if wait_for(tasks, args.poll_seconds) else 1
    return 0
