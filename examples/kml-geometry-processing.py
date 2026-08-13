"""
KML/KMZ geometry extraction and normalization.

Simplified public example based on the production fiber-mapping pipeline.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from io import BytesIO
from zipfile import ZipFile

import pyproj
from shapely.geometry import (
    LineString,
    Point,
    Polygon,
)
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union
from shapely.validation import make_valid


def local_name(tag: str) -> str:
    """Return the XML tag without its namespace."""
    return tag.split("}")[-1] if "}" in tag else tag


def read_kml_from_bytes(
    payload: bytes,
    file_name: str,
) -> str:
    """
    Accept raw KML or KMZ bytes and return decoded KML text.
    """
    if file_name.lower().endswith(".kmz"):
        with ZipFile(BytesIO(payload)) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".kml")
            ]

            if not names:
                raise ValueError("KMZ archive does not contain a KML file.")

            preferred = next(
                (
                    name
                    for name in names
                    if name.lower().endswith("doc.kml")
                ),
                names[0],
            )

            return archive.read(preferred).decode(
                "utf-8",
                errors="replace",
            )

    return payload.decode("utf-8", errors="replace")


def coordinates_from_element(element) -> list[tuple[float, float]]:
    """
    Read lon/lat coordinate pairs without automatically closing the ring.

    Polygon and LineString callers have different requirements, so closure is
    handled by the geometry-specific code.
    """
    coordinates = []

    for child in element.iter():
        if (
            local_name(child.tag) == "coordinates"
            and child.text
        ):
            for token in child.text.strip().split():
                parts = token.split(",")

                if len(parts) < 2:
                    continue

                try:
                    coordinates.append(
                        (float(parts[0]), float(parts[1]))
                    )
                except ValueError:
                    continue

    return coordinates


def close_ring(
    coordinates: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if (
        coordinates
        and coordinates[0] != coordinates[-1]
    ):
        coordinates = [*coordinates, coordinates[0]]

    return coordinates


def find_by_local_name(root, tag_name: str):
    return [
        element
        for element in root.iter()
        if local_name(element.tag) == tag_name
    ]


def polygon_parts(geometry):
    """Yield Polygon members from mixed valid geometry values."""
    if geometry is None or geometry.is_empty:
        return

    if geometry.geom_type == "Polygon":
        yield geometry
        return

    if geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms
        return

    if geometry.geom_type == "GeometryCollection":
        for child in geometry.geoms:
            yield from polygon_parts(child)


def extract_service_geometries(
    kml_text: str,
    *,
    line_buffer_meters: float = 75,
    point_buffer_meters: float = 25,
) -> list[Polygon]:
    """
    Convert supported KML geometry into valid WGS84 polygons.

    - Polygon: use the exterior ring.
    - LineString: buffer in a projected CRS.
    - Point: buffer in a projected CRS.
    """
    root = ET.fromstring(kml_text)

    to_web_mercator = pyproj.Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3857",
        always_xy=True,
    ).transform

    to_wgs84 = pyproj.Transformer.from_crs(
        "EPSG:3857",
        "EPSG:4326",
        always_xy=True,
    ).transform

    output: list[Polygon] = []

    for placemark in find_by_local_name(
        root,
        "Placemark",
    ):
        # Polygon geometry
        for polygon_element in find_by_local_name(
            placemark,
            "Polygon",
        ):
            outer_boundary = next(
                (
                    child
                    for child in polygon_element.iter()
                    if local_name(child.tag) == "outerBoundaryIs"
                ),
                polygon_element,
            )

            coordinates = coordinates_from_element(
                outer_boundary
            )

            if len(coordinates) < 3:
                continue

            polygon = Polygon(
                close_ring(coordinates)
            )

            if not polygon.is_valid:
                polygon = make_valid(polygon)

            output.extend(polygon_parts(polygon) or [])

        # LineString geometry
        for line_element in find_by_local_name(
            placemark,
            "LineString",
        ):
            coordinates = coordinates_from_element(
                line_element
            )

            if len(coordinates) < 2:
                continue

            # Do not close a LineString before buffering.
            line = LineString(coordinates)
            line_projected = shapely_transform(
                to_web_mercator,
                line,
            )

            buffered = line_projected.buffer(
                line_buffer_meters
            )

            buffered_wgs84 = shapely_transform(
                to_wgs84,
                buffered,
            )

            output.extend(
                polygon_parts(buffered_wgs84) or []
            )

        # Point geometry
        for point_element in find_by_local_name(
            placemark,
            "Point",
        ):
            coordinates = coordinates_from_element(
                point_element
            )

            if not coordinates:
                continue

            lon, lat = coordinates[0]

            point = Point(lon, lat)
            point_projected = shapely_transform(
                to_web_mercator,
                point,
            )

            buffered = point_projected.buffer(
                point_buffer_meters
            )

            buffered_wgs84 = shapely_transform(
                to_wgs84,
                buffered,
            )

            output.extend(
                polygon_parts(buffered_wgs84) or []
            )

    return [
        polygon
        for polygon in output
        if not polygon.is_empty
    ]


def build_combined_service_area(
    polygons: list[Polygon],
):
    """
    Merge service-area pieces into one valid Shapely geometry.
    """
    if not polygons:
        raise ValueError(
            "No usable service-area polygons were extracted."
        )

    combined = unary_union(polygons)

    if not combined.is_valid:
        combined = make_valid(combined)

    if combined.is_empty:
        raise ValueError(
            "Combined service-area geometry is empty."
        )

    return combined
