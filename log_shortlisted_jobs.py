import argparse

from job_utils import append_tracker_csv, read_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Append shortlisted jobs to the tracker CSV.")
    parser.add_argument("--shortlisted", default="shortlisted_jobs.json", help="Shortlisted jobs JSON")
    parser.add_argument(
        "--tracker",
        default="application_tracker.csv",
        help="CSV tracker to append to",
    )
    parser.add_argument("--status", default="Shortlisted", help="Status value to write")
    parser.add_argument("--notes", default="AI shortlisted", help="Notes to write")
    args = parser.parse_args()

    jobs = read_json(args.shortlisted, default=[])
    if not jobs:
        print(f"No shortlisted jobs found in {args.shortlisted}.")
        return 1

    append_tracker_csv(args.tracker, jobs, status=args.status, notes=args.notes)
    print("Tracker updated.")
    print(f"- Jobs appended: {len(jobs)}")
    print(f"- Tracker: {args.tracker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
