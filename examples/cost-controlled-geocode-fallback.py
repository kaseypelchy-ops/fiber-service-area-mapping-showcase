"""
Cost-controlled reverse-geocode fallback.

Simplified public example based on the production pipeline.

The fallback is optional. It samples points inside the service area only when
they are not already close to a matched reference location, and it enforces a
hard request cap.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from shapely.geometry import Point, Polygon
from shapely.prepared import prep
from shapely.strtree import STRtree


def haversine_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius = 6_371_000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(
        lat2 - lat1
    )

    delta_lambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )

    return radius * 2 * math.asin(math.sqrt(a))


def build_point_index(
    rows: list[dict],
):
    points = []

    for row in rows:
        try:
            points.append(
                Point(
                    float(row["longitude"]),
                    float(row["latitude"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    return (
        points,
        STRtree(points) if points else None,
    )


def nearest_distance_meters(
    *,
    latitude: float,
    longitude: float,
    points,
    tree,
):
    if not points or tree is None:
        return None

    query_point = Point(
        longitude,
        latitude,
    )

    nearest = tree.nearest(query_point)

    # Shapely versions can return an index or the geometry.
    if isinstance(nearest, int):
        nearest_point = points[nearest]
    else:
        nearest_point = nearest

    return haversine_meters(
        latitude,
        longitude,
        nearest_point.y,
        nearest_point.x,
    )


def generate_points_in_polygon(
    polygon: Polygon,
    *,
    spacing_meters: float = 100,
):
    """
    Generate an approximately square lon/lat sampling grid.
    """
    min_lon, min_lat, max_lon, max_lat = (
        polygon.bounds
    )

    center_lat = (min_lat + max_lat) / 2

    lat_spacing = spacing_meters / 111_000

    lon_spacing = spacing_meters / (
        111_000
        * max(
            math.cos(math.radians(center_lat)),
            0.01,
        )
    )

    x = min_lon

    while x <= max_lon:
        y = min_lat

        while y <= max_lat:
            point = Point(x, y)

            if polygon.contains(point):
                yield point.y, point.x

            y += lat_spacing

        x += lon_spacing


def add_fallback_locations(
    *,
    service_area,
    existing_locations: list[dict],
    reverse_geocode: Callable[
        [float, float],
        dict | None,
    ],
    request_cap: int = 250,
    skip_radius_meters: float = 75,
    sample_spacing_meters: float = 100,
    delay_seconds: float = 0.05,
):
    """
    Evaluate uncovered sample points while keeping external API usage bounded.
    """
    if request_cap <= 0:
        return existing_locations

    prepared_area = prep(service_area)

    points, tree = build_point_index(
        existing_locations
    )

    seen = {
        (
            str(row.get("address") or "")
            .upper()
            .strip(),
            str(row.get("city") or "")
            .upper()
            .strip(),
            str(row.get("state") or "")
            .upper()
            .strip(),
            str(row.get("zip") or "")[:5],
        )
        for row in existing_locations
    }

    requests_made = 0
    output = list(existing_locations)

    polygons = (
        [service_area]
        if service_area.geom_type == "Polygon"
        else list(service_area.geoms)
    )

    for polygon in polygons:
        for latitude, longitude in generate_points_in_polygon(
            polygon,
            spacing_meters=sample_spacing_meters,
        ):
            if requests_made >= request_cap:
                return output

            distance = nearest_distance_meters(
                latitude=latitude,
                longitude=longitude,
                points=points,
                tree=tree,
            )

            if (
                distance is not None
                and distance <= skip_radius_meters
            ):
                continue

            requests_made += 1

            candidate = reverse_geocode(
                latitude,
                longitude,
            )

            if delay_seconds > 0:
                time.sleep(delay_seconds)

            if not candidate:
                continue

            try:
                result_lat = float(
                    candidate["latitude"]
                )

                result_lon = float(
                    candidate["longitude"]
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            if not prepared_area.intersects(
                Point(result_lon, result_lat)
            ):
                continue

            key = (
                str(candidate.get("address") or "")
                .upper()
                .strip(),
                str(candidate.get("city") or "")
                .upper()
                .strip(),
                str(candidate.get("state") or "")
                .upper()
                .strip(),
                str(candidate.get("zip") or "")[:5],
            )

            if key in seen:
                continue

            output.append(candidate)
            seen.add(key)

            # Rebuild the index so later samples can skip the new location.
            points, tree = build_point_index(output)

    return output
