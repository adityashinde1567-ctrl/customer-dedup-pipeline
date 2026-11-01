import argparse
import logging
from src.pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Customer deduplication pipeline")
    parser.add_argument("--input", default="data/input/customers.csv")
    parser.add_argument("--db", default="data/output/dedup.db")
    parser.add_argument("--output", default="data/output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    report = run_pipeline(args.input, args.db, args.output)
    print("\nPIPELINE REPORT")
    for key, value in report.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()
