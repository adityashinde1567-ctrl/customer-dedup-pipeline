import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = [
    "source_record_id","source_system","first_name","last_name","email",
    "phone","address","city","postal_code","created_at","updated_at"
]

def generate(path, rows=1000, seed=42):
    random.seed(seed)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    first_names = ["Aarav","Isha","Rohan","Priya","Neha","Arjun","Maya","Kabir","Anaya","Vikram","Sara","Dev"]
    last_names = ["Shinde","Patil","Kulkarni","Joshi","Deshmukh","Mehta","Shah","Khan","Rao","Pawar"]
    locations = [("Pune","411001"),("Mumbai","400001"),("Nashik","422001"),("Nagpur","440001")]
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    records = []
    for i in range(rows):
        first, last = random.choice(first_names), random.choice(last_names)
        city, postal = random.choice(locations)
        records.append({
            "source_record_id": f"SRC{i+1:07d}",
            "source_system": random.choice(["crm","web","legacy"]),
            "first_name": first, "last_name": last,
            "email": f"{first}.{last}.{i+1}@example.com".lower(),
            "phone": f"+91{random.randint(7000000000, 9999999999)}",
            "address": f"{random.randint(1,250)} MG Road",
            "city": city, "postal_code": postal,
            "created_at": (now-timedelta(days=random.randint(1,1000))).isoformat(),
            "updated_at": (now-timedelta(days=random.randint(0,30))).isoformat()
        })
    # Exact duplicates: copy an existing email and phone under a new source ID.
    for j in range(max(1, rows // 50)):
        source = records[random.randrange(len(records))]
        duplicate = dict(source)
        duplicate["source_record_id"] = f"DUP{j+1:06d}"
        duplicate["source_system"] = "web"
        duplicate["updated_at"] = (now + timedelta(days=1)).isoformat()
        records.append(duplicate)

    # Deliberately invalid example for quarantine.
    records.append({
        "source_record_id":"BAD000001", "source_system":"web",
        "first_name":"", "last_name":"Missing", "email":"bad-email",
        "phone":"123", "address":"", "city":"", "postal_code":"",
        "created_at":"", "updated_at":"not-a-date"
    })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    return len(records)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="data/input/customers.csv")
    args = parser.parse_args()
    print(f"Generated {generate(args.output, args.rows, args.seed)} rows at {args.output}")
