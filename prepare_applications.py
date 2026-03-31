import argparse
import csv


def main() -> int:
    parser = argparse.ArgumentParser(description="List jobs ready to apply from the tracker CSV.")
    parser.add_argument("--tracker", default="application_tracker.csv", help="Tracker CSV")
    parser.add_argument("--status", default="Shortlisted", help="Status filter")
    args = parser.parse_args()

    prepared_jobs = []
    try:
        with open(args.tracker, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == args.status:
                    prepared_jobs.append(row)
    except FileNotFoundError:
        print(f"Tracker not found: {args.tracker}")
        return 1

    print(f"Found {len(prepared_jobs)} job(s) with status '{args.status}'.")
    if not prepared_jobs:
        return 0

    for job in prepared_jobs:
        print("-" * 40)
        print(f"Role    : {job.get('job_title')}")
        print(f"Company : {job.get('company')}")
        print(f"Apply   : {job.get('apply_link') or 'N/A'}")
        print("Status  : Ready to apply (manual)")
    print("-" * 40)
    print("Preparation complete. No applications were submitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
