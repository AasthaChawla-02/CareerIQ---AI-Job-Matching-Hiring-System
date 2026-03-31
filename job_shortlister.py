import argparse

from job_utils import append_tracker_csv, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Shortlist jobs based on match score.")
    parser.add_argument("--scored", default="scored_jobs.json", help="Input scored jobs JSON")
    parser.add_argument("--out", default="shortlisted_jobs.json", help="Output shortlisted JSON")
    parser.add_argument("--threshold", type=int, default=70, help="Score threshold")
    parser.add_argument(
        "--tracker",
        default="application_tracker.csv",
        help="CSV tracker to append to",
    )
    parser.add_argument(
        "--notes",
        default="AI shortlisted (match score >= threshold)",
        help="Notes column for tracker",
    )
    args = parser.parse_args()

    scored = read_json(args.scored, default=[])
    if not scored:
        print(f"No scored jobs found in {args.scored}.")
        return 1

    shortlisted = [j for j in scored if (j.get("match_score") or 0) >= args.threshold]
    write_json(args.out, shortlisted)
    append_tracker_csv(args.tracker, shortlisted, status="Shortlisted", notes=args.notes)

    print("Shortlisting complete.")
    print(f"- Scored jobs: {len(scored)}")
    print(f"- Shortlisted: {len(shortlisted)}")
    print(f"- JSON: {args.out}")
    print(f"- Tracker updated: {args.tracker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
