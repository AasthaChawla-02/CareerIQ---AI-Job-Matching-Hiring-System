import argparse
import os

from job_utils import extract_resume_profile, read_resume_text, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract resume profile JSON using a local LLM.")
    parser.add_argument("--resume", default="AasthaChawlaResume.pdf", help="Path to resume PDF")
    parser.add_argument("--out", default="resume_profile.json", help="Output JSON file")
    parser.add_argument("--text-out", default="resume_text.txt", help="Output resume text file")
    parser.add_argument("--model", default=None, help="Ollama model name (default: env OLLAMA_MODEL)")
    args = parser.parse_args()

    if not os.path.isfile(args.resume):
        print(f"Resume not found: {args.resume}")
        return 1

    resume_text = read_resume_text(args.resume)
    if not resume_text:
        print("Resume text is empty. Check the PDF content.")
        return 1

    model = args.model or None
    profile = extract_resume_profile(resume_text, model=model)
    write_json(args.out, profile)

    if args.text_out:
        with open(args.text_out, "w", encoding="utf-8") as f:
            f.write(resume_text)

    print("Resume profile saved:")
    print(f"- JSON: {args.out}")
    print(f"- Text: {args.text_out}")
    print(f"- Name: {profile.get('name') or 'Unknown'}")
    print(f"- Skills: {len(profile.get('skills') or [])}")
    print(f"- Target roles: {len(profile.get('target_roles') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
