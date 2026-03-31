import argparse
import os

from job_utils import read_resume_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Print resume text from a PDF.")
    parser.add_argument("--resume", default="AasthaChawlaResume.pdf", help="Resume PDF")
    args = parser.parse_args()

    if not os.path.isfile(args.resume):
        print(f"Resume not found: {args.resume}")
        return 1

    text = read_resume_text(args.resume)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
