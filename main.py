"""
main.py — Entry point for timetable processing pipeline.
Run:
    python main.py                      # full pipeline
    python main.py --dry-run            # preview DB rows without writing
    python main.py --skip-subjects      # skip PDF parsing (subjects already in DB)
    python main.py --skip-teachers      # skip PDF parsing (teachers already in DB)
"""

import argparse
from parsers.nanonets_docstrange import extract_json


def main():
    ap = argparse.ArgumentParser(description="Timetable Processing Pipeline")
    ap.add_argument("--timetable-pdf",   default="uploads/timetable.pdf")
    ap.add_argument("--subjects-pdf",    default="uploads/subjects.pdf")
    ap.add_argument("--teachers-pdf",    default="uploads/teachers.pdf")
    ap.add_argument("--timetable-json",  default="uploads/timetable.json",
                    help="Use existing JSON instead of re-calling Nanonets API")
    ap.add_argument("--skip-subjects",   action="store_true")
    ap.add_argument("--skip-teachers",   action="store_true")
    ap.add_argument("--skip-nanonets",   action="store_true",
                    help="Skip Nanonets API call, use existing timetable.json")
    ap.add_argument("--cid",   type=int, default=1)
    ap.add_argument("--sem",   type=int, default=5)
    ap.add_argument("--year",  default="2025-26")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview parsed rows without inserting into DB")
    args = ap.parse_args()

    # ── Step 1: Insert Subjects ──────────────────────────────────────────
    if not args.skip_subjects:
        print("\n Parsing subjects...")
        from parsers.subjects_parser import parse_subjects
        parse_subjects(args.subjects_pdf, sem=args.sem)
    else:
        print("⏭  Skipping subjects (--skip-subjects)")

    # ── Step 2: Insert Teachers ──────────────────────────────────────────
    if not args.skip_teachers:
        print("\n Parsing teachers...")
        from parsers.teachers_parser import parse_teachers
        parse_teachers(args.teachers_pdf)
    else:
        print("⏭  Skipping teachers (--skip-teachers)")

    # ── Step 3: Extract JSON from PDF (or use existing) ──────────────────
    if not args.skip_nanonets:
        print("\n Calling Nanonets API...")
        extract_json(args.timetable_pdf)
    else:
        print(f"⏭  Skipping Nanonets (using {args.timetable_json})")

    # ── Step 4: Parse JSON → DB ──────────────────────────────────────────
    print("\n  Parsing timetable JSON → DB...")
    from parsers.json_to_db import parse_and_store
    parse_and_store(
        json_path=args.timetable_json,
        cid=args.cid,
        sem=args.sem,
        academic_year=args.year,
        dry_run=args.dry_run,
    )
    print("\n Pipeline complete.")


if __name__ == "__main__":
    main()