import re
from typing import Iterable

import requests


def parse_salary_range(text: str):
    if not text:
        return (None, None)
    raw = str(text).lower()
    nums = re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    if not nums:
        return (None, None)
    values = []
    for n in nums:
        val = float(n)
        if "k" in raw and val < 1000:
            val *= 1000
        values.append(int(val))
    if len(values) == 1:
        return (values[0], values[0])
    return (min(values), max(values))


def fetch_remoteok_jobs():
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    jobs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("position") or "")
        description = str(item.get("description") or "")
        if not title and not description:
            continue
        tags = item.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        if salary_min is not None:
            salary_min = _safe_int(salary_min)
        if salary_max is not None:
            salary_max = _safe_int(salary_max)
        if salary_min is None and salary_max is None:
            salary_min, salary_max = parse_salary_range(item.get("salary") or "")
        jobs.append(
            normalize_job(
                {
                    "source": "RemoteOK",
                    "title": title,
                    "company": str(item.get("company") or ""),
                    "description": description,
                    "location": str(item.get("location") or ""),
                    "apply_url": str(item.get("url") or item.get("apply_url") or ""),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "tags": tags,
                }
            )
        )
    return jobs


def fetch_remotive_jobs():
    url = "https://remotive.com/api/remote-jobs"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    jobs_raw = data.get("jobs") or []
    jobs = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        salary_min, salary_max = parse_salary_range(item.get("salary") or "")
        jobs.append(
            normalize_job(
                {
                    "source": "Remotive",
                    "title": item.get("title") or "",
                    "company": item.get("company_name") or "",
                    "description": item.get("description") or "",
                    "location": item.get("candidate_required_location") or "",
                    "apply_url": item.get("url") or "",
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "tags": item.get("category") or [],
                }
            )
        )
    return jobs


def normalize_job(job: dict) -> dict:
    tags = job.get("tags") or []
    if isinstance(tags, (list, tuple, set)):
        tags = [str(t) for t in tags if str(t).strip()]
    else:
        tags = [str(tags)] if str(tags).strip() else []
    return {
        "title": str(job.get("title") or ""),
        "company": str(job.get("company") or job.get("company_name") or ""),
        "description": str(job.get("description") or ""),
        "location": str(job.get("location") or job.get("candidate_required_location") or ""),
        "apply_url": str(job.get("apply_url") or job.get("url") or ""),
        "source": str(job.get("source") or ""),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "tags": tags,
    }


def dedupe_jobs(jobs: Iterable[dict]) -> list:
    seen = set()
    unique = []
    for job in jobs:
        url = (job.get("apply_url") or "").strip().lower()
        if url:
            key = url
        else:
            title = (job.get("title") or "").strip().lower()
            company = (job.get("company") or "").strip().lower()
            key = f"{title}|{company}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def filter_jobs_by_keywords(jobs: Iterable[dict], keywords: Iterable[str]) -> list:
    keywords = [str(k).strip().lower() for k in keywords if str(k).strip()]
    if not keywords:
        return list(jobs)
    matched = []
    for job in jobs:
        content = " ".join(
            [
                str(job.get("title") or ""),
                str(job.get("company") or ""),
                str(job.get("description") or ""),
                str(job.get("location") or ""),
                " ".join(str(t) for t in (job.get("tags") or [])),
            ]
        ).lower()
        if any(k in content for k in keywords):
            matched.append(job)
    return matched


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
