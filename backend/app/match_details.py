from typing import Dict, List, Optional, Tuple
import re
from .ai import score_job_match, explain_job_match

COMMON_TECH_TERMS = {
    'python', 'javascript', 'react', 'node.js', 'java', 'sql', 'docker', 'aws', 'git',
    'machine learning', 'data science', 'devops', 'fullstack', 'frontend', 'backend',
    'angular', 'vue', 'typescript', 'mongodb', 'postgres', 'redis', 'kubernetes',
    # Add more as needed
}

def extract_skills(text: str) -> List[str]:
    """Simple heuristic skill extraction"""
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9+#.-]{,50}\b', text.lower())
    skills = [w for w in words if w in COMMON_TECH_TERMS or len(w) > 3]
    return list(set(skills))[:20]  # Top 20 unique

def heuristic_detailed_match(resume_text: str, job_description: str) -> Dict:
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)
    
    matched = [s for s in resume_skills if s in job_skills]
    missing = [s for s in job_skills if s not in resume_skills]
    
    keyword_score = int(100 * len(matched) / max(len(job_skills), 1)) if job_skills else 0
    skill_score = keyword_score  # Simplified
    exp_score = 50  # Placeholder - could parse years
    
    overall = int((skill_score * 0.6) + (exp_score * 0.2) + (keyword_score * 0.2))
    
    return {
        'match_score': overall,
        'matched_skills': matched,
        'missing_skills': missing[:10],
        'skill_score': skill_score,
        'exp_score': exp_score,
        'keyword_score': keyword_score
    }

def detailed_match_score(resume_text: str, job_description: str) -> Dict:
    \"\"\"Returns detailed match with skills breakdown\"\"\"
    if not settings.openai_api_key:
        return heuristic_detailed_match(resume_text, job_description)
    
    resume_short = _limit_text(resume_text, MAX_RESUME_CHARS)
    job_short = _limit_text(job_description, MAX_JOB_CHARS)
    
    prompt = f\"\"\"Analyze resume-job match and return VALID JSON only:
{{
  \\"match_score\\": 0-100 number,
  \\"matched_skills\\": [\\"skill1\\", \\"skill2\\"],
  \\"missing_skills\\": [\\"skill1\\", \\"skill2\\"],
  \\"skill_score\\": 0-100,
  \\"exp_score\\": 0-100, 
  \\"keyword_score\\": 0-100
}}

RESUME:
{resume_short}

JOB:
{job_short}

Respond ONLY with valid JSON.\"\"\"
    
    try:
        response = _get_client().responses.create(
            model=settings.openai_model,
            input=prompt,
        )
        # Parse JSON response - simplified
        text = response.output_text or ""
        # Extract JSON block
        json_match = re.search(r'\\{.*\\}', text, re.DOTALL)
        if json_match:
            # Would parse JSON here - fallback for now
            pass
        score = score_job_match(resume_text, job_description)
        detail = heuristic_detailed_match(resume_text, job_description)
        detail['match_score'] = score
        return detail
    except Exception:
        return heuristic_detailed_match(resume_text, job_description)
