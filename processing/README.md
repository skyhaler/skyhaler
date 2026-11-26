# processing

Satellite data processing for Skyhaler (Sentinel-1/2/5P via Google Earth Engine, risk index).

## Configuration

`config.yaml` is the single source of truth for every non-secret processing parameter. Scripts must
read values from it and never hard-code dates, area, thresholds or `k`.

| Section | Holds |
| --- | --- |
| `aoi` | Study area file (`aoi/bucharest.geojson`, Municipiul București from OSM, EPSG:4326) and buffer |
| `season` | Analysis year, season start/end (`MM-DD`) and composite windows (`dekad` or `month`) |
| `crs` | Storage CRS (EPSG:4326) and metric CRS (EPSG:32635, UTM 35N) |
| `grid_resolution_m` | Analysis grid cell size |
| `sentinel2` | GEE collection, Cloud Score+ collection/band/threshold, spectral `indices` |
| `sentinel1` / `sentinel5p` | GEE collections, QA filters, polarisations, NO2 scaling |
| `export` | Export `destination` (`asset` or `drive`), `asset_folder`, `drive_folder`, `quicklook_dir` |
| `risk` | Weight `k` and low/medium/high class thresholds |

Secrets and per-person values come from environment variables (or the repo-root `.env`, see
`.env.example`), never from `config.yaml`:

- `GEE_PROJECT` (required for GEE scripts): Google Cloud project used for Earth Engine
- `GEE_SERVICE_ACCOUNT_KEY` (optional): path to a service account JSON key file, kept outside
  git. Leave it empty to use your personal Google account: run `earthengine authenticate` once.

## Usage

```python
from skyhaler_processing import load_config

config = load_config()  # processing/config.yaml + repo-root .env
config.periods()  # dekads: [(date(2025, 7, 1), date(2025, 7, 10)), ...] inclusive
config.aoi_geojson()  # parsed AOI GeoJSON
gee = config.require_gee()  # raises GeeConfigError if GEE_PROJECT is missing
```

Invalid values (reversed season, negative `k`, unsorted thresholds, missing AOI file, ...) raise a
`pydantic.ValidationError` at load time.

## Earth Engine setup

The team shares one noncommercial Earth Engine project, `skyhaler` (Contributor tier). Everyone
signs in with their own Google account; no service account key is needed.

1. **Ask for access.** Ask the owner of the `skyhaler` Google Cloud project (the assignee of
   issue #7, `vlasinmarian17` on GitHub) to add your Google account in IAM with these two roles:
   - **Earth Engine Resource Writer** (`roles/earthengine.writer`)
   - **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`)
2. **Install the Earth Engine extra** (kept out of the core dependencies so tests and CI run
   without it):

   ```bash
   cd processing
   pip install -e ".[dev,gee]"
   ```

3. **Authenticate once** with your Google account:

   ```bash
   earthengine authenticate
   ```

4. **Set the project.** Copy `GEE_PROJECT=skyhaler` from `.env.example` into the repo-root `.env`.
   Leave `GEE_SERVICE_ACCOUNT_KEY` empty unless you were explicitly given a service account key.
5. **Run the check** from `processing/`:

   ```bash
   python scripts/check_gee.py
   ```

   On success it prints `OK: ...` and the number of Sentinel-2 images over the study area for the
   configured season. On failure it says what to fix: not authenticated, a missing IAM role, or a
   wrong/unregistered project.

**Never commit a key file or credentials.** Keep any service account JSON key outside the repo
and only point to it with `GEE_SERVICE_ACCOUNT_KEY` in your local `.env`.

## Sentinel-2 composites (task #9)

Cloud-masked median composites, one per window in `season` (9 dekads, Jul–Sep). Each composite has
10 reflectance bands (`B2`..`B12`, scaled to 0–1), the indices listed in `sentinel2.indices`
(NDVI, NDRE, NDMI, MNDWI, BSI) and `n_obs` (number of clear observations per pixel; 0 = gap).

- **Mask:** Cloud Score+ `cs_cdf >= sentinel2.cloud_score_threshold` (0.6).
- **Grid:** fixed 10 m grid in EPSG:32635, snapped to multiples of 10 m, so every composite (and
  later the Sentinel-1 / risk layers) lines up pixel for pixel.
- **Names:** `s2_<year>_dekad_<MMDD>_<MMDD>`, under `projects/<GEE_PROJECT>/assets/<export.asset_folder>/`.

Decide `season.year` in `config.yaml` before the first export (it must match the VHR imagery year
you validate against).

```bash
cd processing
python scripts/export_s2_composites.py --dry-run             # list what would be exported, no GEE needed
python scripts/export_s2_composites.py --period 2025-07-01 --wait   # one window as a test
python scripts/quicklook_s2.py                               # RGB / NDVI / n_obs thumbnails + index.html
python scripts/export_s2_composites.py                       # all windows (existing assets are skipped)
```

Options of the export script: `--overwrite` (replace existing assets), `--wait` (poll until the
tasks finish), `--poll-seconds N`. Set `export.destination: drive` to write GeoTIFFs to the Drive
folder `export.drive_folder` instead of Earth Engine assets.

Quick-look output goes to `export.quicklook_dir` (`../data/quicklook`, outside git): open
`index.html`, check each window for cloud artefacts and large gaps (gap fraction is printed too).

Data: contains modified Copernicus Sentinel-2 data (ESA), processed with Google Earth Engine; cloud
mask Cloud Score+ (Google). Keep exports and thumbnails private (no public hosting).

## Sentinel-1 composites (task #10)

Median SAR backscatter composites on the same windows and the same 10 m grid as the Sentinel-2
composites, so the layers line up pixel by pixel (shared code in `skyhaler_processing/grid.py`).
Each composite has `VV` and `VH` in dB, `VH_VV` (VH - VV in dB, cross-polarisation ratio) and
`n_obs` (number of observations per pixel; 0 = gap).

- **Scenes:** `COPERNICUS/S1_GRD` (already calibrated, noise-removed and terrain corrected),
  `sentinel1.instrument_mode` (IW) and one `sentinel1.orbit_pass` (DESCENDING by default; use one
  pass so the incidence angle stays comparable, or `BOTH` to get more observations).
- **Mask:** backscatter below `sentinel1.noise_floor_db` (-30 dB) is treated as noise / scene border.
  There is no cloud mask: radar sees through clouds.
- **Names:** `s1_<year>_dekad_<MMDD>_<MMDD>`, in the same asset folder as the Sentinel-2 composites.

```bash
cd processing
python scripts/export_s1_composites.py --dry-run                    # list the windows, no GEE needed
python scripts/export_s1_composites.py --period 2025-07-01 --wait   # one window as a test
python scripts/quicklook_s1.py                                      # VV / VH / n_obs previews + index_s1.html
python scripts/export_s1_composites.py --wait                       # all windows (existing assets skipped)
```

Same options as the Sentinel-2 export (`--overwrite`, `--wait`, `--poll-seconds`). Data: contains
modified Copernicus Sentinel-1 data (ESA), processed with Google Earth Engine; keep exports and
thumbnails private.

## Development

```bash
cd processing
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -v
```

AOI boundary: © OpenStreetMap contributors, ODbL 1.0.
