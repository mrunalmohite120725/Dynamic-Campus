"""
subjects_parser.py
Parses subjects from a PDF and inserts them into DB.
Handles multi-word subject names (LP II, HON AI, etc.) and deduplicates before insert.
"""

import pdfplumber
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection


SKIP_WORDS = {"subject", "semester", "sem", "code", "name", "sr", "no", "s.no"}


def parse_subjects(pdf_path: str, sem: int = 5):
    conn   = get_connection()
    cursor = conn.cursor()

    subjects = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Skip header lines
                lower = line.lower()
                if any(w in lower.split() for w in SKIP_WORDS):
                    continue

                parts = line.split()
                if not parts:
                    continue

                subject_sem = sem
                if parts[-1].isdigit():
                    subject_sem = int(parts[-1])
                    parts = parts[:-1]

                if parts:
                    subject_name = " ".join(parts)
                    subjects[subject_name] = subject_sem

    inserted = 0
    updated  = 0
    for sname, s_sem in subjects.items():
        cursor.execute("SELECT sid, sem FROM subjects WHERE sname = %s", (sname,))
        row = cursor.fetchone()
        
        if not row:
            cursor.execute(
                "INSERT INTO subjects (sname, sem) VALUES (%s, %s)",
                (sname, s_sem)
            )
            inserted += 1
        elif row[1] != s_sem:
            cursor.execute(
                "UPDATE subjects SET sem = %s WHERE sid = %s",
                (s_sem, row[0])
            )
            updated += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Subjects inserted: {inserted} | Updated: {updated}")