import argparse

import requests

from job_utils import (
    dedupe_jobs,
    fetch_remoteok_jobs,
    fetch_remotive_jobs,
    filter_jobs_by_keywords,
    keywords_from_profile,
    read_json,
    write_json,
)


def _parse_keywords(value: str) -> list:
    if not value:
        return []
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch jobs from public APIs.")
    parser.add_argument("--resume-profile", default="resume_profile.json", help="Resume profile JSON")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords")
    parser.add_argument("--sources", default="remoteok,remotive", help="Sources: remoteok,remotive")
    parser.add_argument("--out", default="jobs.json", help="Output JSON file")
    parser.add_argument("--limit", type=int, default=200, help="Max jobs to keep after filtering")
    args = parser.parse_args()

    profile = read_json(args.resume_profile, default={}) or {}
    keywords = _parse_keywords(args.keywords) or keywords_from_profile(profile)
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    jobs = []
    if "remoteok" in sources:
        try:
            jobs.extend(fetch_remoteok_jobs())
        except requests.RequestException as exc:
            print(f"RemoteOK fetch failed: {exc}")
    if "remotive" in sources:
        try:
            jobs.extend(fetch_remotive_jobs())
        except requests.RequestException as exc:
            print(f"Remotive fetch failed: {exc}")

    jobs = dedupe_jobs(jobs)
    jobs = filter_jobs_by_keywords(jobs, keywords)
    if args.limit and len(jobs) > args.limit:
        jobs = jobs[: args.limit]

    write_json(args.out, jobs)

    print("Job search complete.")
    print(f"- Sources: {', '.join(sources) if sources else 'none'}")
    print(f"- Keywords: {', '.join(keywords) if keywords else 'none'}")
    print(f"- Jobs saved: {len(jobs)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
