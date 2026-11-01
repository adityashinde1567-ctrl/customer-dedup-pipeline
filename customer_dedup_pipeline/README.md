# Customer Data Deduplication & Master Data Management Pipeline

A local, reproducible data-engineering project. It validates customer CSVs, detects exact duplicates, identifies probable duplicates for manual review, applies deterministic survivorship, and preserves source-to-master lineage.

## Quick start

Requirements: Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Run the included sample:
python run_pipeline.py --input data/input/customers.csv --db data/output/dedup.db

# Generate a larger deterministic dataset (100,000 source rows plus duplicate/reject examples):
python generate_data.py --rows 100000 --seed 42
python run_pipeline.py --input data/input/customers.csv --db data/output/dedup.db

# Tests:
pytest -q
```

## Architecture

```text
CSV -> schema checks -> row validation -> normalization
   -> exact duplicate clusters -> survivorship + deterministic master IDs
   -> source-to-master lineage
   -> fuzzy candidate pairs -> manual review queue
   -> SQLite tables + CSV exports + reconciliation JSON
Invalid rows -> rejects/quarantine table and rejects.csv
```

## Matching rules

**Exact:** records sharing a non-empty normalized email OR normalized phone are merged transitively. Empty identifiers never match.

**Probable:** names with similarity >= 0.88 and a shared postal code or last seven phone digits are sent to a review queue. They are never automatically merged.

**Survivorship:** highest completeness, then latest `updated_at`, then source priority (`crm` > `web` > `legacy`), then lexicographically smallest source ID. Missing business fields are filled from other cluster members in the same ranking order. Cluster creation date is earliest; update date is latest.

**Master ID:** `M-` + first 12 uppercase hex characters of SHA-256 over sorted source record IDs.

## Outputs

- `data/output/master_customers.csv`
- `data/output/duplicate_review_queue.csv`
- `data/output/rejects.csv`
- `data/output/reconciliation.json`
- `data/output/dedup.db`

SQLite tables: `pipeline_runs`, `source_records`, `master_customers`, `customer_lineage`, `duplicate_review_queue`, `rejected_records`.

## Data assumptions and limitations

Required fields: `source_record_id`, `first_name`, `last_name`, `updated_at`. Input schema is defined in `src/pipeline.py`. Timestamps use ISO-8601; timezone-less values are interpreted as UTC. Email and phone are identifiers only when populated. Shared family/business contact details can create false positives; review business rules before production use. Fuzzy matching is a review aid. The starter is snapshot-based, not streaming CDC.

Reruns rebuild snapshot output tables transactionally and retain run history. Re-running the same input creates stable master IDs and output content. For backfills, pass the full source snapshot.

## Performance and scale

Exact matching uses hash maps/union-find rather than comparing every pair. Fuzzy matching blocks by postal code and phone suffix to reduce candidate comparisons. The report captures elapsed runtime. For larger production workloads, consider more selective blocking, batch loading, an optimized similarity library, and partitioned processing.

## Design trade-offs

This project deliberately uses SQLite and the Python standard library to be easy to run and review within a 72-hour assignment. It favors explainable deterministic rules over ML-based entity resolution. Review-queue pairs are not merged, avoiding risky false-positive merges. PII access controls, encryption, retention, human review UI, CDC, and alerting are production extensions.
