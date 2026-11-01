import csv
import json
from pathlib import Path
import pytest

from src.pipeline import FIELDS, run_pipeline

def write_input(path, rows, headers=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers or FIELDS)
        writer.writeheader()
        writer.writerows(rows)

def record(sid, first="Asha", last="Patil", email="", phone="", postal="411001",
           updated="2026-10-01T10:00:00+00:00", system="crm"):
    return {
        "source_record_id":sid, "source_system":system, "first_name":first,
        "last_name":last, "email":email, "phone":phone, "address":"MG Road",
        "city":"Pune", "postal_code":postal,
        "created_at":"2025-01-01T00:00:00+00:00", "updated_at":updated
    }

def execute(tmp_path, rows, headers=None):
    source = tmp_path / "input.csv"
    output = tmp_path / "out"
    db = tmp_path / "test.db"
    write_input(source, rows, headers)
    return run_pipeline(source, db, output), output

def test_happy_path_and_exact_duplicate(tmp_path):
    rows = [
        record("A1", email="asha@example.com", phone="9876543210"),
        record("A2", email="ASHA@example.com", phone="9876543210", system="web",
               updated="2026-10-02T10:00:00+00:00")
    ]
    report, out = execute(tmp_path, rows)
    assert report["input_rows"] == 2
    assert report["valid_rows"] == 2
    assert report["master_rows"] == 1
    assert report["exact_merged_rows"] == 1
    assert report["checks"]["all_passed"]
    with (out / "master_customers.csv").open() as f:
        assert len(list(csv.DictReader(f))) == 1

def test_empty_input(tmp_path):
    report, _ = execute(tmp_path, [])
    assert report["input_rows"] == 0
    assert report["master_rows"] == 0
    assert report["checks"]["all_passed"]

def test_missing_required_and_bad_timestamp_quarantined(tmp_path):
    bad = record("BAD")
    bad["first_name"] = ""
    bad["updated_at"] = "not-a-date"
    report, out = execute(tmp_path, [bad])
    assert report["rejected_rows"] == 1
    rejects = list(csv.DictReader((out / "rejects.csv").open()))
    assert "missing_required:first_name" in rejects[0]["reject_reason"]
    assert "invalid_timestamp:updated_at" in rejects[0]["reject_reason"]

def test_null_identifiers_do_not_match(tmp_path):
    rows = [record("N1"), record("N2")]
    rows[0]["email"] = rows[1]["email"] = ""
    rows[0]["phone"] = rows[1]["phone"] = ""
    report, _ = execute(tmp_path, rows)
    assert report["master_rows"] == 2

def test_probable_duplicate_goes_to_review_not_auto_merge(tmp_path):
    rows = [
        record("P1", first="Asha", last="Patil", phone="9876543210"),
        record("P2", first="Asha", last="Patil", phone="8876543210")
    ]
    report, out = execute(tmp_path, rows)
    assert report["master_rows"] == 2
    assert report["review_pairs"] == 1
    queue = list(csv.DictReader((out / "duplicate_review_queue.csv").open()))
    assert queue[0]["review_status"] == "PENDING"

def test_duplicate_source_key_second_row_rejected(tmp_path):
    rows = [record("D1", email="one@example.com"), record("D1", email="two@example.com")]
    report, _ = execute(tmp_path, rows)
    assert report["valid_rows"] == 1
    assert report["rejected_rows"] == 1

def test_invalid_email_and_phone_rejected(tmp_path):
    row = record("BAD2", email="not-an-email", phone="123")
    report, _ = execute(tmp_path, [row])
    assert report["rejected_rows"] == 1

def test_unexpected_schema_missing_column_fails(tmp_path):
    source = tmp_path / "bad_schema.csv"
    headers = [x for x in FIELDS if x != "email"]
    write_input(source, [record("X1")], headers)
    with pytest.raises(ValueError, match="Unexpected schema"):
        run_pipeline(source, tmp_path / "db.sqlite", tmp_path / "out")

def test_rerun_is_idempotent_for_outputs(tmp_path):
    rows = [record("R1", email="r@example.com"), record("R2", email="r@example.com")]
    source = tmp_path / "same.csv"
    write_input(source, rows)
    db, out = tmp_path / "db.sqlite", tmp_path / "out"
    first = run_pipeline(source, db, out)
    first_output = (out / "master_customers.csv").read_text()
    second = run_pipeline(source, db, out)
    second_output = (out / "master_customers.csv").read_text()
    assert first_output == second_output
    assert first["master_rows"] == second["master_rows"] == 1
