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
