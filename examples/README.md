# Fiber Service Area Mapping Pipeline — Public Code Examples

This folder contains simplified, sanitized examples based on implementation patterns used in the private production fiber-mapping pipeline.

The production workflow takes KML or KMZ service-area geometry, converts it into usable spatial boundaries, identifies address locations that fall inside those boundaries, normalizes and enriches the matched records, and produces structured output for downstream mapping, marketing, sales, and operational systems.

These examples are intended to show how I approached the spatial processing, large-dataset querying, address normalization, cloud execution, cost controls, and export workflow without publishing proprietary service areas, licensed reference data, internal import schemas, API credentials, or company-specific business logic.

These are representative examples rather than copies of the production codebase.

---

## Included Examples

### [`kml-geometry-processing.py`](kml-geometry-processing.py)

Demonstrates how KML and KMZ service-area files are converted into usable geometry before any address matching takes place.

Real-world KML files are not always made up of simple polygons. A service area may contain polygons, open LineStrings, Points, invalid geometry, or multiple disconnected pieces.

The geometry layer converts those different inputs into valid Shapely polygons that can be used by the rest of the pipeline.

**Demonstrates:**

- KMZ archive extraction
- KML parsing
- XML namespace handling
- Polygon extraction
- Geometry validation and repair
- `MultiPolygon` handling
- `GeometryCollection` handling
- LineString buffering
- Point buffering
- CRS transformation with `pyproj`
- Shapely geometry processing
- Combining multiple service-area geometries

Conceptually:

```text
KML / KMZ
    ↓
Read Placemark Geometry
    ↓
Polygon / LineString / Point
    ↓
Repair or Buffer
    ↓
Convert to WGS84 Polygon
    ↓
Combine Geometry
    ↓
Service Area
```

One important distinction is that LineStrings are not closed into rings before buffering. They remain open paths and are buffered in a projected coordinate system so distance can be handled in meters.

---

### [`duckdb-fabric-polygon-extract.py`](duckdb-fabric-polygon-extract.py)

Demonstrates the primary spatial-extraction pattern used against a large DuckDB-backed address dataset.

Loading every reference location into Python and testing every point against the service area would be unnecessarily expensive.

Instead, the workflow uses two stages.

First, DuckDB reduces the dataset using the service area's geographic bounding box.

Then Python performs the exact point-in-polygon check against the resulting candidates using a prepared Shapely geometry.

```text
Large Reference Dataset
        ↓
Service Area Bounding Box
        ↓
DuckDB SQL Filter
        ↓
Smaller Candidate Set
        ↓
Shapely Point-in-Polygon
        ↓
Matched Locations
```

**Demonstrates:**

- Read-only DuckDB access
- Defensive schema inspection
- Dynamic column handling
- Bounding-box prefiltering
- Parameterized SQL
- Safe numeric conversion
- Batched result streaming
- Prepared Shapely geometries
- Exact spatial intersection testing
- Official-location-ID deduplication
- Address-based fallback deduplication
- Stable output ordering

The query streams results in batches so large candidate sets do not have to be loaded into Python memory all at once.

---

### [`address-normalization.py`](address-normalization.py)

Demonstrates the address cleanup layer used before comparison, deduplication, and export.

Address data from different sources may represent the same location using slightly different formatting.

For example:

```text
101 Sample Road
101 SAMPLE RD
101 Sample Rd.
```

A small deterministic normalization layer helps reduce those differences without attempting to completely rewrite the source address.

**Demonstrates:**

- USPS-style street suffix normalization
- Case normalization
- Punctuation cleanup
- Match-key generation
- House-number extraction
- ZIP-code cleanup
- Safe numeric parsing
- Canonical address keys
- Address-based fallback deduplication

Authoritative location identifiers are preferred when they exist. Address matching is used as a fallback rather than replacing the official identifier.

---

### [`cost-controlled-geocode-fallback.py`](cost-controlled-geocode-fallback.py)

Demonstrates an optional fallback for evaluating parts of a service area that do not already have nearby matched reference locations.

External geocoding can become expensive very quickly if every point in a large polygon is submitted to an API.

The fallback therefore applies several checks before making a request.

```text
Service Area
      ↓
Generate Sample Grid
      ↓
Near Existing Matched Location?
   /                \
 Yes                 No
  ↓                   ↓
Skip            Reverse Geocode
                       ↓
              Returned Point Still
              Inside Service Area?
                   /       \
                 No         Yes
                 ↓           ↓
               Skip       Add If Unique
```

**Demonstrates:**

- Polygon grid generation
- Latitude-aware grid spacing
- `STRtree` spatial indexing
- Nearest-neighbor searches
- Haversine distance
- Skip-radius logic
- Hard API request caps
- Request throttling
- Polygon revalidation
- Duplicate-address prevention
- Cost-aware fallback design

This fallback is optional and intentionally bounded. It is not used as an uncontrolled replacement for the primary reference dataset.

---

### [`generation-safe-cloud-worker.py`](generation-safe-cloud-worker.py)

Demonstrates how the processing pipeline handles repeated Cloud Storage events and concurrent executions.

Cloud Storage events can be delivered more than once, and a file can also be replaced with a newer object generation using the same filename.

The worker therefore tracks the immutable source generation rather than assuming that a filename uniquely identifies one processing job.

```text
Cloud Storage Event
        ↓
Object + Generation
        ↓
Output Already Exists
for This Generation?
     /          \
   Yes           No
    ↓             ↓
  Stop       Acquire Lock
                  ↓
              Run Pipeline
                  ↓
               Write Output
```

**Demonstrates:**

- Cloud event validation
- Source object generations
- Generation-specific processing identity
- Output/source lineage metadata
- Atomic lock creation
- Duplicate-event protection
- Stale-lock detection
- Safe stale-lock replacement
- Concurrent-worker protection
- Completion-marker semantics
- Cleanup handling

The lock is created conditionally so two workers cannot both successfully claim the same processing job.

---

### [`structured-export.py`](structured-export.py)

Demonstrates how matched reference records are converted into a stable output schema.

The spatial-matching layer may contain source-specific field names and diagnostic information. The export layer separates that internal representation from the final structure used downstream.

**Demonstrates:**

- Explicit output schemas
- Stable field ordering
- Census block GEOID parsing
- Reference-location field mapping
- Coordinate precision control
- ZIP cleanup
- JSON serialization
- CSV generation
- Extra-field exclusion
- Consistent downstream output

The public example exports:

```text
location_id
address_1
address_2
city
state
zip
latitude
longitude
census_state
census_county
census_tract
census_block
bsl_flag
building_type
land_use_type
unit_count
fabric_release
verification_source
```

---

### [`sample-output.csv`](sample-output.csv)

Provides a synthetic example of the data produced by the public structured-export example.

The values are intentionally fictional and should not be interpreted as official FCC building-type, land-use, or classification codes.

The file exists to demonstrate the structure of the output rather than provide real location data.

**Demonstrates:**

- Final field ordering
- Location identifiers
- Normalized addresses
- Coordinates
- Census geography
- Building and land-use fields
- BSL information
- Unit counts
- Reference-data release tracking
- Verification source

---

## Architecture Represented

Together, the examples represent the main stages of the spatial-processing pipeline.

```text
KML / KMZ Service Area
        ↓
Parse Geometry
        ↓
Repair / Buffer / Normalize
        ↓
Combined Service Polygon
        ↓
Calculate Bounding Box
        ↓
DuckDB Candidate Query
        ↓
Stream Candidate Records
        ↓
Exact Shapely Point-in-Polygon
        ↓
Deduplicate Locations
        ↓
Normalize Address Data
        ↓
Map Reference Fields
        ↓
Structured JSON + CSV
```

The database and geometry layers have separate responsibilities.

```text
DuckDB
  ↓
Fast Candidate Reduction

Shapely
  ↓
Exact Geographic Decision
```

DuckDB determines which records are worth testing.

Shapely determines whether those locations actually fall inside the service area.

---

## Optional Coverage Fallback

The production architecture can also evaluate portions of a service area that do not already have nearby matched reference locations.

```text
Service Area
      +
Matched Locations
      ↓
Generate Sample Points
      ↓
Spatial Nearest-Neighbor Check
      ↓
Uncovered Sample Point
      ↓
Reverse Geocode
      ↓
Validate Returned Coordinates
      ↓
Still Inside Polygon?
      ↓
Deduplicate
      ↓
Add Fallback Location
```

The process includes request caps and distance-based filtering so external API use remains controlled.

---

## Cloud Processing Flow

The production pipeline can run automatically when a KML or KMZ file is uploaded.

```text
KML / KMZ Upload
        ↓
Cloud Storage Event
        ↓
Source Generation Check
        ↓
Existing Completed Output?
     /              \
   Yes               No
    ↓                 ↓
  Stop          Processing Lock
                       ↓
                 Geometry Parsing
                       ↓
                 Spatial Extraction
                       ↓
                   Enrichment
                       ↓
                   Write JSON
                       ↓
                   Write CSV
                       ↓
                    Complete
```

The JSON output is written first.

The CSV is written last and acts as the completion marker for that source generation.

That ordering allows the worker to distinguish a completed run from one that stopped partway through processing.

---

## Selected Engineering Decisions

### Bounding Box Before Exact Spatial Matching

The service-area bounding box is used to reduce the number of records retrieved from the reference database.

Only that candidate set is passed through the more exact Shapely spatial test.

This avoids performing Python geometry operations against the entire dataset.

---

### Stream Large Result Sets

DuckDB results are processed in batches rather than calling a single operation that loads the full candidate result into memory.

This allows the same workflow to handle larger service areas more predictably.

---

### Prefer Authoritative Location IDs

When an official reference-location identifier is available, it is used as the primary deduplication key.

Normalized address matching is used only as a fallback when the identifier is unavailable.

---

### Repair Geometry Before Matching

Invalid geometry is repaired before it enters the spatial-matching stage.

This prevents malformed polygons from silently creating incorrect point-in-polygon results.

---

### Use Projected Coordinates for Buffers

Buffer distances represent real-world distances in meters.

LineStrings and Points are therefore transformed into a projected CRS before buffering and transformed back to geographic coordinates afterward.

---

### Keep External API Usage Bounded

The optional geocoding fallback includes:

- Minimum distance from existing matched locations
- Request caps
- Request delays
- Polygon validation
- Duplicate detection

This allows an external service to supplement the dataset without turning it into the primary source or creating uncontrolled request volume.

---

### Track the Exact Source Generation

A filename alone is not enough to identify an immutable Cloud Storage object.

The processing workflow associates outputs with the exact uploaded generation so a replacement file can be processed even if it uses the same object name.

---

### Write the Completion Artifact Last

Intermediate output may exist even if processing does not finish successfully.

Writing the final CSV last provides a simple completion signal for the exact source generation.

---

## Why These Examples Are Included

The production pipeline needed to solve problems that go beyond simply opening a KMZ file or running a spatial query.

Examples include:

- KML files containing different geometry types
- Invalid or fragmented polygons
- Open network paths represented as LineStrings
- Large address datasets
- Reducing spatial workload before exact testing
- Streaming large candidate sets
- Handling inconsistent source data types
- Deduplicating locations reliably
- Normalizing addresses for downstream use
- Controlling external geocoding costs
- Handling repeated cloud events
- Protecting against concurrent processing
- Recovering from stale processing locks
- Tracking data lineage to the original uploaded file
- Producing a predictable downstream schema

These examples show selected implementation patterns I used to address those problems.

---

## Public-Safe Scope

The examples intentionally remove, rename, or generalize production-specific information, including:

- Company names
- Production Cloud Storage bucket names
- Production database paths
- Internal import column names
- Internal system identifiers
- Real service-area names
- Real addresses
- Licensed reference records
- API keys and credentials
- Production database table names
- Territory identifiers
- Company-specific classification rules
- Internal workflow configuration
- Full retry and migration logic

All location records in the public examples are synthetic.

The complete production implementation, service-area data, and reference datasets remain private.

---

## Production Source

The full production mapping pipeline is maintained privately because it contains proprietary service-area information, internal address data, licensed reference data, production infrastructure configuration, credentials, and company-specific output requirements.

These examples are portfolio representations of selected implementation patterns.

They are intended to show how I built the spatial-processing workflow without exposing the production environment or underlying operational datasets.
