"""
teachers_parser.py
Parses teachers from a PDF and inserts into DB.
Teacher names are normalised via the shared utils.normalize_teacher so that
the stored form always matches what json_to_db.py looks up.
"""

import pdfplumber
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection
from parsers.utils import normalize_teacher


TITLE_TOKENS = {"prof.", "pro.", "dr.", "mr.", "ms.", "mrs."}


def parse_teachers(pdf_path: str):
    conn   = get_connection()
    cursor = conn.cursor()

    teachers_raw = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line  = line.strip()
                lower = line.lower()
                # Pick lines that contain an academic title
                if any(t in lower for t in TITLE_TOKENS) or "dr." in lower:
                    teachers_raw.add(line)

    # Import here to avoid circular imports if any
    from parsers.json_to_db import get_teacher_id

    inserted = 0
    for raw_name in teachers_raw:
        norm = normalize_teacher(raw_name)
        if not norm:
            continue
        
        # Check if teacher exists (using normalised matching)
        existing_tid = get_teacher_id(cursor, raw_name)
        if existing_tid:
            continue
            
        # If truly new, insert the original official display name
        cursor.execute("INSERT IGNORE INTO teachers (tname) VALUES (%s)", (raw_name,))
        if cursor.rowcount:
            inserted += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Teachers inserted: {inserted} (duplicates automatically skipped)")