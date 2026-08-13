"""
Generation-safe Cloud Storage processing pattern.

Simplified public example based on the production fiber-mapping worker.

Cloud Storage notifications are at-least-once. The worker therefore associates
outputs and locks with the immutable source object generation.
"""

from __future__ import annotations

import json
import time

from google.api_core.exceptions import (
    Conflict,
    NotFound,
    PreconditionFailed,
)


def output_matches_source(
    blob,
    *,
    source_object: str,
    source_generation: str,
) -> bool:
    """
    Return True only when the existing output belongs to this exact source
    generation.
    """
    if not blob.exists():
        return False

    blob.reload()
    metadata = blob.metadata or {}

    if source_generation:
        return (
            metadata.get("source_generation")
            == source_generation
        )

    return (
        metadata.get("source_object")
        == source_object
    )


def acquire_generation_lock(
    lock_blob,
    *,
    bucket_name: str,
    object_name: str,
    generation: str,
    stale_after_seconds: int = 6 * 60 * 60,
) -> bool:
    """
    Atomically create a generation-specific lock.

    If a previous worker crashed, an old lock can be replaced after the stale
    threshold. Generation preconditions prevent two workers from winning the
    replacement race.
    """
    payload = {
        "bucket": bucket_name,
        "name": object_name,
        "generation": generation,
        "started_at_unix": time.time(),
    }

    def create_lock():
        lock_blob.upload_from_string(
            json.dumps(payload),
            content_type="application/json",
            if_generation_match=0,
        )

    try:
        create_lock()
        return True

    except (PreconditionFailed, Conflict):
        pass

    try:
        lock_blob.reload()

        existing_blob_generation = (
            lock_blob.generation
        )

        existing_payload = json.loads(
            lock_blob.download_as_text() or "{}"
        )

        started_at = float(
            existing_payload.get(
                "started_at_unix",
                0,
            )
            or 0
        )

        age = max(
            0,
            time.time() - started_at,
        )

        if (
            started_at
            and age <= stale_after_seconds
        ):
            return False

        lock_blob.delete(
            if_generation_match=(
                existing_blob_generation
            )
        )

        create_lock()

        return True

    except (
        PreconditionFailed,
        Conflict,
        NotFound,
    ):
        # Another worker changed the lock while this instance was inspecting
        # it.
        return False


def process_storage_event(
    *,
    event: dict,
    storage_client,
    run_pipeline,
):
    """
    Public-safe orchestration example.

    `run_pipeline()` is injected so this file focuses on generation safety and
    output semantics rather than the private spatial implementation.
    """
    bucket_name = str(
        event.get("bucket") or ""
    )

    object_name = str(
        event.get("name") or ""
    )

    generation = str(
        event.get("generation") or ""
    )

    if (
        not bucket_name
        or not object_name
        or not object_name.lower().endswith(
            (".kml", ".kmz")
        )
    ):
        return

    bucket = storage_client.bucket(
        bucket_name
    )

    base_name = object_name.rsplit(".", 1)[0]

    json_blob = bucket.blob(
        f"{base_name}.locations.json"
    )

    csv_blob = bucket.blob(
        f"{base_name}.locations.csv"
    )

    # CSV is the completion marker for this exact source generation.
    if output_matches_source(
        csv_blob,
        source_object=object_name,
        source_generation=generation,
    ):
        return

    lock_name = (
        f".locks/{object_name}.{generation}.lock"
        if generation
        else f".locks/{object_name}.lock"
    )

    lock_blob = bucket.blob(lock_name)

    if not acquire_generation_lock(
        lock_blob,
        bucket_name=bucket_name,
        object_name=object_name,
        generation=generation,
    ):
        return

    try:
        result = run_pipeline(
            bucket_name=bucket_name,
            object_name=object_name,
            generation=generation,
        )

        metadata = {
            "source_object": object_name,
            "source_generation": generation,
            "record_count": str(
                len(result["records"])
            ),
        }

        # JSON first: diagnostic/intermediate artifact.
        json_blob.metadata = metadata

        json_blob.upload_from_string(
            json.dumps(
                result["records"],
                indent=2,
            ),
            content_type="application/json",
        )

        # CSV last: completion marker.
        csv_blob.metadata = metadata

        csv_blob.upload_from_string(
            result["csv_text"],
            content_type="text/csv",
        )

    finally:
        try:
            lock_blob.delete()
        except NotFound:
            pass
