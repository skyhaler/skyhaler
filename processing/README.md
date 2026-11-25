# processing

Satellite data processing for Skyhaler (Sentinel-1/2/5P via Google Earth Engine, risk index).

## Configuration

`config.yaml` is the single source of truth for every non-secret processing parameter. Scripts must
read values from it and never hard-code dates, area, thresholds or `k`.

| Section | Holds |
| --- | --- |
| `aoi` | Study area file (`aoi/bucharest.geojson`, Municipiul București from OSM, EPSG:4326) and buffer |
| `season` | Analysis year, season start/end (`MM-DD`) and composite window length |
| `crs` | Storage CRS (EPSG:4326) and metric CRS (EPSG:32635, UTM 35N) |
| `grid_resolution_m` | Analysis grid cell size |
| `sentinel2` / `sentinel1` / `sentinel5p` | GEE collections, cloud / QA filters, polarisations, NO2 scaling |
| `risk` | Weight `k` and low/medium/high class thresholds |

Secrets and per-person values come from environment variables (or the repo-root `.env`, see
`.env.example`), never from `config.yaml`:

- `GEE_PROJECT`: Google Cloud project used for Earth Engine
- `GEE_SERVICE_ACCOUNT_KEY`: path to the service account JSON key file (keep it outside git)

## Usage

```python
from skyhaler_processing import load_config

config = load_config()  # processing/config.yaml + repo-root .env
config.periods()  # [(date(2025, 7, 1), date(2025, 7, 10)), ...] inclusive windows
config.aoi_geojson()  # parsed AOI GeoJSON
gee = config.require_gee()  # raises GeeConfigError if GEE settings are missing
```

Invalid values (reversed season, negative `k`, unsorted thresholds, missing AOI file, ...) raise a
`pydantic.ValidationError` at load time.

## Development

```bash
cd processing
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -v
```

AOI boundary: © OpenStreetMap contributors, ODbL 1.0.
