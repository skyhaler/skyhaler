# Requirements (draft, to be agreed by the team)

## Goal
Help people with allergies and asthma plan ahead by combining pollen sources (e.g. ragweed) and air quality.
Study area: Bucharest. Deadline: ROSPIN Demo Day, December 2026 (confirm date: 11 or 12 Dec).

## Data
| Source | Use | Notes |
| --- | --- | --- |
| Sentinel-2 (GEE) | vegetation, NDVI, Red Edge | free |
| Sentinel-5P (TROPOMI) | NO2, aerosol, HCHO | free, 3.5 x 5.5 km |
| PlanetScope (Planet Insights) | 3 m time series | SR change on 30 Nov 2026, keep periods consistent |
| KOMPSAT-3A / Pleiades Neo / SPOT 7 | VHR summer imagery | masterclass licence, private only |
| Ragweed ground truth | validation | to be collected |

## Functional (TBD)
- Map with pollen-source layer and air quality layer.
- TBD: user input, alerts, time resolution.

## Non-functional
- No secrets or data in git.
- Licence: educational use only, private demo, credit lines on all outputs.
- Romanian labels in outputs.

## Validation
- Independent reference (ground truth), baseline, honest test split by area/time, uncertainty stated.

## Open questions
- Final study area (Pleiades 38 km2 vs a KOMPSAT-3A tile).
- Who owns which component.

## Decision log

### D001 — Mapping library: Leaflet vs. MapLibre (Issue #5)

- Date: 2026-11-25
- Decision: MapLibre GL JS

#### Comparison

| Criterion | Leaflet | MapLibre GL JS |
| --- | --- | --- |
| GeoJSON layers | Native support | Native support |
| VHR raster/tile layers | Native support | Native support |
| Legends | Custom controls | Custom controls |
| Geolocation | Built-in (`map.locate()`) | Built-in (`GeolocateControl`) |
| Rendering | SVG / Canvas | GPU-accelerated WebGL |
| Vector tiles | Requires plugins | Native support |
| Performance with many cells | May require additional optimization | Better suited to large, tiled datasets |
| Implementation complexity | Low | Moderate |

#### Rationale

MapLibre GL JS was selected for its GPU-accelerated rendering,
native vector tile support and data-driven styling. These
features provide better scalability for visualizing large
numbers of pollen-risk cells, air quality layers and VHR imagery.

#### Implementation

- Use `maplibre-gl` with React and TypeScript.
- Use GeoJSON for initial risk and air quality layers.
- Use raster tiles for VHR imagery.
- Switch to vector tiles if performance becomes an issue.
- Implement custom legends and built-in geolocation.
- Serve licensed imagery and derived data locally.

#### Trade-offs

Higher implementation complexity and WebGL dependency.
Performance must be validated with actual project datasets.

#### References

- https://leafletjs.com/reference.html
- https://maplibre.org/maplibre-gl-js/docs/