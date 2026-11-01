# Data Dictionary

## Input: customers.csv

| Column | Type | Required | Meaning |
|---|---|---:|---|
| source_record_id | string | Yes | Unique source-row identifier |
| source_system | string | No | Source name: crm, web, legacy |
| first_name | string | Yes | Customer first name |
| last_name | string | Yes | Customer last name |
| email | string | No | Email identifier |
| phone | string | No | Phone identifier |
| address | string | No | Street address |
| city | string | No | City |
| postal_code | string | No | Postal/ZIP code |
| created_at | ISO-8601 string | No | Source creation timestamp |
| updated_at | ISO-8601 string | Yes | Source update timestamp |

## Target entities

- `master_customers`: one row per exact-match cluster; deterministic `master_customer_id`.
- `customer_lineage`: one row per valid source record, linking it to a master.
- `duplicate_review_queue`: probable pairs requiring human decision; PENDING by default.
- `rejected_records`: invalid source rows with original JSON, file, row number, and reason.
- `source_records`: validated input snapshot with source file and row metadata.
- `pipeline_runs`: run-level operational metrics and failure status.

## Grain and constraints

- Source grain: one source customer record per `source_record_id`.
- Master grain: one merged customer per exact-match cluster.
- `source_record_id` must be unique within an input file.
- `customer_lineage.source_record_id` is unique; each valid source record maps to exactly one master.
- `master_customer_id` is primary key.
- Probable duplicate pairs are not merged until reviewed.
