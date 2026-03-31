import argparse
import csv
import time
import webbrowser


def main() -> int:
    parser = argparse.ArgumentParser(description="Open application links or search queries.")
    parser.add_argument("--tracker", default="application_tracker.csv", help="Tracker CSV")
    parser.add_argument("--status", default="Shortlisted", help="Status filter")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between tabs in seconds")
    parser.add_argument("--open", action="store_true", help="Actually open links in browser")
    args = parser.parse_args()

    jobs_to_open = []
    try:
        with open(args.tracker, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == args.status:
                    jobs_to_open.append(row)
    except FileNotFoundError:
        print(f"Tracker not found: {args.tracker}")
        return 1

    print(f"Found {len(jobs_to_open)} job(s) with status '{args.status}'.")
    if not jobs_to_open:
        return 0

    for job in jobs_to_open:
        title = job.get("job_title") or ""
        company = job.get("company") or ""
        apply_link = job.get("apply_link") or ""
        if apply_link:
            target = apply_link
            label = "Apply link"
        else:
            query = f"{title} {company} job".strip().replace(" ", "+")
            target = f"https://www.google.com/search?q={query}"
            label = "Search link"

        print(f"{label}: {title} at {company}")
        print(target)

        if args.open:
            webbrowser.open(target)
            time.sleep(args.delay)

    print("Done. No applications were submitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
