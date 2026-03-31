import re
from typing import Optional

from openai import OpenAI

from .settings import settings

_client: Optional[OpenAI] = None
MAX_RESUME_CHARS = 4000
MAX_JOB_CHARS = 1500


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if settings.openai_api_key:
            _client = OpenAI(api_key=settings.openai_api_key)
        else:
            _client = OpenAI()
    return _client


def _tokenize(text: str) -> set:
    if not text:
        return set()
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}", text.lower()))


def _heuristic_match_score(resume_text: str, job_description: str) -> int:
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


def _parse_first_int(text: str) -> Optional[int]:
    match = re.search(r"\d+", text or "")
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _limit_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def detailed_match_score(resume_text: str, job_description: str) -> dict:
    """
    Returns {'match_score': int, 'matched_skills': list[str], 'missing_skills': list[str], 'skill_score': int, 'exp_score': int, 'keyword_score': int}
    """
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)
    
    matched = [s for s in resume_skills if s in job_skills]
    missing = [s for s in job_skills if s not in resume_skills]
    
    keyword_score = int(100 * len(matched) / max(len(job_skills), 1)) if job_skills else 0
    skill_score = keyword_score
    exp_score = 50  # Placeholder
    
    overall = int((skill_score * 0.6) + (exp_score * 0.2) + (keyword_score * 0.2))
    
    return {
        'match_score': overall,
        'matched_skills': matched,
        'missing_skills': missing[:10],
        'skill_score': skill_score,
        'exp_score': exp_score,
        'keyword_score': keyword_score
    }

def extract_skills(text: str) -> list[str]:
    COMMON_TECH_TERMS = {
        'python', 'javascript', 'react', 'node', 'java', 'sql', 'docker', 'aws', 'git', 'ml',
        'data science', 'devops', 'fullstack', 'frontend', 'backend', 'angular', 'vue', 'typescript',
        'mongodb', 'postgres', 'redis', 'kubernetes'
    }
    words = re.findall(r'\\b[a-zA-Z][a-zA-Z0-9+#.-]{{1,20}}\\b', text.lower())
    skills = [w for w in words if w in COMMON_TECH_TERMS]
    return list(set(skills))[:15]

def score_job_match(resume_text: str, job_description: str) -> int:
    detail = detailed_match_score(resume_text, job_description)
    return detail['match_score']


def explain_job_match(resume_text: str, job_description: str) -> str:
    if not settings.openai_api_key:
        return ""
    resume_short = _limit_text(resume_text, MAX_RESUME_CHARS)
    job_short = _limit_text(job_description, MAX_JOB_CHARS)
    prompt = f"""
Explain why this resume matches the job in 3-5 concise bullet points.

RESUME:
{resume_short}

JOB:
{job_short}
"""
    try:
        response = _get_client().responses.create(
            model=settings.openai_model,
            input=prompt,
        )
        return (response.output_text or "").strip()
    except Exception:
        return ""


def generate_application_content(
    resume_text: str,
    job_title: str,
    company_name: str,
    job_description: str,
) -> str:
    if not settings.openai_api_key:
        return "OpenAI API key missing. Set OPENAI_API_KEY to enable generation."
    resume_short = _limit_text(resume_text, MAX_RESUME_CHARS)
    job_short = _limit_text(job_description, MAX_JOB_CHARS)
    prompt = f"""You are an expert recruiter creating a highly personalized cover letter for {job_title} at {company_name}.

CRITICAL REQUIREMENTS:
1. ANALYZE job description - extract 3-5 SPECIFIC requirements (skills, experience, responsibilities)
2. MAP exact resume achievements/experience matching each requirement  
3. Write conversationally - like the candidate wrote it themselves
4. Show company research - mention specific aspects of {company_name} 
5. Structure: Opening + 3 body paragraphs (each tying resume TO job req) + enthusiastic close

RESUME EXCERPTS (pull key achievements):
{resume_short}

JOB REQUIREMENTS ANALYSIS:
- Title: {job_title}
- Company: {company_name} 
- Key requirements: {job_short}

DETAILED COVER LETTER (400-500 words):
"""
    try:
        response = _get_client().chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return "AI generation failed. Please try again."
