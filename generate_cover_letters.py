import argparse
import os

from job_utils import read_json, run_ollama_prompt, sanitize_filename


def _fallback_cover_letter(resume: dict, job: dict) -> str:
    name = resume.get("name") or "Candidate"
    title = job.get("title") or "the role"
    company = job.get("company") or "your company"
    skills = ", ".join(resume.get("skills") or []) or "relevant skills"
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to apply for {title} at {company}. "
        f"My background includes {skills}, and I have delivered measurable impact "
        f"through data-driven work. I am excited about the opportunity to contribute "
        f"to {company}'s goals and collaborate with the team.\n\n"
        f"Thank you for your time and consideration.\n"
        f"Sincerely,\n{name}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate cover letters for shortlisted jobs.")
    parser.add_argument("--shortlisted", default="shortlisted_jobs.json", help="Shortlisted jobs JSON")
    parser.add_argument("--resume-profile", default="resume_profile.json", help="Resume profile JSON")
    parser.add_argument("--out-dir", default="generated_cover_letters", help="Output folder")
    parser.add_argument("--limit", type=int, default=20, help="Max letters to generate")
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
Write a professional, tailored cover letter.
Rules:
- Be concise (3 short paragraphs max)
- Do NOT repeat the resume
- Do NOT list skills mechanically
- Sound human, confident, and specific

Candidate:
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
"""

        output = run_ollama_prompt(prompt, model=model)
        if not output:
            output = _fallback_cover_letter(resume, job)

        filename = sanitize_filename(f"{job.get('title')}_{job.get('company')}.txt")
        path = os.path.join(args.out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(output)
        total += 1

    print("Cover letters generated.")
    print(f"- Output folder: {args.out_dir}")
    print(f"- Files created: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
