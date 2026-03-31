# AI Job Application Assistant

End-to-end helper for searching jobs, scoring matches, shortlisting, and generating application content.
Includes a Streamlit UI and a CLI pipeline.

## Setup

1. Create a virtual environment.
2. Install dependencies.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Full-Stack App (React + FastAPI + Postgres + OpenAI)

This repo now includes a React frontend and a FastAPI backend that uses PostgreSQL
and the OpenAI API for scoring and generation.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env with your DATABASE_URL and OPENAI_API_KEY
uvicorn app.main:app --app-dir backend --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Notes

- The backend auto-creates tables on startup.
- The React app expects the API at `http://localhost:8000` (override with `VITE_API_BASE`).

## Streamlit App

```bash
streamlit run app.py
```

## CLI Pipeline

1) Extract resume profile and text:

```bash
python resume_to_json_local.py --resume AasthaChawlaResume.pdf
```

2) Fetch jobs from public APIs:

```bash
python job_search.py --keywords "data scientist,data analyst"
```

3) Score jobs against the resume:

```bash
python job_matcher.py --jobs jobs.json --resume AasthaChawlaResume.pdf
```

4) Shortlist jobs and update the tracker:

```bash
python job_shortlister.py --scored scored_jobs.json --threshold 70
```

5) Generate cover letters:

```bash
python generate_cover_letters.py --shortlisted shortlisted_jobs.json
```

6) Generate full application answers:

```bash
python generate_application_answers.py --shortlisted shortlisted_jobs.json
```

7) Review prepared applications:

```bash
python prepare_applications.py --status Shortlisted
```

## Useful Commands

Open application links or search queries:

```bash
python assist_apply.py --status Shortlisted --open
```

## Notes

- Uses the local Ollama CLI by default. Configure with `OLLAMA_MODEL`.
- No applications are submitted automatically.
