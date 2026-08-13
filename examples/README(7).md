# Example Output

`sample-output.csv` is a synthetic example showing the type of structured address-level data produced by the fiber service-area mapping pipeline.

The records, coordinates, Census identifiers, ZIP code, and territory name in this example are fabricated for portfolio use. They do not represent customers, actual serviceable addresses, production service areas, or internal company data.

The production output schema may contain additional company-specific fields that are intentionally not included in this public repository.

## Example Flow

```text
KMZ service-area polygon
        +
DuckDB address coordinates
        +
Census reference data
        ↓
Spatial point-in-polygon matching
        ↓
Census enrichment
        ↓
Validation / normalization
        ↓
sample-output.csv
```

The example demonstrates the main output concepts:

- Stable location identifier
- Structured address fields
- Latitude and longitude
- Census geography fields
- Assigned service-area / territory value
