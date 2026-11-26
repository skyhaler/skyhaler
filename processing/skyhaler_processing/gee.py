"""Shared Google Earth Engine helpers: initialisation, error hints and the study-area geometry.

The ``ee`` module is passed in by the caller instead of being imported here, so this package
(and its tests) work without ``earthengine-api`` installed; install it with the ``gee`` extra.
"""

from __future__ import annotations

from typing import Any

from skyhaler_processing.config import ENV_GEE_PROJECT, Config, GeeCredentials

ROLES_HINT = (
    "Cere administratorului proiectului rolurile IAM 'Earth Engine Resource Writer' și "
    "'Service Usage Consumer' pentru contul tău Google (vezi processing/README.md)."
)


def explain_error(message: str, project: str) -> str:
    """Translate an Earth Engine / Google API error message into a Romanian fix-it hint."""
    text = message.lower()
    if "serviceusage" in text:
        return f"Lipsește rolul 'Service Usage Consumer' pe proiectul '{project}'. {ROLES_HINT}"
    if any(
        s in text
        for s in ("not found", "not registered", "not signed up", "has not been used", "disabled")
    ):
        return (
            f"Proiectul '{project}' nu există, nu este înregistrat pentru Earth Engine sau API-ul "
            f"Earth Engine nu este activat. Verifică {ENV_GEE_PROJECT} în fișierul .env "
            "(valoarea corectă este în .env.example)."
        )
    if any(s in text for s in ("permission", "403", "forbidden", "access denied")):
        return f"Contul tău nu are acces la proiectul '{project}'. {ROLES_HINT}"
    if any(
        s in text
        for s in (
            "authenticate",
            "authorize",
            "credentials",
            "invalid_grant",
            "reauth",
            "token",
            "401",
        )
    ):
        return (
            "Nu ești autentificat în Earth Engine (sau autentificarea a expirat). "
            "Rulează: earthengine authenticate"
        )
    return f"Eroare neașteptată de la Earth Engine: {message}"


def initialise(ee: Any, gee: GeeCredentials) -> str:
    """Initialise Earth Engine for ``gee.project``; return a Romanian description of the login."""
    assert gee.project is not None
    if gee.service_account_key is not None:
        credentials = ee.ServiceAccountCredentials(key_file=str(gee.service_account_key))
        ee.Initialize(credentials=credentials, project=gee.project)
        return f"cont de serviciu ({gee.service_account_key.name})"
    ee.Initialize(project=gee.project)
    return "cont Google personal (earthengine authenticate)"


def aoi_geometry(ee: Any, config: Config) -> Any:
    """Study area as an ``ee.Geometry`` (EPSG:4326), buffered by ``aoi.buffer_m`` if > 0."""
    feature = config.aoi_geojson()["features"][0]
    geometry = ee.Geometry(feature["geometry"])
    if config.aoi.buffer_m > 0:
        geometry = geometry.buffer(config.aoi.buffer_m)
    return geometry
