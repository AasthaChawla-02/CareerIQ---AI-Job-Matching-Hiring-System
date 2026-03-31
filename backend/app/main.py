from datetime import datetime
from io import BytesIO
import pdfplumber
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .ai import explain_job_match, generate_application_content, score_job_match, detailed_match_score
from .auth import create_access_token, get_current_user, new_salt, require_role, verify_password
from .auth import hash_password
from .db import Base, engine, get_db
from .job_sources import dedupe_jobs, fetch_remotive_jobs, fetch_remoteok_jobs, filter_jobs_by_keywords
from .models import Job, Match, Resume, User
from .schemas import (
    ApplicationRequest,
    ApplicationResponse,
    CandidateMatchOut,
    ExternalJob,
    EmployerMatchOut,
    JobCreate,
    JobOut,
    MatchScoreRequest,
    MatchScoreResponse,
    ResumeOut,
    TokenOut,
    UserCreate,
    UserLogin,
    UserOut,
)


app = FastAPI(title="AI Job Application Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _job_to_external(job: dict) -> ExternalJob:
    return ExternalJob(**job)


def _upsert_match(db: Session, job_id: int, candidate_id: int, detail: dict) -> Match:
    score = detail['match_score']
    existing = (
        db.query(Match)
        .filter(Match.job_id == job_id, Match.candidate_id == candidate_id)
        .first()
    )
    if existing:
        existing.match_score = score
        existing.matched_skills = detail.get('matched_skills')
        existing.missing_skills = detail.get('missing_skills')
        existing.created_at = datetime.utcnow()
        return existing
    match = Match(
        job_id=job_id, 
        candidate_id=candidate_id, 
        match_score=score,
        matched_skills=detail.get('matched_skills'),
        missing_skills=detail.get('missing_skills')
    )
    db.add(match)
    return match


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    role = payload.role.strip()
    if role not in ("Candidate", "Employer"):
        raise HTTPException(status_code=400, detail="Role must be Candidate or Employer.")
    email = _normalize_email(payload.email)
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")
    salt = new_salt()
    hashed = hash_password(payload.password, salt)
    user = User(email=email, password_hash=hashed, salt=salt, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.salt, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user)
    return TokenOut(access_token=token, user=user)


@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@app.get("/jobs/external", response_model=list[ExternalJob])
def list_external_jobs(
    keywords: str = Query("", description="Comma-separated keywords"),
    sources: str = Query("Remotive,RemoteOK", description="Comma-separated sources"),
    limit: int = Query(50, ge=1, le=200),
):
    keywords_list = [k.strip() for k in keywords.split(",") if k.strip()]
    sources_list = [s.strip() for s in sources.split(",") if s.strip()]
    jobs = []
    if "Remotive" in sources_list:
        jobs.extend(fetch_remotive_jobs())
    if "RemoteOK" in sources_list:
        jobs.extend(fetch_remoteok_jobs())
    jobs = dedupe_jobs(jobs)
    jobs = filter_jobs_by_keywords(jobs, keywords_list)
    return [_job_to_external(job) for job in jobs[:limit]]


@app.post("/jobs", response_model=JobOut)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Employer")),
):
    job = Job(
        created_by=user.id,
        source="Employer",
        title=payload.title,
        company_name=payload.company_name,
        description=payload.description,
        location=payload.location,
        category=payload.category,
        url=payload.url,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        work_mode=payload.work_mode or "Unknown",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Auto match with all candidates
    compute_matches_for_job(job.id, db, user)
    
    return job


@app.get("/jobs/employer", response_model=list[JobOut])
def list_employer_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Employer")),
):
    return (
        db.query(Job)
        .filter(Job.created_by == user.id)
        .order_by(Job.id.desc())
        .all()
    )


@app.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Employer")),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.created_by == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    db.query(Match).filter(Match.job_id == job_id).delete()
    db.delete(job)
    db.commit()
    return None


@app.post("/resumes", response_model=ResumeOut)
def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Candidate")),
):
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")
    resume_text = ""
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                resume_text += page_text + "\n"
    resume_text = resume_text.strip()
    if not resume_text:
        raise HTTPException(status_code=400, detail="Unable to read text from PDF.")
    existing = db.query(Resume).filter(Resume.user_id == user.id).first()
    if existing:
        existing.resume_text = resume_text
        existing.resume_filename = file.filename
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return ResumeOut(
            resume_text=existing.resume_text,
            resume_filename=existing.resume_filename,
            updated_at=existing.updated_at,
        )
    new_resume = Resume(
        user_id=user.id,
        resume_text=resume_text,
        resume_filename=file.filename,
    )
    db.add(new_resume)
    db.commit()
    db.refresh(new_resume)
    
    # Auto match with all jobs
    compute_matches_for_candidate(db, user)
    
    return ResumeOut(
        resume_text=new_resume.resume_text,
        resume_filename=new_resume.resume_filename,
        updated_at=new_resume.updated_at,
    )


@app.get("/resumes/me", response_model=ResumeOut)
def get_resume(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Candidate")),
):
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return ResumeOut(
        resume_text=resume.resume_text,
        resume_filename=resume.resume_filename,
        updated_at=resume.updated_at,
    )


@app.post("/matches/score", response_model=MatchScoreResponse)
def score_match(payload: MatchScoreRequest):
    score = score_job_match(payload.resume_text, payload.job_description)
    explanation = None
    if payload.explain:
        explanation = explain_job_match(payload.resume_text, payload.job_description)
    return MatchScoreResponse(score=score, explanation=explanation)


@app.post("/matches/compute-job/{job_id}")
def compute_matches_for_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Employer")),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.created_by == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    resumes = db.query(Resume).all()
    if not resumes:
        return {"count": 0}
    count = 0
    for resume in resumes:
        detail = detailed_match_score(resume.resume_text, job.description)
        _upsert_match(db, job_id, resume.user_id, detail)
        count += 1
    db.commit()
    return {"count": count}


@app.post("/matches/compute-candidate")
def compute_matches_for_candidate(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Candidate")),
):
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    jobs = db.query(Job).order_by(Job.id.desc()).all()
    if not jobs:
        return {"count": 0}
    count = 0
    for job in jobs:
        detail = detailed_match_score(resume.resume_text, job.description)
        _upsert_match(db, job.id, user.id, detail)
        count += 1
    db.commit()
    return {"count": count}


@app.get("/matches/candidate", response_model=list[CandidateMatchOut])
def list_candidate_matches(
    min_score: int = Query(0, ge=0, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Candidate")),
):
    rows = (
        db.query(Match, Job)
        .join(Job, Match.job_id == Job.id)
        .filter(Match.candidate_id == user.id, Match.match_score >= min_score)
        .order_by(Match.match_score.desc(), Match.created_at.desc())
        .all()
    )
    results = []
    for match, job in rows:
        results.append(
            {
                "job_id": job.id,
                "match_score": match.match_score,
                "matched_at": match.created_at,
                "title": job.title,
                "company_name": job.company_name,
                "description": job.description,
                "location": job.location,
                "category": job.category,
                "url": job.url,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "work_mode": job.work_mode,
                "source": job.source,
            }
        )
    return results


@app.get("/matches/job/{job_id}", response_model=list[EmployerMatchOut])
def list_job_matches(
    job_id: int,
    min_score: int = Query(0, ge=0, le=100),
    candidate_search: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("Employer")),
):
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.created_by == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    query = db.query(Match, User, Resume).join(User, Match.candidate_id == User.id).join(Resume, Resume.user_id == User.id).filter(
        Match.job_id == job_id, 
        Match.match_score >= min_score
    )
    if candidate_search:
        query = query.filter(User.email.ilike(f"%{candidate_search}%"))
    rows = query.order_by(Match.match_score.desc(), Match.created_at.desc()).all()
    results = []
    for match, candidate, resume in rows:
        results.append(
            {
                "candidate_email": candidate.email,
                "match_score": match.match_score,
                "matched_skills": match.matched_skills,
                "missing_skills": match.missing_skills,
                "matched_at": match.created_at,
                "resume_text": resume.resume_text,
                "resume_filename": resume.resume_filename,
                "resume_updated_at": resume.updated_at,
            }
        )
    return results


@app.post("/applications/generate", response_model=ApplicationResponse)
def generate_application(payload: ApplicationRequest):
    content = generate_application_content(
        payload.resume_text,
        payload.job_title,
        payload.company_name,
        payload.job_description,
    )
    return ApplicationResponse(content=content)
