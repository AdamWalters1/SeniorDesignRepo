"""Convert local east/north/up metres to WGS84 coordinates."""

from __future__ import annotations

from math import cos, degrees, radians

from middleware.models import GeoPoint

EARTH_RADIUS_M = 6_378_137.0


def local_to_wgs84(
    position_m: tuple[float, float, float],
    origin: GeoPoint,
) -> GeoPoint:
    """Apply a local tangent-plane approximation around ``origin``.

    This is appropriate for the campus-scale scenarios in this project. For
    city-scale or survey-grade work, replace it with a pyproj ENU transform.
    Axes are x=east, y=north, z=up.
    """
    east_m, north_m, up_m = position_m
    latitude = origin.lat + degrees(north_m / EARTH_RADIUS_M)
    longitude = origin.lng + degrees(
        east_m / (EARTH_RADIUS_M * cos(radians(origin.lat)))
    )
    return GeoPoint(latitude, longitude, origin.alt_m + up_m)
