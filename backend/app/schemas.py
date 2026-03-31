from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from pydantic.config import ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class JobCreate(BaseModel):
    title: str
    company_name: str
    description: str
    location: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    work_mode: Optional[str] = None


class JobOut(JobCreate):
    id: int
    source: str
    created_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalJob(BaseModel):
    title: str
    company: str
    description: str
    location: str
    apply_url: str
    source: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    tags: list[str] = Field(default_factory=list)


class ResumeOut(BaseModel):
    resume_text: str
    resume_filename: Optional[str] = None
    updated_at: datetime


class MatchScoreRequest(BaseModel):
    resume_text: str
    job_description: str
    explain: bool = False


class MatchScoreResponse(BaseModel):
    score: int
    explanation: Optional[str] = None


class ApplicationRequest(BaseModel):
    resume_text: str
    job_title: str
    company_name: str
    job_description: str


class ApplicationResponse(BaseModel):
    content: str


class MatchOut(BaseModel):
    job_id: int
    candidate_id: int
    match_score: int
    matched_skills: Optional[list[str]] = None
    missing_skills: Optional[list[str]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateMatchOut(BaseModel):
    job_id: int
    match_score: int
    matched_at: datetime
    title: str
    company_name: str
    description: str
    location: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    work_mode: Optional[str] = None
    source: str


class EmployerMatchOut(BaseModel):
    candidate_email: EmailStr
    match_score: int
    matched_skills: Optional[list[str]] = None
    missing_skills: Optional[list[str]] = None
    matched_at: datetime
    resume_text: str
    resume_filename: Optional[str] = None
    resume_updated_at: datetime
