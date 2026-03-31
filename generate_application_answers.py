import argparse
import os

from job_utils import read_json, run_ollama_prompt, sanitize_filename


def _fallback_application(resume: dict, job: dict) -> str:
    name = resume.get("name") or "Candidate"
    title = job.get("title") or "the role"
    company = job.get("company") or "the company"
    skills = ", ".join(resume.get("skills") or []) or "relevant skills"
    return (
        f"COVER LETTER\n\n"
        f"Dear Hiring Manager,\n\n"
        f"I am applying for {title} at {company}. I bring {skills} "
        f"and a track record of delivering results through data-driven work. "
        f"I would welcome the opportunity to contribute and grow with your team.\n\n"
        f"Sincerely,\n{name}\n\n"
        f"WHY I AM A GOOD FIT\n\n"
        f"- My background aligns with the core requirements in the job description.\n"
        f"- I have applied similar methods to solve real problems and communicate results.\n"
        f"- I enjoy collaborative, fast-moving environments and continuous learning.\n\n"
        f"RELEVANT EXPERIENCE\n\n"
        f"- Projects involving analysis, modeling, and stakeholder communication.\n"
        f"- Hands-on work with data pipelines and experimentation.\n\n"
        f"KEY SKILLS\n\n"
        f"- {skills}\n\n"
        f"WHY THIS COMPANY\n\n"
        f"- The role and mission at {company} are a strong fit for my interests.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate application answers for shortlisted jobs.")
    parser.add_argument("--shortlisted", default="shortlisted_jobs.json", help="Shortlisted jobs JSON")
    parser.add_argument("--resume-profile", default="resume_profile.json", help="Resume profile JSON")
    parser.add_argument("--out-dir", default="generated_applications", help="Output folder")
    parser.add_argument("--limit", type=int, default=20, help="Max applications to generate")
    parser.add_argument("--model", default=None, help="Ollama model name (default: env OLLAMA_MODEL)")
    args = parser.parse_args()

    resume = read_json(args.resume_profile, default={}) or {}
    jobs = read_json(args.shortlisted, default=[])
    if not jobs:
        print(f"No shortlisted jobs found in {args.shortlisted}.")
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    model = args.model

    total = 0
    for job in jobs[: args.limit]:
        prompt = f"""
You are an AI assistant preparing a professional job application.

Rules:
- Do NOT repeat the resume
- Do NOT list skills mechanically
- Keep tone human, concise, and confident

Resume:
Name: {resume.get('name') or ''}
Skills: {', '.join(resume.get('skills') or [])}
Experience years: {resume.get('experience_years') or ''}
Target roles: {', '.join(resume.get('target_roles') or [])}

Job:
Title: {job.get('title') or ''}
Company: {job.get('company') or ''}
Location: {job.get('location') or ''}
Description:
{job.get('description') or ''}

Generate:
1) Cover Letter
2) Why are you a good fit for this role?
3) Relevant experience
4) Key skills for this role
5) Why do you want to work at this company?
"""

        output = run_ollama_prompt(prompt, model=model)
        if not output:
            output = _fallback_application(resume, job)

        filename = sanitize_filename(f"{job.get('title')}_{job.get('company')}_application.txt")
        path = os.path.join(args.out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(output)
        total += 1

    print("Application answers generated.")
    print(f"- Output folder: {args.out_dir}")
    print(f"- Files created: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
