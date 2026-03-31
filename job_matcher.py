import argparse
import os

from job_utils import read_json, read_resume_text, score_job_match, write_json


def _read_resume_text(resume_path: str, resume_text_path: str) -> str:
    if resume_text_path and os.path.isfile(resume_text_path):
        with open(resume_text_path, "r", encoding="utf-8") as f:
            return f.read()
    if resume_path and os.path.isfile(resume_path):
        return read_resume_text(resume_path)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Score job matches using a local LLM.")
    parser.add_argument("--jobs", default="jobs.json", help="Input jobs JSON")
    parser.add_argument("--out", default="scored_jobs.json", help="Output scored JSON")
    parser.add_argument("--resume", default="AasthaChawlaResume.pdf", help="Resume PDF")
    parser.add_argument("--resume-text", default="resume_text.txt", help="Resume text file")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum score to keep")
    parser.add_argument("--max-jobs", type=int, default=30, help="Max jobs to score")
    parser.add_argument("--model", default=None, help="Ollama model name (default: env OLLAMA_MODEL)")
    args = parser.parse_args()

    jobs = read_json(args.jobs, default=[])
    if not jobs:
        print(f"No jobs found in {args.jobs}.")
        return 1

    resume_text = _read_resume_text(args.resume, args.resume_text)
    if not resume_text:
        print("Resume text not found. Provide --resume or --resume-text.")
        return 1

    scored = []
    model = args.model or None
    for job in jobs[: args.max_jobs]:
        description = job.get("description") or ""
        score = score_job_match(resume_text, description, model=model)
        job["match_score"] = score
        if score >= args.min_score:
            scored.append(job)

    write_json(args.out, scored)

    print("Job matching complete.")
    print(f"- Jobs scored: {min(len(jobs), args.max_jobs)}")
    print(f"- Jobs kept: {len(scored)}")
    print(f"- Output: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
