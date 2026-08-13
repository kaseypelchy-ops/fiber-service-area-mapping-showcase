"""
Structured public-safe export layer.

Simplified example based on the production pipeline.

Internal production column names are intentionally replaced with generic field
names.
"""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import Any


EXPORT_HEADERS = [
    "location_id",
    "address_1",
    "address_2",
    "city",
    "state",
    "zip",
    "latitude",
    "longitude",
    "census_state",
    "census_county",
    "census_tract",
    "census_block",
    "bsl_flag",
    "building_type",
    "land_use_type",
    "unit_count",
    "fabric_release",
    "verification_source",
]


def clean_zip(value: Any) -> str:
    match = re.search(
        r"\d{5}",
        str(value or ""),
    )

    return match.group(0) if match else ""


def split_block_geoid(
    value: Any,
) -> dict[str, str]:
    """
    Split a 15-digit Census block GEOID into state/county/tract/block pieces.
    """
    geoid = re.sub(
        r"\D",
        "",
        str(value or ""),
    )

    if geoid and len(geoid) < 15:
        geoid = geoid.zfill(15)

    return {
        "census_state": (
            geoid[0:2]
            if len(geoid) >= 2
            else ""
        ),
        "census_county": (
            geoid[2:5]
            if len(geoid) >= 5
            else ""
        ),
        "census_tract": (
            geoid[5:11]
            if len(geoid) >= 11
            else ""
        ),
        "census_block": (
            geoid[11:15]
            if len(geoid) >= 15
            else ""
        ),
    }


def make_export_row(
    record: dict[str, Any],
) -> dict[str, Any]:
    census = split_block_geoid(
        record.get("block_geoid")
    )

    return {
        "location_id":
            record.get("location_id") or "",

        "address_1":
            str(
                record.get("address_primary") or ""
            ).upper().strip(),

        "address_2":
            str(
                record.get("address_secondary") or ""
            ).upper().strip(),

        "city":
            str(
                record.get("city") or ""
            ).upper().strip(),

        "state":
            str(
                record.get("state") or ""
            ).upper().strip(),

        "zip":
            clean_zip(record.get("zip")),

        "latitude":
            round(float(record["latitude"]), 7),

        "longitude":
            round(float(record["longitude"]), 7),

        **census,

        "bsl_flag":
            record.get("bsl_flag") or "",

        "building_type":
            record.get("building_type_code") or "",

        "land_use_type":
            record.get("land_use_code") or "",

        "unit_count":
            record.get("unit_count") or "",

        "fabric_release":
            record.get("fabric_release") or "",

        "verification_source":
            "reference_polygon_match",
    }


def serialize_output(
    records: list[dict[str, Any]],
):
    """
    Produce both JSON and a stable CSV with explicit field ordering.
    """
    export_rows = [
        make_export_row(record)
        for record in records
    ]

    json_text = json.dumps(
        export_rows,
        indent=2,
    )

    csv_buffer = StringIO()

    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=EXPORT_HEADERS,
        extrasaction="ignore",
    )

    writer.writeheader()
    writer.writerows(export_rows)

    return {
        "records": export_rows,
        "json_text": json_text,
        "csv_text": csv_buffer.getvalue(),
    }
