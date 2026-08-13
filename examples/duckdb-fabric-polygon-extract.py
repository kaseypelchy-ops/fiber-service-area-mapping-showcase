"""
DuckDB bounding-box prefilter + exact Shapely point-in-polygon extraction.

Simplified public example based on the production fiber-mapping pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
from shapely.geometry import Point
from shapely.prepared import prep


def quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def safe_float(value: Any):
    try:
        if value in (None, ""):
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_for_match(value: Any) -> str:
    return " ".join(
        str(value or "")
        .upper()
        .replace(".", " ")
        .replace(",", " ")
        .split()
    )


def clean_zip(value: Any) -> str:
    digits = "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )

    return digits[:5]


def location_dedupe_key(record: dict[str, Any]):
    """
    Prefer an authoritative location identifier.

    Fall back to a normalized address identity when no location ID exists.
    """
    location_id = str(
        record.get("location_id") or ""
    ).strip()

    if location_id:
        return ("location_id", location_id)

    return (
        "address",
        normalize_for_match(
            record.get("address_primary")
        ),
        normalize_for_match(record.get("city")),
        str(record.get("state") or "")
        .upper()
        .strip(),
        clean_zip(record.get("zip")),
    )


def extract_locations_inside_polygon(
    *,
    database_path: str,
    table_name: str,
    service_area,
    batch_size: int = 10_000,
) -> list[dict[str, Any]]:
    """
    Query only rows inside the service-area bounding box, then perform the
    exact spatial test in Python.

    This avoids loading the full reference dataset into Python memory.
    """
    if not Path(database_path).exists():
        raise FileNotFoundError(database_path)

    min_lon, min_lat, max_lon, max_lat = (
        service_area.bounds
    )

    prepared_area = prep(service_area)

    table_sql = quote_identifier(table_name)

    connection = duckdb.connect(
        database_path,
        read_only=True,
    )

    try:
        description = connection.execute(
            f"DESCRIBE {table_sql}"
        ).fetchall()

        columns = {
            str(row[0]).lower(): str(row[0])
            for row in description
        }

        for required in (
            "address_primary",
            "latitude",
            "longitude",
        ):
            if required not in columns:
                raise RuntimeError(
                    f"Reference table is missing {required}."
                )

        latitude = quote_identifier(
            columns["latitude"]
        )

        longitude = quote_identifier(
            columns["longitude"]
        )

        def optional_column(
            source: str,
            alias: str,
        ) -> str:
            actual = columns.get(source)

            if actual is None:
                return (
                    f"CAST(NULL AS VARCHAR) "
                    f"AS {quote_identifier(alias)}"
                )

            return (
                f"CAST({quote_identifier(actual)} AS VARCHAR) "
                f"AS {quote_identifier(alias)}"
            )

        select_list = [
            optional_column(
                "location_id",
                "location_id",
            ),
            optional_column(
                "address_primary",
                "address_primary",
            ),
            optional_column("city", "city"),
            optional_column("state", "state"),
            optional_column("zip", "zip"),
            optional_column(
                "building_type_code",
                "building_type_code",
            ),
            optional_column(
                "land_use_code",
                "land_use_code",
            ),
            optional_column(
                "block_geoid",
                "block_geoid",
            ),
            f"TRY_CAST({latitude} AS DOUBLE) AS latitude",
            f"TRY_CAST({longitude} AS DOUBLE) AS longitude",
        ]

        query = f"""
            SELECT
                {", ".join(select_list)}
            FROM {table_sql}
            WHERE TRY_CAST({latitude} AS DOUBLE)
                    BETWEEN ? AND ?
              AND TRY_CAST({longitude} AS DOUBLE)
                    BETWEEN ? AND ?
              AND {quote_identifier(columns["address_primary"])}
                    IS NOT NULL
        """

        cursor = connection.execute(
            query,
            [
                min_lat,
                max_lat,
                min_lon,
                max_lon,
            ],
        )

        column_names = [
            item[0]
            for item in cursor.description
        ]

        seen = set()
        output = []

        while True:
            rows = cursor.fetchmany(batch_size)

            if not rows:
                break

            for values in rows:
                record = dict(
                    zip(column_names, values)
                )

                latitude_value = safe_float(
                    record.get("latitude")
                )

                longitude_value = safe_float(
                    record.get("longitude")
                )

                if (
                    latitude_value is None
                    or longitude_value is None
                ):
                    continue

                point = Point(
                    longitude_value,
                    latitude_value,
                )

                if not prepared_area.intersects(point):
                    continue

                dedupe_key = location_dedupe_key(
                    record
                )

                if dedupe_key in seen:
                    continue

                seen.add(dedupe_key)
                output.append(record)

        output.sort(
            key=lambda row: (
                str(row.get("state") or ""),
                clean_zip(row.get("zip")),
                str(row.get("city") or ""),
                normalize_for_match(
                    row.get("address_primary")
                ),
                str(row.get("location_id") or ""),
            )
        )

        return output

    finally:
        connection.close()
