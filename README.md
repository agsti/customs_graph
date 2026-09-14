# Customs Tier-N Discovery

This prototype finds upstream supplier candidates from customs manifests. Starting from a known consignee, it follows shipments backwards: each shipper is a potential supplier to that consignee.

It normalizes company names, applies the embedded registry facts, excludes known intra-group and pass-through relationships, scores the remaining relationships, and walks upstream through every supported tier.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

Install the project dependencies:

```bash
uv sync --dev
```

## Run

Run the supplied example from the repository root:

```bash
uv run tier-n-discovery \
  --customs customs_extract.csv \
  --root "Solstice Materials Co" \
  --entity-match-threshold 0.94 \
  --output-dir output
```

The graph opens in the default browser. To generate files without opening a browser, add `--no-open-browser`.

The only runtime input is the customs CSV. The small set of facts extracted from `corporate_registry_notes.txt` is intentionally embedded in the application as provenance-backed static data.

## Output

The command writes these files to `output/`:

- `tier_n_candidates.csv` — a compact list of candidate company name, tier depth, and confidence.
- `tier_n_candidates.json` — candidates plus strongest paths and supporting BOL/product evidence.
- `tier_n_graph.html` — interactive company graph; hover nodes and edges for details.
- `parked_shipments.json` — excluded relationships and data-quality issues with reasons.
- `cycles.json` — detected circular paths.

Candidate confidence is labeled High (`>= 0.75`), Medium (`>= 0.45`), or Low. Confidence compounds as the path gets deeper, so deeper candidates should be treated as weaker signals.

## Customs CSV format

The parser expects this header row:

```text
bill_of_lading_id,shipment_date,shipper_name,shipper_country,consignee_name,consignee_country,product_description,weight_kg,vessel_name
```

`bill_of_lading_id`, `shipment_date`, `shipper_name`, `consignee_name`, and `product_description` are required. Dates accept ISO format (`YYYY-MM-DD`) or day-first slash format (`DD/MM/YYYY`). Malformed rows are recorded as data-quality issues while valid rows continue through the pipeline.

## Tests

```bash
uv run pytest -v
```
