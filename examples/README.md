# Fiber Service Area Mapping Pipeline — Public Code Examples

This folder contains simplified, sanitized examples based on implementation patterns used in the private production fiber-mapping pipeline.

The production workflow accepts KML/KMZ service-area geometry, converts that geometry into valid Shapely polygons, identifies official address records that fall inside the footprint, enriches and normalizes the resulting records, and writes structured output for downstream use.

These examples are intended to show the engineering approach without publishing proprietary service areas, licensed reference data, internal import schemas, API credentials, or company-specific business logic.

They are representative examples rather than copies of the production codebase.

---

## Included Examples

### [`kml-geometry-processing.py`](kml-geometry-processing.py)

Shows how KML/KMZ geometry is parsed and normalized before spatial matching.

**Demonstrates:**

- KMZ extraction
- Namespace-independent KML parsing
- Polygon handling
- Geometry repair with `make_valid`
- MultiPolygon handling
- LineString buffering
- Point buffering
- Coordinate-reference transformations
- Combined service-area geometry

---

### [`duckdb-fabric-polygon-extract.py`](duckdb-fabric-polygon-extract.py)

Shows the main spatial-extraction pattern used against a large DuckDB-backed address dataset.

The database first reduces the search space with a bounding-box query. Python then performs the exact point-in-polygon test with a prepared Shapely geometry.

**Demonstrates:**

- Read-only DuckDB access
- Defensive schema inspection
- Bounding-box prefiltering
- Parameterized SQL
- Batched result streaming
- Prepared Shapely geometries
- Exact point-in-polygon testing
- Address/location deduplication
- Stable output ordering

---

### [`address-normalization.py`](address-normalization.py)

Shows the normalization helpers used to make address comparison and export more consistent.

**Demonstrates:**

- USPS-style street suffix normalization
- Match-key normalization
- House-number extraction
- ZIP cleanup
- Safe numeric parsing
- Canonical dedupe keys

---

### [`cost-controlled-geocode-fallback.py`](cost-controlled-geocode-fallback.py)

Shows the optional fallback pattern for sampling uncovered parts of a service area without allowing external geocoding costs to grow without limit.

**Demonstrates:**

- Grid generation inside polygons
- Spatial nearest-neighbor checks with `STRtree`
- Haversine distance
- Skip-radius logic
- Hard API request caps
- Request throttling
- Polygon revalidation after geocoding
- Duplicate-address prevention

---

### [`generation-safe-cloud-worker.py`](generation-safe-cloud-worker.py)

Shows how a Cloud Storage-triggered processing job can protect itself from duplicate delivery and stale concurrent executions.

**Demonstrates:**

- CloudEvent validation
- Source object generations
- Output/source lineage metadata
- Generation-specific processing locks
- Atomic lock creation
- Stale-lock replacement
- Completion-marker semantics
- Safe cleanup

---

### [`structured-export.py`](structured-export.py)

Shows how matched location records are transformed into a stable public-safe output schema and written as both JSON and CSV.

**Demonstrates:**

- Output-schema control
- Census GEOID parsing
- FCC/Fabric field mapping
- Stable field ordering
- JSON diagnostics
- CSV generation
- Source-lineage metadata
- Completion-marker ordering

---

## Architecture Represented

```text
KML / KMZ Service Area
        ↓
Parse Geometry
        ↓
Repair / Normalize
        ↓
Combined Polygon
        ↓
Bounding Box
        ↓
DuckDB Candidate Query
        ↓
Exact Point-in-Polygon Match
        ↓
Deduplicate
        ↓
Normalize / Enrich
        ↓
Structured JSON + CSV
```

An optional fallback can evaluate parts of the footprint that do not already have nearby matched reference locations.

```text
Matched Reference Points
        +
Service Area Polygon
        ↓
Generate Sample Points
        ↓
Nearest Existing Location?
    /              \
 Close              Not Close
  ↓                    ↓
Skip             Reverse Geocode
                       ↓
                Still Inside Polygon?
                       ↓
                  Add If Unique
```

The production worker also protects each uploaded object generation from duplicate processing.

```text
Cloud Storage Event
        ↓
Source Generation
        ↓
Existing Output for Same Generation?
        ↓
Generation-Specific Lock
        ↓
Run Spatial Pipeline
        ↓
Write JSON
        ↓
Write CSV Last
        ↓
CSV Acts as Completion Marker
```

---

## Why These Examples Are Included

The pipeline needed to solve several problems that go beyond simply opening a KMZ file.

Examples include:

- KML files containing different geometry types
- Invalid or fragmented polygons
- Large reference datasets that should not be loaded into memory all at once
- Reducing spatial workload before exact point-in-polygon testing
- Handling source fields whose data types may vary
- Deduplicating by official location ID when available
- Keeping address formatting stable enough for downstream matching
- Preventing optional external geocoding from becoming an uncontrolled cost
- Avoiding duplicate work from repeated cloud events
- Making output traceable to the exact uploaded source generation
- Producing a predictable import-ready schema

These examples show selected patterns used to solve those problems.

---

## Public-Safe Scope

The examples intentionally remove, rename, or generalize:

- Company names
- Production bucket names
- Production database paths
- Internal import column names
- Real service-area names
- Real addresses
- Licensed FCC Fabric records
- API keys and credentials
- Production table names
- Internal territory identifiers
- Company-specific classification rules
- Full operational retry and migration logic

The complete production implementation and datasets remain private.

These files are portfolio examples and are not intended to be drop-in replacements for the production pipeline.
