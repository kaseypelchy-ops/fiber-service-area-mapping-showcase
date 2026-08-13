"""
Public-safe address normalization helpers.

These helpers are representative of the cleanup layer used before matching and
export. They are intentionally small and deterministic.
"""

from __future__ import annotations

import re
from typing import Any


USPS_SUFFIXES = {
    "STREET": "ST",
    "ROAD": "RD",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "PARKWAY": "PKWY",
    "HIGHWAY": "HWY",
}


def normalize_street_address(value: Any) -> str:
    """
    Apply a small USPS-style normalization without trying to rewrite the
    entire address.
    """
    words = str(value or "").upper().strip().split()

    if not words:
        return ""

    if words[-1] in USPS_SUFFIXES:
        words[-1] = USPS_SUFFIXES[words[-1]]

    return " ".join(words)


def normalize_for_match(value: Any) -> str:
    """
    Produce a stable comparison key for address matching.
    """
    text = str(value or "").upper().strip()

    text = re.sub(
        r"[^A-Z0-9 ]",
        " ",
        text,
    )

    for long_name, short_name in USPS_SUFFIXES.items():
        text = re.sub(
            rf"\b{re.escape(long_name)}\b",
            short_name,
            text,
        )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def extract_house_number(value: Any) -> str:
    match = re.match(
        r"^\s*([0-9]+[A-Z]?)\b",
        normalize_for_match(value),
    )

    return match.group(1) if match else ""


def clean_zip(value: Any) -> str:
    text = str(value or "").strip()

    match = re.search(r"\d{5}", text)

    if match:
        return match.group(0)

    digits = re.sub(r"\D", "", text)

    return digits[:5].zfill(5) if digits else ""


def safe_float(value: Any):
    try:
        if value in (None, ""):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def canonical_address_key(record: dict[str, Any]):
    """
    Address-based fallback identity used only when an authoritative location
    identifier is not available.
    """
    return (
        normalize_for_match(
            record.get("address_primary")
        ),
        normalize_for_match(
            record.get("city")
        ),
        str(record.get("state") or "")
        .upper()
        .strip(),
        clean_zip(record.get("zip")),
    )
