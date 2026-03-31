import csv
import json
import os
import re
import subprocess
from typing import Iterable

import pdfplumber
import requests

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


def clean_text(text: str) -> str:
    if not text:
        return ""
    return text.replace("\x00", "").replace("\r", " ").replace("\n", " ")


def limit_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def read_resume_text(pdf_path: str) -> str:
    resume_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                resume_text += page_text + "\n"
    return resume_text.strip()


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*", "", text).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def safe_json_loads(text: str):
    if not text:
        return None
    text = _strip_code_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None


def extract_resume_profile(resume_text: str, model: str = DEFAULT_MODEL) -> dict:
    model = model or DEFAULT_MODEL
    prompt = f"""
You are an AI that extracts structured data from resumes.
Return ONLY valid JSON with these keys:
- name (string)
- skills (list of strings)
- experience_years (number)
- target_roles (list of strings)

Resume text:
{resume_text}
"""
    output = run_ollama_prompt(prompt, model=model)
    data = safe_json_loads(output) or {}
    if not isinstance(data, dict):
        data = {}
    name = str(data.get("name") or data.get("full_name") or "").strip()
    skills = _ensure_list_of_str(data.get("skills") or [])
    target_roles = _ensure_list_of_str(
        data.get("target_roles") or data.get("job_roles") or []
    )
    experience_years = _safe_int(data.get("experience_years") or 0)
    return {
        "name": name,
        "skills": skills,
        "experience_years": experience_years,
        "target_roles": target_roles,
    }


def write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


def read_json(path: str, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


def keywords_from_profile(profile: dict) -> list:
    keywords = []
    for key in ("skills", "target_roles", "job_roles"):
        values = profile.get(key) or []
        keywords.extend(values)
    return [str(k).strip().lower() for k in keywords if str(k).strip()]


def run_ollama_prompt(prompt: str, model: str = DEFAULT_MODEL) -> str:
    model = model or DEFAULT_MODEL
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
    except FileNotFoundError:
        return ""
    return (result.stdout or "").strip()


def parse_first_int(text: str):
    match = re.search(r"\d+", text or "")
    if not match:
        return None
    return _safe_int(match.group(0))


def heuristic_match_score(resume_text: str, job_description: str) -> int:
    resume_words = _tokenize(resume_text)
    job_words = _tokenize(job_description)
    if not resume_words or not job_words:
        return 0
    overlap = resume_words & job_words
    denom = min(len(resume_words), len(job_words))
    if denom == 0:
        return 0
    score = int(100 * len(overlap) / denom)
    return max(0, min(100, score))


def score_job_match(resume_text: str, job_description: str, model: str = DEFAULT_MODEL) -> int:
    model = model or DEFAULT_MODEL
    resume_short = limit_text(clean_text(resume_text), 4000)
    job_short = limit_text(clean_text(job_description), 1500)
    prompt = f"""
Score how well this resume matches the job on a scale of 0 to 100.
Return ONLY the number.

RESUME:
{resume_short}

JOB:
{job_short}
"""
    output = run_ollama_prompt(prompt, model=model)
    score = parse_first_int(output)
    if score is None:
        return heuristic_match_score(resume_text, job_description)
    return max(0, min(100, score))


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    value = value.strip("._")
    return value or "output"


def append_tracker_csv(
    csv_path: str,
    jobs: Iterable[dict],
    status: str,
    notes: str,
) -> None:
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["job_title", "company", "apply_link", "status", "notes"])
        for job in jobs:
            writer.writerow(
                [
                    job.get("title") or "",
                    job.get("company") or "",
                    job.get("apply_url") or "",
                    status,
                    notes,
                ]
            )


def _ensure_list_of_str(value) -> list:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _tokenize(text: str) -> set:
    if not text:
        return set()
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", text.lower()))
