import requests
import streamlit as st
import subprocess
import pdfplumber
import tempfile
import re
import sqlite3
import secrets
import hashlib
from datetime import datetime

# ---------------- Tuning ----------------

MAX_RESUME_CHARS = 4000
MAX_JOB_CHARS = 1500
MAX_JOBS_TO_SCORE = 3
JOB_CACHE_TTL_SECONDS = 600
DB_PATH = "app.db"

# ---------------- Utility ----------------

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


def infer_work_mode(location_text, tags):
    location_text = (location_text or "").lower()
    tags_text = " ".join(tags) if isinstance(tags, list) else str(tags or "")
    text = f"{location_text} {tags_text}".lower()
    if "hybrid" in text:
        return "Hybrid"
    if "remote" in text or "anywhere" in text:
        return "Remote"
    if text.strip():
        return "On-site"
    return "Unknown"


def format_salary(job):
    min_salary = job.get("salary_min")
    max_salary = job.get("salary_max")
    if min_salary and max_salary:
        return f"${min_salary:,} - ${max_salary:,}"
    if min_salary and not max_salary:
        return f"${min_salary:,}+"
    if max_salary and not min_salary:
        return f"Up to ${max_salary:,}"
    return "Not listed"


def salary_in_range(job, min_salary, max_salary, include_unknown):
    job_min = job.get("salary_min")
    job_max = job.get("salary_max")
    if job_min is None and job_max is None:
        return include_unknown
    if min_salary and job_max is not None and job_max < min_salary:
        return False
    if max_salary and job_min is not None and job_min > max_salary:
        return False
    return True


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_by INTEGER NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                company_name TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                category TEXT,
                url TEXT,
                salary_min INTEGER,
                salary_max INTEGER,
                work_mode TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                resume_text TEXT NOT NULL,
                resume_filename TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                candidate_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(job_id, candidate_id),
                FOREIGN KEY(job_id) REFERENCES jobs(id),
                FOREIGN KEY(candidate_id) REFERENCES users(id)
            )
            """
        )


def hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hashed.hex()


def create_user(email: str, password: str, role: str):
    email = normalize_email(email)
    if role not in ("Candidate", "Employer"):
        return (None, "Invalid role.")
    salt_hex = secrets.token_hex(16)
    password_hash = hash_password(password, salt_hex)
    created_at = datetime.utcnow().isoformat()
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (email, password_hash, salt, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, password_hash, salt_hex, role, created_at)
            )
            return (cur.lastrowid, None)
    except sqlite3.IntegrityError:
        return (None, "Email already registered.")


def authenticate_user(email: str, password: str):
    email = normalize_email(email)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, salt, role FROM users WHERE email = ?",
            (email,)
        ).fetchone()
    if row is None:
        return (None, "Invalid email or password.")
    expected = row["password_hash"]
    actual = hash_password(password, row["salt"])
    if actual != expected:
        return (None, "Invalid email or password.")
    return (dict(row), None)


def row_to_job(row):
    return {
        "id": row["id"],
        "source": row["source"],
        "title": row["title"],
        "company_name": row["company_name"],
        "description": row["description"],
        "candidate_required_location": row["location"] or "",
        "category": row["category"] or "",
        "url": row["url"] or "",
        "salary_min": row["salary_min"],
        "salary_max": row["salary_max"],
        "work_mode": row["work_mode"] or "Unknown"
    }


def fetch_employer_jobs():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, source, title, company_name, description, location, category,
                   url, salary_min, salary_max, work_mode
            FROM jobs
            ORDER BY id DESC
            """
        ).fetchall()
    return [row_to_job(row) for row in rows]


def fetch_employer_jobs_by_user(user_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, source, title, company_name, description, location, category,
                   url, salary_min, salary_max, work_mode
            FROM jobs
            WHERE created_by = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()
    return [row_to_job(row) for row in rows]


def add_employer_job(user_id: int, job):
    created_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (
                created_by, source, title, company_name, description, location,
                category, url, salary_min, salary_max, work_mode, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                job.get("source") or "Employer",
                job.get("title") or "",
                job.get("company_name") or "",
                job.get("description") or "",
                job.get("candidate_required_location") or "",
                job.get("category") or "",
                job.get("url") or "",
                job.get("salary_min"),
                job.get("salary_max"),
                job.get("work_mode") or "Unknown",
                created_at
            )
        )
        return cur.lastrowid


def delete_employer_job(job_id: int, user_id: int):
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE id = ? AND created_by = ?",
            (job_id, user_id)
        )
        if cur.rowcount:
            conn.execute(
                "DELETE FROM matches WHERE job_id = ?",
                (job_id,)
            )
        return cur.rowcount > 0


def save_resume(user_id: int, resume_text: str, resume_filename: str):
    updated_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO resumes (user_id, resume_text, resume_filename, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                resume_text = excluded.resume_text,
                resume_filename = excluded.resume_filename,
                updated_at = excluded.updated_at
            """,
            (user_id, resume_text, resume_filename, updated_at)
        )


def fetch_resume(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT resume_text, resume_filename, updated_at
            FROM resumes
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()
    return dict(row) if row else None


def fetch_all_resumes():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.user_id, r.resume_text, r.resume_filename, r.updated_at, u.email
            FROM resumes r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_counts():
    with get_conn() as conn:
        jobs_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        resumes_count = conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0]
        matches_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    return jobs_count, resumes_count, matches_count


def upsert_match(job_id: int, candidate_id: int, score: int):
    created_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO matches (job_id, candidate_id, score, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(job_id, candidate_id) DO UPDATE SET
                score = excluded.score,
                created_at = excluded.created_at
            """,
            (job_id, candidate_id, score, created_at)
        )


def fetch_candidate_matches(candidate_id: int, min_score: int = 0):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.score, m.created_at, j.*
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            WHERE m.candidate_id = ? AND m.score >= ?
            ORDER BY m.score DESC, m.created_at DESC
            """,
            (candidate_id, min_score)
        ).fetchall()
    matches = []
    for row in rows:
        job = row_to_job(row)
        job["match_score"] = row["score"]
        job["matched_at"] = row["created_at"]
        matches.append(job)
    return matches


def fetch_job_matches(job_id: int, min_score: int = 0):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.score, m.created_at, u.email, r.resume_text, r.resume_filename, r.updated_at
            FROM matches m
            JOIN users u ON m.candidate_id = u.id
            JOIN resumes r ON r.user_id = u.id
            WHERE m.job_id = ? AND m.score >= ?
            ORDER BY m.score DESC, m.created_at DESC
            """,
            (job_id, min_score)
        ).fetchall()
    return [dict(row) for row in rows]


def compute_matches_for_job(job_id: int, job_description: str):
    resumes = fetch_all_resumes()
    if not resumes:
        return 0
    count = 0
    for resume in resumes:
        score = score_job_match(resume["resume_text"], job_description)
        upsert_match(job_id, resume["user_id"], score)
        count += 1
    return count


def compute_matches_for_candidate(candidate_id: int, resume_text: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, description FROM jobs ORDER BY id DESC"
        ).fetchall()
    if not rows:
        return 0
    count = 0
    for row in rows:
        score = score_job_match(resume_text, row["description"])
        upsert_match(row["id"], candidate_id, score)
        count += 1
    return count

# ---------------- Streamlit Setup ----------------

st.set_page_config(
    page_title="AI Job Application Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
    :root {
        --bg: #f6f1e8;
        --surface: #ffffff;
        --surface-2: #fbf7f0;
        --primary: #1b1b22;
        --muted: #5d6572;
        --accent: #e07a3a;
        --accent-2: #1f8a70;
        --border: rgba(27,27,34,0.08);
        --shadow: 0 18px 44px rgba(27,27,34,0.12);
        --shadow-soft: 0 10px 28px rgba(27,27,34,0.08);
    }
    html, body, [class*="css"]  {
        font-family: 'IBM Plex Sans', sans-serif;
        color: var(--primary);
    }
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Space Grotesk', sans-serif;
        letter-spacing: -0.02em;
    }
    .stApp {
        background:
            radial-gradient(900px 600px at 8% -10%, rgba(224,122,58,0.18) 0%, rgba(246,241,232,0.2) 50%),
            radial-gradient(900px 600px at 90% 0%, rgba(31,138,112,0.14) 0%, rgba(246,241,232,0) 55%),
            linear-gradient(180deg, #fbf7f0 0%, #f6f1e8 100%);
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #18181f 0%, #242634 100%);
        color: #f1ece3;
        border-right: 1px solid rgba(255,255,255,0.08);
    }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p {
        color: #f1ece3;
    }
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea,
    section[data-testid="stSidebar"] .stMultiSelect div {
        background: rgba(255,255,255,0.08);
        color: #fbf7f0;
    }
    .hero {
        background: linear-gradient(135deg, #1c1b22 0%, #2c2d3a 60%, #2f3f4b 100%);
        color: #f8f5ef;
        padding: 32px 36px;
        border-radius: 26px;
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 22px 55px rgba(20,20,26,0.35);
        margin-bottom: 18px;
    }
    .hero-grid {
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(220px, 1fr);
        gap: 24px;
        align-items: center;
    }
    .eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.2em;
        font-size: 11px;
        opacity: 0.7;
        margin-bottom: 10px;
    }
    .hero-title { font-size: 32px; font-weight: 700; margin-bottom: 10px; }
    .hero-sub { font-size: 15px; opacity: 0.9; max-width: 640px; }
    .hero-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .hero-card {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.18);
        border-radius: 18px;
        padding: 16px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.12);
    }
    .hero-card-title {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        opacity: 0.7;
        margin-bottom: 10px;
    }
    .hero-card-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        font-size: 13px;
    }
    .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.2);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .section-title {
        font-size: 20px;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .subtle { color: var(--muted); }
    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 12px;
        box-shadow: var(--shadow-soft);
    }
    div[data-testid="stExpander"] {
        border-radius: 16px;
        border: 1px solid var(--border);
        background: var(--surface);
        box-shadow: var(--shadow-soft);
    }
    div[data-baseweb="tab-list"] {
        gap: 8px;
    }
    button[role="tab"] {
        border-radius: 999px;
        padding: 6px 16px;
        border: 1px solid var(--border);
        background: var(--surface);
        color: var(--primary);
    }
    button[role="tab"][aria-selected="true"] {
        background: var(--accent);
        color: #ffffff;
        border-color: var(--accent);
    }
    button[kind="primary"] {
        background: linear-gradient(135deg, var(--accent), #f0a159);
        border: none;
    }
    button[kind="secondary"] {
        border: 1px solid var(--border);
    }
    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: var(--shadow-soft);
    }
    @media (max-width: 900px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="hero">
        <div class="hero-grid">
            <div>
                <div class="eyebrow">AI Job Application Assistant</div>
                <div class="hero-title">A focused command center for smarter hiring.</div>
                <div class="hero-sub">
                    Keep candidates, employers, and AI scoring in one calm workspace.
                    Fetch jobs, compare matches, and generate tailored applications in minutes.
                </div>
                <div class="hero-row">
                    <span class="pill">Candidate Workflow</span>
                    <span class="pill">Employer Matching</span>
                    <span class="pill">AI Scoring</span>
                </div>
            </div>
            <div class="hero-card">
                <div class="hero-card-title">Workspace</div>
                <div class="hero-card-row"><span>Resume Intake</span><strong>PDF Upload</strong></div>
                <div class="hero-card-row"><span>Job Sources</span><strong>Remote APIs</strong></div>
                <div class="hero-card-row"><span>Matching</span><strong>Score + Explain</strong></div>
                <div class="hero-card-row"><span>Applications</span><strong>Generate</strong></div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- Helper Functions ----------------

def extract_keywords(resume_text: str):
    common_skills = [
        "python", "sql", "machine learning", "data analysis",
        "data scientist", "data analyst", "statistics",
        "nlp", "deep learning", "tableau", "power bi"
    ]
    text = resume_text.lower()
    return [skill for skill in common_skills if skill in text]


def parse_keywords(text: str):
    if not text:
        return []
    return [k.strip().lower() for k in text.split(",") if k.strip()]


def _job_key(job):
    url = (job.get("url") or "").strip().lower()
    if url:
        return url
    title = (job.get("title") or "").strip().lower()
    company = (job.get("company_name") or "").strip().lower()
    return f"{title}|{company}"


def dedupe_jobs(jobs):
    seen = set()
    unique = []
    for job in jobs:
        key = _job_key(job)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def match_jobs_by_keywords(jobs, keywords):
    if not keywords:
        return []
    matched = []
    for job in jobs:
        title = job.get("title") or ""
        description = job.get("description") or ""
        content = (title + " " + description).lower()
        if any(k in content for k in keywords):
            matched.append(job)
    return matched


def filter_jobs(
    jobs,
    location_filter,
    city_filter,
    company_filter,
    work_modes,
    min_salary,
    max_salary,
    include_unknown_salary
):
    location_filter = (location_filter or "").strip().lower()
    city_filter = (city_filter or "").strip().lower()
    company_filters = [c.strip().lower() for c in (company_filter or "").split(",") if c.strip()]
    work_modes = work_modes or []
    filtered = []
    for job in jobs:
        location_text = (job.get("candidate_required_location") or "").lower()
        company_text = (job.get("company_name") or "").lower()
        work_mode = job.get("work_mode") or "Unknown"
        if location_filter and location_filter not in location_text:
            continue
        if city_filter and city_filter not in location_text:
            continue
        if company_filters and not any(c in company_text for c in company_filters):
            continue
        if work_modes and work_mode not in work_modes:
            continue
        if not salary_in_range(job, min_salary, max_salary, include_unknown_salary):
            continue
        filtered.append(job)
    return filtered


def init_state():
    defaults = {
        "authenticated": False,
        "role": "",
        "user_email": "",
        "user_id": None,
        "selected_job": None,
        "resume_text": "",
        "resume_filename": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def logout():
    st.session_state["authenticated"] = False
    st.session_state["role"] = ""
    st.session_state["user_email"] = ""
    st.session_state["user_id"] = None
    st.session_state["selected_job"] = None
    st.session_state["resume_text"] = ""
    st.session_state["resume_filename"] = ""


@st.cache_data(ttl=JOB_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_remotive_jobs(keywords):
    url = "https://remotive.com/api/remote-jobs"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
    except (requests.RequestException, ValueError):
        return []

    matched = []
    for job in jobs:
        title = job.get("title", "")
        description = job.get("description", "")
        salary_text = job.get("salary", "")
        salary_min, salary_max = parse_salary_range(salary_text)
        content = (title + " " + description).lower()
        if any(k in content for k in keywords):
            matched.append({
                "source": "Remotive",
                "title": title,
                "company_name": job.get("company_name", ""),
                "description": description,
                "candidate_required_location": job.get("candidate_required_location", ""),
                "category": job.get("category", ""),
                "url": job.get("url", ""),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "work_mode": "Remote"
            })

    return matched


@st.cache_data(ttl=JOB_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_remoteok_jobs(keywords):
    url = "https://remoteok.com/api"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return []

    matched = []
    for job in data:
        if not isinstance(job, dict):
            continue
        title = str(job.get("position") or "")
        description = str(job.get("description") or "")
        location = str(job.get("location") or "")
        if not title and not description:
            continue
        content = (title + " " + description).lower()
        if any(k in content for k in keywords):
            tags = job.get("tags") or []
            if isinstance(tags, list):
                category = ", ".join(tags[:3])
            else:
                category = str(tags)
            salary_min = job.get("salary_min") or None
            salary_max = job.get("salary_max") or None
            if salary_min is not None:
                try:
                    salary_min = int(salary_min)
                except ValueError:
                    salary_min = None
            if salary_max is not None:
                try:
                    salary_max = int(salary_max)
                except ValueError:
                    salary_max = None
            if salary_min is None and salary_max is None:
                salary_min, salary_max = parse_salary_range(job.get("salary") or "")
            matched.append({
                "source": "RemoteOK",
                "title": title,
                "company_name": str(job.get("company") or ""),
                "description": description,
                "candidate_required_location": location,
                "category": category,
                "url": str(job.get("url") or job.get("apply_url") or ""),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "work_mode": infer_work_mode(location, tags)
            })

    return matched


@st.cache_data(show_spinner=False)
def score_job_match(resume_text, job_description):
    resume_short = limit_text(clean_text(resume_text), MAX_RESUME_CHARS)
    job_short = limit_text(clean_text(job_description), MAX_JOB_CHARS)
    prompt = f"""
Score how well this resume matches the job on a scale of 0 to 100.
Return ONLY the number.

RESUME:
{resume_short}

JOB:
{job_short}
"""
    result = subprocess.run(
        ["ollama", "run", "llama3"],
        input=prompt,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0

@st.cache_data(show_spinner=False)
def explain_job_match(resume_text, job_description):
    resume_short = limit_text(clean_text(resume_text), MAX_RESUME_CHARS)
    job_short = limit_text(clean_text(job_description), MAX_JOB_CHARS)
    prompt = f"""
Explain why this resume matches or does not match the job.
Give 3 short bullet points.
Be honest and concise.

RESUME:
{resume_short}

JOB:
{job_short}
"""

    result = subprocess.run(
        ["ollama", "run", "llama3"],
        input=prompt,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    return result.stdout.strip()

init_db()
init_state()

if not st.session_state["authenticated"]:
    st.header("Sign in")
    st.write("Choose a role to continue.")
    with st.form("auth_form"):
        action = st.radio("Action", ["Login", "Register"], horizontal=True)
        if action == "Register":
            role = st.radio("I am a", ["Candidate", "Employer"])
        else:
            role = "Candidate"
            st.caption("Role will be loaded from your account.")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Continue")
    if submitted:
        if not email or not password:
            st.error("Email and password are required.")
        else:
            if action == "Register":
                user_id, error = create_user(email, password, role)
                if error:
                    st.error(error)
                else:
                    st.session_state["authenticated"] = True
                    st.session_state["role"] = role
                    st.session_state["user_email"] = normalize_email(email)
                    st.session_state["user_id"] = user_id
                    st.rerun()
            else:
                user, error = authenticate_user(email, password)
                if error:
                    st.error(error)
                else:
                    st.session_state["authenticated"] = True
                    st.session_state["role"] = user["role"]
                    st.session_state["user_email"] = user["email"]
                    st.session_state["user_id"] = user["id"]
                    st.rerun()
    st.stop()

jobs_count, resumes_count, matches_count = fetch_counts()
metric_cols = st.columns(3)
metric_cols[0].metric("Jobs in system", jobs_count)
metric_cols[1].metric("Candidate resumes", resumes_count)
metric_cols[2].metric("Total matches", matches_count)
st.divider()

sources = []
extra_keywords_input = ""
location_filter = ""
city_filter = ""
company_filter = ""
work_modes = []
min_match_score = 0
max_jobs_to_score = MAX_JOBS_TO_SCORE
show_explanations = False
salary_min = 0
salary_max = 0
include_unknown_salary = True
employer_min_match_score = 70
employer_view_min_score = 70

with st.sidebar:
    st.markdown("### Session")
    st.write(f"Signed in as: {st.session_state['user_email']}")
    st.write(f"Role: {st.session_state['role']}")
    if st.button("Log out"):
        logout()
        st.rerun()
    if st.session_state["role"] == "Candidate":
        st.divider()
        st.markdown("### Preferences")
        with st.expander("Sources & Keywords", expanded=True):
            sources = st.multiselect(
                "Job sources",
                ["Remotive", "RemoteOK", "Employer"],
                default=["Remotive", "RemoteOK", "Employer"]
            )
            extra_keywords_input = st.text_input("Extra keywords (comma-separated)")
        with st.expander("Work & Location", expanded=False):
            work_modes = st.multiselect(
                "Work mode",
                ["Remote", "Hybrid", "On-site", "Unknown"],
                default=["Remote", "Hybrid", "On-site", "Unknown"]
            )
            location_filter = st.text_input("Location preference (country/region)")
            city_filter = st.text_input("City preference")
            company_filter = st.text_input("Preferred companies (comma-separated)")
        with st.expander("Salary & Scoring", expanded=False):
            salary_min = st.number_input("Minimum package (USD)", min_value=0, value=0, step=1000)
            salary_max = st.number_input("Maximum package (USD)", min_value=0, value=0, step=1000)
            include_unknown_salary = st.checkbox("Include jobs with unknown salary", value=True)
            min_match_score = st.slider(
                "Minimum match score",
                min_value=0,
                max_value=100,
                value=5,
                step=5
            )
            max_jobs_to_score = st.slider(
                "Jobs to score",
                min_value=1,
                max_value=10,
                value=MAX_JOBS_TO_SCORE
            )
            show_explanations = st.checkbox("Show explanations (slower)", value=False)
        with st.expander("Employer Matching", expanded=False):
            employer_min_match_score = st.slider(
                "Employer match minimum score",
                min_value=0,
                max_value=100,
                value=70,
                step=5
            )
    elif st.session_state["role"] == "Employer":
        st.divider()
        st.markdown("### Employer Filters")
        employer_view_min_score = st.slider(
            "Minimum match score to show",
            min_value=0,
            max_value=100,
            value=70,
            step=5
        )

# ---------------- Resume Upload ----------------

if st.session_state["role"] == "Candidate":
    st.header("Candidate Workspace")
    stored_resume = fetch_resume(st.session_state["user_id"])
    resume_text_session = st.session_state.get("resume_text") or ""
    resume_filename_session = st.session_state.get("resume_filename") or ""
    resume_text_current = resume_text_session
    resume_filename_current = resume_filename_session
    resume_source = "uploaded" if resume_text_session else "none"
    if not resume_text_current and stored_resume:
        resume_text_current = stored_resume.get("resume_text") or ""
        resume_filename_current = stored_resume.get("resume_filename") or ""
        resume_source = "stored" if resume_text_current else "none"

    tab_resume, tab_jobs, tab_employer, tab_apply = st.tabs(
        ["Resume", "Job Matches", "Employer Matches", "Applications"]
    )

    with tab_resume:
        st.subheader("Resume Profile")
        st.caption("Upload a PDF resume to unlock matching and application generation.")
        uploaded_resume = st.file_uploader("Upload your resume (PDF)", type=["pdf"])

        if uploaded_resume:
            resume_text_upload = ""
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_resume.read())
                tmp_path = tmp.name

            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        resume_text_upload += page_text + "\n"

            if resume_text_upload.strip():
                st.session_state["resume_text"] = resume_text_upload
                st.session_state["resume_filename"] = uploaded_resume.name
                resume_text_current = resume_text_upload
                resume_filename_current = uploaded_resume.name
                resume_source = "uploaded"
                save_resume(
                    st.session_state["user_id"],
                    resume_text_upload,
                    uploaded_resume.name
                )
                with st.spinner("Updating employer matches..."):
                    compute_matches_for_candidate(
                        st.session_state["user_id"],
                        resume_text_upload
                    )
                st.success("Resume uploaded and read successfully.")
            else:
                st.warning("Unable to read text from this PDF. Try another file.")

        if resume_text_current:
            word_count = len(re.findall(r"\\w+", resume_text_current))
            keyword_list = extract_keywords(resume_text_current)
            stats_cols = st.columns(3)
            stats_cols[0].metric("Words", f"{word_count:,}")
            stats_cols[1].metric("Detected skills", len(keyword_list))
            stats_cols[2].metric(
                "Source",
                "Uploaded" if resume_source == "uploaded" else "Stored"
            )
            if keyword_list:
                st.caption(f"Detected keywords: {', '.join(keyword_list)}")
            if stored_resume and resume_source == "stored":
                updated = stored_resume.get("updated_at") or ""
                filename = resume_filename_current or "Stored resume"
                st.caption(f"Stored resume: {filename} - Updated {updated}")
            with st.expander("View extracted resume text"):
                st.text_area("Resume Text", resume_text_current, height=250)
        else:
            st.info("Upload a resume to start matching.")

    with tab_jobs:
        st.subheader("Matching Job Opportunities")
        st.caption("Fetches jobs from selected sources and scores the best matches.")

        if not resume_text_current:
            st.info("Upload your resume in the Resume tab to see matching jobs.")
        else:
            resume_keywords = extract_keywords(resume_text_current)
            extra_keywords = parse_keywords(extra_keywords_input)
            keywords = sorted(set(resume_keywords + extra_keywords))

            if salary_max and salary_min and salary_max < salary_min:
                st.warning("Maximum package should be greater than or equal to minimum package.")
            elif not sources:
                st.warning("Select at least one job source in the sidebar.")
            elif not keywords:
                st.warning("No keywords found. Add extra keywords in the sidebar.")
            else:
                with st.spinner("Fetching matching jobs..."):
                    keywords_tuple = tuple(keywords)
                    remotive_jobs = fetch_remotive_jobs(keywords_tuple) if "Remotive" in sources else []
                    remoteok_jobs = fetch_remoteok_jobs(keywords_tuple) if "RemoteOK" in sources else []
                    employer_jobs_all = fetch_employer_jobs() if "Employer" in sources else []
                    employer_jobs = (
                        match_jobs_by_keywords(employer_jobs_all, keywords)
                        if "Employer" in sources
                        else []
                    )
                    jobs = dedupe_jobs(remotive_jobs + remoteok_jobs + employer_jobs)
                    jobs = filter_jobs(
                        jobs,
                        location_filter,
                        city_filter,
                        company_filter,
                        work_modes,
                        salary_min or None,
                        salary_max or None,
                        include_unknown_salary
                    )

                st.write(
                    "Found "
                    f"{len(jobs)} keyword-matched jobs "
                    f"({len(remotive_jobs)} Remotive, {len(remoteok_jobs)} RemoteOK, "
                    f"{len(employer_jobs)} Employer)"
                )

                scored_jobs = []

                with st.spinner("Scoring jobs using AI (this may take a moment)..."):
                    for job in jobs[:max_jobs_to_score]:
                        score = score_job_match(resume_text_current, job["description"])
                        if score >= min_match_score:
                            explanation = ""
                            if show_explanations:
                                explanation = explain_job_match(
                                    resume_text_current,
                                    job["description"]
                                )
                            scored_jobs.append((job, score, explanation))

                if not scored_jobs:
                    st.warning("No jobs met the minimum match score.")
                else:
                    for i, (job, score, explanation) in enumerate(scored_jobs):
                        with st.expander(f"{job['title']} - {job['company_name']} ({score}%)"):
                            st.write(clean_text(job["description"])[:500] + "...")
                            st.write(f"Location: {job['candidate_required_location']}")
                            st.write(f"Work mode: {job.get('work_mode', 'Unknown')}")
                            st.write(f"Salary: {format_salary(job)}")
                            st.write(f"Category: {job['category']}")
                            st.write(f"Source: {job['source']}")
                            if job.get("url"):
                                st.write(f"Apply: {job['url']}")
                            st.write(f"Match Score: {score}%")
                            if explanation:
                                st.write("Why this matches:")
                                st.write(explanation)

                            if st.button("Select this job", key=f"select_{i}"):
                                st.session_state["selected_job"] = job

    with tab_employer:
        st.subheader("Employer Match Notifications")
        st.caption("Matches against employer-posted jobs are shown here.")

        if st.button("Recalculate employer matches"):
            if not resume_text_current:
                st.warning("Upload your resume to enable employer matching.")
            else:
                with st.spinner("Recalculating matches against employer jobs..."):
                    total = compute_matches_for_candidate(
                        st.session_state["user_id"],
                        resume_text_current
                    )
                st.success(f"Matches refreshed for {total} job(s).")

        candidate_matches = fetch_candidate_matches(
            st.session_state["user_id"],
            employer_min_match_score
        )
        if not candidate_matches:
            st.info("No employer matches yet. Upload a resume and check back.")
        else:
            st.write(f"Found {len(candidate_matches)} matched employer job(s).")
            for job in candidate_matches:
                with st.expander(
                    f"{job['title']} - {job['company_name']} ({job['match_score']}%)"
                ):
                    st.write(clean_text(job["description"])[:500] + "...")
                    st.write(f"Location: {job['candidate_required_location']}")
                    st.write(f"Work mode: {job.get('work_mode', 'Unknown')}")
                    st.write(f"Salary: {format_salary(job)}")
                    st.write(f"Category: {job['category']}")
                    st.write(f"Source: {job['source']}")
                    if job.get("url"):
                        st.write(f"Apply: {job['url']}")
                    st.write(f"Match Score: {job['match_score']}%")

    with tab_apply:
        st.subheader("Generate Application Content")
        selected_job = st.session_state.get("selected_job")

        if not resume_text_current:
            st.info("Upload your resume in the Resume tab first.")
        elif selected_job:
            st.info(f"Selected job: {selected_job['title']} at {selected_job['company_name']}")

            if st.button("Generate Application"):
                with st.spinner("AI is generating application content..."):
                    prompt = f"""
You are an AI assistant preparing a professional job application.

RULES:
- Do NOT repeat the resume
- Do NOT list skills mechanically
- Keep tone human, concise, and confident

RESUME:
{clean_text(resume_text_current)}

JOB:
Title: {selected_job['title']}
Company: {selected_job['company_name']}
Description:
{clean_text(selected_job['description'])}

Generate:
1) Cover Letter
2) Why are you a good fit for this role?
3) Relevant experience
4) Key skills for this role
5) Why do you want to work at this company?
"""

                    result = subprocess.run(
                        ["ollama", "run", "llama3"],
                        input=prompt,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="ignore"
                    )

                st.success("Application content generated!")
                st.text_area("Generated Application", result.stdout, height=500)

                st.download_button(
                    "Download Application",
                    result.stdout,
                    file_name="job_application.txt",
                    mime="text/plain"
                )
        else:
            st.info("Select a job in the Job Matches tab to generate an application.")

elif st.session_state["role"] == "Employer":
    st.header("Employer Workspace")
    st.caption("Post roles and review matched candidates in one place.")

    with st.form("employer_form", clear_on_submit=True):
        st.subheader("Post a job")
        job_title = st.text_input("Job title")
        company_name = st.text_input("Company name")
        job_location = st.text_input("Location")
        work_mode = st.selectbox("Work mode", ["Remote", "Hybrid", "On-site", "Unknown"])
        job_category = st.text_input("Category / Tags")
        salary_min_input = st.number_input("Minimum package (USD)", min_value=0, value=0, step=1000)
        salary_max_input = st.number_input("Maximum package (USD)", min_value=0, value=0, step=1000)
        apply_url = st.text_input("Apply URL (optional)")
        job_description = st.text_area("Job description", height=200)
        submitted = st.form_submit_button("Post job")

    if submitted:
        if not job_title or not company_name or not job_description:
            st.error("Please fill in job title, company name, and description.")
        elif salary_max_input and salary_min_input and salary_max_input < salary_min_input:
            st.error("Maximum package should be greater than or equal to minimum package.")
        else:
            job_id = add_employer_job(
                st.session_state["user_id"],
                {
                    "source": "Employer",
                    "title": job_title,
                    "company_name": company_name,
                    "description": job_description,
                    "candidate_required_location": job_location,
                    "category": job_category,
                    "url": apply_url,
                    "salary_min": salary_min_input or None,
                    "salary_max": salary_max_input or None,
                    "work_mode": work_mode
                }
            )
            st.success("Job posted. Matching candidates...")
            with st.spinner("Scoring candidates against this job..."):
                total = compute_matches_for_job(job_id, job_description)
            st.success(f"Job posted. {total} candidate(s) scored.")

    st.divider()
    employer_jobs = fetch_employer_jobs_by_user(st.session_state["user_id"])
    if employer_jobs:
        st.subheader("Posted jobs")
        for job in employer_jobs:
            with st.expander(f"{job['title']} - {job['company_name']}"):
                st.write(job["description"])
                if job.get("candidate_required_location"):
                    st.write(f"Location: {job['candidate_required_location']}")
                st.write(f"Work mode: {job.get('work_mode', 'Unknown')}")
                st.write(f"Salary: {format_salary(job)}")
                if job.get("category"):
                    st.write(f"Category: {job['category']}")
                if job.get("url"):
                    st.write(f"Apply: {job['url']}")
                if st.button("Remove job", key=f"remove_employer_{job['id']}"):
                    if delete_employer_job(job["id"], st.session_state["user_id"]):
                        st.success("Job removed.")
                        st.rerun()
                st.divider()
                st.markdown("**Matched candidates**")
                if st.button(
                    "Refresh matches for this job",
                    key=f"refresh_matches_{job['id']}"
                ):
                    with st.spinner("Re-scoring candidates..."):
                        total = compute_matches_for_job(job["id"], job["description"])
                    st.success(f"Re-scored {total} candidate(s).")
                    st.rerun()

                matches = fetch_job_matches(job["id"], employer_view_min_score)
                if not matches:
                    st.write("No candidate matches yet.")
                else:
                    st.write(f"{len(matches)} candidate(s) matched.")
                    for idx, match in enumerate(matches):
                        st.markdown(
                            f"**{match['email']}** — Match Score: {match['score']}%"
                        )
                        st.text_area(
                            "Resume Text",
                            match["resume_text"],
                            height=200,
                            key=f"resume_text_{job['id']}_{idx}"
                        )
    else:
        st.info("No jobs posted yet. Add one above to see matches.")

st.caption("Testing mode only. No job applications are submitted.")


