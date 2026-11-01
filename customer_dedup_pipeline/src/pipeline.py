import csv
import json
import sqlite3
import uuid
import time
import logging

from pathlib import Path

# Other existing imports and functions

def run_pipeline(input_path, db_path="data/output/dedup.db", output_dir="data/output"):
    start_clock = time.perf_counter()
    run_id = str(uuid.uuid4())
    started_at = now_iso()

    input_path = Path(input_path)
    db_path = Path(db_path)
    output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = connect_db(db_path)

    try:
        # 1. Check input file
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # 2. Read CSV
        with input_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ValueError("Input CSV has no header")

            missing_columns = sorted(set(FIELDS) - set(reader.fieldnames))
            unexpected_columns = sorted(set(reader.fieldnames) - set(FIELDS))

            if missing_columns:
                raise ValueError(
                    "Unexpected schema: missing columns "
                    + ", ".join(missing_columns)
                )

            raw_rows = list(reader)

        # 3. Validate records
        valid = []
        rejects = []
        seen_ids = set()
        source_row_map = {}

        for row_number, raw in enumerate(raw_rows, start=2):
            row = {
                field: (raw.get(field) or "").strip()
                for field in FIELDS
            }

            reasons = validate_row(row)
            sid = row.get("source_record_id", "")

            if sid and sid in seen_ids:
                reasons.append("duplicate_source_record_id")

            if sid:
                seen_ids.add(sid)

            if reasons:
                rejects.append({
                    "source_file": str(input_path),
                    "source_row": row_number,
                    "source_record_id": sid,
                    "raw_json": json.dumps(raw),
                    "reject_reason": "|".join(reasons)
                })
            else:
                valid.append(row)
                source_row_map[sid] = row_number

        # 4. Exact duplicate detection
        groups = exact_clusters(valid)

        masters = []
        lineage = []

        for group in groups:
            merged, survivor_id = merge_cluster(group)
            master_id = deterministic_master_id(group)

            masters.append({
                "master_customer_id": master_id,
                **{
                    k: merged.get(k, "")
                    for k in BUSINESS_FIELDS + [
                        "created_at",
                        "updated_at"
                    ]
                },
                "survivor_source_record_id": survivor_id
            })

            for row in group:
                lineage.append({
                    "source_record_id": row["source_record_id"],
                    "master_customer_id": master_id
                })

        exact_merged = len(valid) - len(masters)

        # 5. Probable duplicate detection
        review_pairs = fuzzy_review_pairs(valid, groups)

        # 6. Prepare source records
        source_records = []

        for row in valid:
            source_records.append((
                row["source_record_id"],
                str(input_path),
                source_row_map[row["source_record_id"]],
                run_id,
                row["source_system"],
                row["first_name"],
                row["last_name"],
                row["email"],
                row["phone"],
                row["address"],
                row["city"],
                row["postal_code"],
                row["created_at"],
                row["updated_at"]
            ))

        # 7. Database operations
        # Delete child tables before parent tables.
        with con:
            tables = [
                "customer_lineage",
                "duplicate_review_queue",
                "rejected_records",
                "source_records",
                "master_customers"
            ]

            for table in tables:
                con.execute(f"DELETE FROM {table}")

            # Insert source records
            con.executemany(
                """
                INSERT INTO source_records
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                source_records
            )

            # Insert master customers
            con.executemany(
                """
                INSERT INTO master_customers
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        m["master_customer_id"],
                        m["first_name"],
                        m["last_name"],
                        m["email"],
                        m["phone"],
                        m["address"],
                        m["city"],
                        m["postal_code"],
                        m["created_at"],
                        m["updated_at"],
                        m["survivor_source_record_id"]
                    )
                    for m in masters
                ]
            )

            # Insert customer lineage
            con.executemany(
                """
                INSERT INTO customer_lineage
                VALUES (?, ?, ?)
                """,
                [
                    (
                        item["source_record_id"],
                        item["master_customer_id"],
                        run_id
                    )
                    for item in lineage
                ]
            )

            # Insert probable duplicate review pairs
            con.executemany(
                """
                INSERT INTO duplicate_review_queue
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item["source_record_id_1"],
                        item["source_record_id_2"],
                        item["similarity_score"],
                        item["match_reason"],
                        item["review_status"]
                    )
                    for item in review_pairs
                ]
            )

            # Insert rejected records
            con.executemany(
                """
                INSERT INTO rejected_records
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item["source_file"],
                        item["source_row"],
                        item["source_record_id"],
                        item["raw_json"],
                        item["reject_reason"]
                    )
                    for item in rejects
                ]
            )

        # 8. Generate output CSV files
        write_csv(
            output_dir / "master_customers.csv",
            masters,
            [
                "master_customer_id",
                "first_name",
                "last_name",
                "email",
                "phone",
                "address",
                "city",
                "postal_code",
                "created_at",
                "updated_at",
                "survivor_source_record_id"
            ]
        )

        write_csv(
            output_dir / "duplicate_review_queue.csv",
            review_pairs,
            [
                "source_record_id_1",
                "source_record_id_2",
                "similarity_score",
                "match_reason",
                "review_status"
            ]
        )

        write_csv(
            output_dir / "rejects.csv",
            rejects,
            [
                "source_file",
                "source_row",
                "source_record_id",
                "raw_json",
                "reject_reason"
            ]
        )

        # 9. Reconciliation report
        duration = round(time.perf_counter() - start_clock, 6)

        report = {
            "run_id": run_id,
            "status": "SUCCESS",
            "input_rows": len(raw_rows),
            "valid_rows": len(valid),
            "rejected_rows": len(rejects),
            "master_rows": len(masters),
            "exact_merged_rows": exact_merged,
            "review_pairs": len(review_pairs),
            "lineage_rows": len(lineage),
            "duration_seconds": duration,
            "schema_unexpected_columns": unexpected_columns,
            "checks": {
                "input_equals_valid_plus_rejected":
                    len(raw_rows) == len(valid) + len(rejects),

                "valid_equals_lineage":
                    len(valid) == len(lineage),

                "master_ids_unique":
                    len({
                        m["master_customer_id"]
                        for m in masters
                    }) == len(masters)
            }
        }

        report["checks"]["all_passed"] = all(
            report["checks"].values()
        )

        (output_dir / "reconciliation.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8"
        )

        # 10. Record successful pipeline run
        ended_at = now_iso()

        with con:
            con.execute(
                """
                INSERT INTO pipeline_runs
                (
                    run_id, input_file, status, started_at, ended_at,
                    input_rows, valid_rows, rejected_rows, master_rows,
                    exact_merged_rows, review_pairs, duration_seconds,
                    failure_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(input_path),
                    "SUCCESS",
                    started_at,
                    ended_at,
                    len(raw_rows),
                    len(valid),
                    len(rejects),
                    len(masters),
                    exact_merged,
                    len(review_pairs),
                    duration,
                    None
                )
            )

        LOG.info("Run %s completed: %s", run_id, report)

        return report

    except Exception as exc:
        con.rollback()

        ended_at = now_iso()
        duration = round(time.perf_counter() - start_clock, 6)

        try:
            with con:
                con.execute(
                    """
                    INSERT INTO pipeline_runs
                    (
                        run_id, input_file, status, started_at,
                        ended_at, duration_seconds, failure_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        str(input_path),
                        "FAILED",
                        started_at,
                        ended_at,
                        duration,
                        str(exc)
                    )
                )
        except sqlite3.Error:
            LOG.exception("Could not record failed pipeline run")

        LOG.exception("Pipeline failed; run_id=%s", run_id)
        raise

    finally:
        con.close()
