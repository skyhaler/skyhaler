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
| `sentinel2` / `sentinel1` / `sentinel5p` | GEE collections, cloud / QA filters, polarisations, NO2 scaling |
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

## Development

```bash
cd processing
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -v
```

AOI boundary: © OpenStreetMap contributors, ODbL 1.0.
