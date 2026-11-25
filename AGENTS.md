# AGENTS.md

## Project

Skyhaler: web app showing pollen sources and air quality (Bucharest) for people with allergies and asthma.
See `docs/REQUIREMENTS.md`.

## Layout

`backend/`, `frontend/`, `processing/`, `db/`, `docs/`, `data/` (git-ignored). Keep each concern in its own folder.

## Hard rules

- Never commit data or secrets. `data/` and imagery formats are git-ignored; use `.env` (see `.env.example`).
- The imagery is licensed for the ROSPIN masterclass only: no upload to GitHub, Kaggle, Hugging Face or public cloud;
  no public hosting of anything derived from it.
- Do not hard-code credentials, paths or API keys. Read them from environment variables.
- Script outputs, figure titles and labels are in **Romanian**.
- Every map/figure/slide shows: "Data © AIM Space, provided for educational use in the ROSPIN Satellite Data
  Processing Masterclass 2026" plus the dataset's source credit.

## Mapping library

Use **MapLibre GL JS** (`maplibre-gl`) with React and TypeScript.

MapLibre was chosen over Leaflet due to its GPU-accelerated WebGL rendering, native vector tile support, data-driven styling and better scalability for large geospatial datasets.

- Use GeoJSON for risk and NO₂ layers.
- Use raster tiles for VHR satellite imagery.
- Use vector tiles when necessary to optimize performance.
- Implement custom legends and use `GeolocateControl` for geolocation.
- Ensure proper map initialization, resizing and cleanup.

See the decision log in `docs/REQUIREMENTS.md` (issue #5).