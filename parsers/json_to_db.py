"""
json_to_db.py — Robust Timetable Cell Parser
=============================================
Handles:
  - Multi-subject + multi-batch slots  e.g. "LP II K1 L1 WTL M1"
  - HON-prefix abbreviated subjects    e.g. "HON AI A1-309 SML A1-310 EAC A1-311"
  - Room vs Batch disambiguation       rooms: A1-309 | batches: K1 L1 M1
  - Consecutive slot merging
  - Internship (tid=NULL, room=NULL)
  - Theory (batch=NULL, room=classroom)
  - Practical (batch required, room=lab from JSON)
"""

import json
import re
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection
from parsers.utils import normalize_teacher   # single canonical implementation


# ---------------------------------------------------------------------------
# NORMALISATION HELPERS
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Strip spaces, dots, dashes, underscores → lowercase."""
    if not text:
        return ""
    return re.sub(r'[\s.\-_]', '', text).lower()


# normalize_teacher is imported from parsers.utils — do not redefine it here.


# ---------------------------------------------------------------------------
# TOKEN CLASSIFIERS
# ---------------------------------------------------------------------------

# Room:  A1-309, F1-101, A2-205  (building-letter + digits + dash + digits)
# Also matches A1-102[THUA1-314] because the pattern anchors on the START
ROOM_RE = re.compile(r'^[A-Z]\d+-\d+')

# Batch: K1, L1, M1, N1, A1 … (single-letter + one-or-more digits, NO dash)
BATCH_RE = re.compile(r'^[A-Z]\d+$')

IGNORE_CELLS = {"break", "lunchbreak", "lunch"}
IGNORE_SUBJECTS = {"internship", "honsemiar", "honseminar", "break", "lunch"}


def is_room_token(token: str) -> bool:
    return bool(ROOM_RE.match(token))


def is_batch_token(token: str) -> bool:
    """True for tokens like K1, L1, M1 — but NOT room tokens like A1-309."""
    return bool(BATCH_RE.match(token)) and not is_room_token(token)


def clean_lab(lab: str) -> str:
    """Extract primary room from strings like 'A1-102[THUA1-314]'."""
    if not lab:
        return lab
    m = ROOM_RE.match(lab)
    return m.group(0) if m else lab


# ---------------------------------------------------------------------------
# SUBJECT LOADING & MATCHING
# ---------------------------------------------------------------------------

def load_subjects(cursor):
    """
    Returns sorted list of (normalized_name, original_name).
    Sorted longest-first so 'LP II' matches before 'LP'.
    """
    cursor.execute("SELECT sid, sname FROM subjects")
    rows = cursor.fetchall()
    subjects = [(normalize(sname), sname, sid) for sid, sname in rows]
    subjects.sort(key=lambda x: len(x[0]), reverse=True)
    return subjects  # [(norm, orig, sid), ...]


def match_subject(phrase: str, subjects):
    """
    Match phrase against known subjects.
    Priority:
      1) Exact normalised match          e.g. 'lpii' == 'lpii'
      2) Starts-with match               e.g. 'mdmbfsi...' matches 'MDM BFSI'
      3) Suffix match for abbreviations  e.g. 'is' matches 'eleis' (ELE-IS)
    Returns (original_name, sid) or (None, None).
    """
    norm = normalize(phrase)
    if not norm:
        return None, None

    # 1. Exact match
    for norm_sub, orig_sub, sid in subjects:
        if norm_sub == norm:
            return orig_sub, sid

    # 2. Starts-with match (longest subject first — list is sorted longest-first)
    #    Ensures 'MDM BFSI' cell text matches 'MDM BFSI' before 'MDM'
    for norm_sub, orig_sub, sid in subjects:
        if norm.startswith(norm_sub) and len(norm_sub) > 2:
            return orig_sub, sid

    # 3. Suffix match — only for short abbreviations (2-4 chars)
    #    Prevents false positives: 'dsbda' will NOT match 'dsbdal'
    if 2 <= len(norm) <= 4:
        for norm_sub, orig_sub, sid in subjects:
            if norm_sub.endswith(norm) and len(norm_sub) > len(norm):
                return orig_sub, sid

    return None, None


# ---------------------------------------------------------------------------
# TEACHER & ROOM LOOKUP FROM JSON CONTENT
# ---------------------------------------------------------------------------

def build_practical_index(content: dict) -> dict:
    """
    Returns dict: { (normalize(subject), batch) → {staff, lab} }
    """
    index = {}
    # Nanonets uses different key names across PDFs — check all variants
    practical_data = (content.get("practical_staff") or
                      content.get("practical_details") or
                      content.get("practical_staff_lab") or [])
    
    if isinstance(practical_data, dict):
        for subj, entries in practical_data.items():
            norm_subj = normalize(subj)
            for e in entries:
                batch = e.get("batch", "").strip()
                index[(norm_subj, batch)] = {
                    "staff": e.get("staff", ""),
                    "lab":   clean_lab(e.get("lab", "")),
                }
    elif isinstance(practical_data, list):
        for e in practical_data:
            subj = e.get("subject", "")
            batch = e.get("batch", "").strip()
            index[(normalize(subj), batch)] = {
                "staff": e.get("staff", ""),
                "lab":   clean_lab(e.get("lab", "")),
            }
    return index


def build_theory_index(content: dict) -> dict:
    """
    Returns dict: { normalize(course) → staff_name }
    """
    index = {}
    for t in content.get("theory_staff", []):
        course = t.get("course", "")
        index[normalize(course)] = t.get("staff", "")
    return index


def get_teacher_id(cursor, name: str) -> int | None:
    """Look up teacher id by name, with normalisation and partial-match fallback."""
    if not name:
        return None
    norm_input = normalize_teacher(name)
    if not norm_input:
        return None

    # Fetch ALL rows once and store — do NOT call fetchall() twice
    cursor.execute("SELECT tid, tname FROM teachers")
    all_teachers = cursor.fetchall()   # list of (tid, tname)

    # 1. Exact normalised match
    for tid, tname in all_teachers:
        if normalize_teacher(tname) == norm_input:
            return tid

    # 2. Partial match — one contains the other (handles middle-name variants)
    for tid, tname in all_teachers:
        norm_db = normalize_teacher(tname)
        if norm_input in norm_db or norm_db in norm_input:
            return tid


def auto_insert_teacher(cursor, conn, name: str) -> int | None:
    """
    If a teacher name from the PDF JSON is not in the DB, insert them
    automatically so that tid is never NULL. Returns the new (or existing) tid.

    Storage strategy:
      - STORE the normalized name (e.g. 'aachandorkar') to prevent duplicates.
      - Both teachers_parser.py and json_to_db.py will insert identical strings.

    Deduplication:
      1. get_teacher_id() uses normalized matching — if a match exists, return it.
      2. No insert needed — existing tid returned.
      3. If truly new, insert the normalized name and return new tid.
    """
    display = (name or "").strip()
    if not display:
        return None

    norm_name = normalize_teacher(display)
    if not norm_name:
        return None

    # Check for existing teacher via normalized comparison
    existing = get_teacher_id(cursor, display)
    if existing:
        return existing

    # Not found — insert original display name
    cursor.execute("INSERT IGNORE INTO teachers (tname) VALUES (%s)", (display,))
    conn.commit()
    if cursor.rowcount == 0:
        # Race condition: someone else inserted — look it up
        existing = get_teacher_id(cursor, display)
        return existing

    new_tid = cursor.lastrowid
    print(f"  [AUTO-TEACHER] Inserted new teacher: '{display}' (tid={new_tid})")
    return new_tid


# ---------------------------------------------------------------------------
# CELL PARSER — STATE MACHINE
# ---------------------------------------------------------------------------

def parse_cell(text: str, subjects) -> list:
    """
    Parse a timetable cell into a list of entries.
    Returns: [ (subject_name, sid, batch_or_None, room_override_or_None), ... ]

    Algorithm:
      Scan tokens left-to-right.
      - Room token   → attach to current subject as room override
      - Batch token  → accumulate for current subject
      - Subject match (longest-first) → emit previous, start new
      - HON-prefix fallback: after a HON subject, try "HON <token>" for unknowns
    """
    tokens = text.split()
    results = []

    current_subject = None
    current_sid = None
    current_batches = []
    current_room = None
    hon_context = False   # True when last matched subject started with "HON"

    def emit():
        if current_subject is None:
            return
        if current_batches:
            for b in current_batches:
                results.append((current_subject, current_sid, b, current_room))
        else:
            results.append((current_subject, current_sid, None, current_room))

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # ── ROOM TOKEN ──────────────────────────────────────────────────────
        if is_room_token(token):
            current_room = clean_lab(token)
            i += 1
            continue

        # ── BATCH TOKEN ─────────────────────────────────────────────────────
        if is_batch_token(token):
            if current_subject is not None:
                current_batches.append(token)
            i += 1
            continue

        # ── SUBJECT MATCH (greedy: try 3-word, 2-word, 1-word) ──────────────
        matched_sub = None
        matched_sid = None
        matched_len = 0

        for n in range(min(3, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i:i + n])

            sub, sid = match_subject(phrase, subjects)
            if sub:
                matched_sub, matched_sid, matched_len = sub, sid, n
                break

            # HON-prefix fallback: only try if we're inside a HON group
            if hon_context:
                hon_phrase = "HON " + phrase
                sub, sid = match_subject(hon_phrase, subjects)
                if sub:
                    matched_sub, matched_sid, matched_len = sub, sid, n
                    break

        if matched_sub:
            emit()
            current_subject = matched_sub
            current_sid = matched_sid
            current_batches = []
            current_room = None
            hon_context = normalize(matched_sub).startswith("hon")
            i += matched_len
        else:
            # Unknown token — skip silently
            i += 1

    emit()
    return results


# ---------------------------------------------------------------------------
# TIME UTILITIES
# ---------------------------------------------------------------------------

def parse_time(time_str: str) -> tuple[str, str] | None:
    """
    Parse time strings like '08:45 to 09:45' or '10.45 to 11:00'.
    Converts afternoon times (1:00 to 7:00) to 24-hour format.
    Returns ('08:45', '13:00') or None for BREAK slots.
    """
    if not time_str:
        return None
    time_str = time_str.replace(".", ":")
    parts = time_str.lower().split("to")
    if len(parts) != 2:
        return None
    start = parts[0].strip()
    end   = parts[1].strip()
    # Validate HH:MM
    if not re.match(r'^\d{1,2}:\d{2}$', start):
        return None
    if not re.match(r'^\d{1,2}:\d{2}$', end):
        return None
    
    def to_24h(t: str) -> str:
        h, m = t.split(":")
        hi = int(h)
        # Any hour from 1 to 7 is considered PM (13:00 to 19:00)
        if 1 <= hi <= 7:
            hi += 12
        return f"{hi:02d}:{m}"
        
    return to_24h(start), to_24h(end)


# ---------------------------------------------------------------------------
# SLOT MERGING (consecutive identical slots → one longer slot)
# ---------------------------------------------------------------------------

def merge_slots(entries: list) -> list:
    """
    Merge consecutive time slots with the same (day, sid, batch, tid, room).
    Input/output: list of dicts with keys day, sid, tid, batch, room, start, end.
    """
    if not entries:
        return []

    # Sort by day → sid → batch → start_time
    entries.sort(key=lambda x: (
        x["day"],
        str(x["sid"]),
        str(x["batch"]),
        x["start"]
    ))

    merged = []
    prev = dict(entries[0])

    for curr in entries[1:]:
        same = (
            prev["day"]   == curr["day"]   and
            prev["sid"]   == curr["sid"]   and
            prev["batch"] == curr["batch"] and
            prev["tid"]   == curr["tid"]   and
            prev["room"]  == curr["room"]
        )
        if same and prev["end"] == curr["start"]:
            prev["end"] = curr["end"]   # extend
        else:
            merged.append(prev)
            prev = dict(curr)

    merged.append(prev)
    return merged


# ---------------------------------------------------------------------------
# MAIN PARSE & STORE
# ---------------------------------------------------------------------------

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def parse_and_store(
    json_path: str = "uploads/timetable.json",
    cid: int = 1,
    sem: int = 5,
    academic_year: str = "2025-26",
    dry_run: bool = False,
):
    conn   = get_connection()
    cursor = conn.cursor()

    # ── Load JSON ──────────────────────────────────────────────────────────
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    content  = data["result"]["json"]["content"]
    # Nanonets might name the main array time_table, timetable, or schedule
    schedule = content.get("time_table") or content.get("timetable") or content.get("schedule") or []

    header      = content.get("header_info", {})
    classroom   = header.get("class_room", "")          # default theory room

    # ── Build lookup structures ────────────────────────────────────────────
    subjects         = load_subjects(cursor)             # [(norm, orig, sid), ...]
    practical_index  = build_practical_index(content)   # {(norm_subj, batch): {staff, lab}}
    theory_index     = build_theory_index(content)      # {norm_course: staff}

    # ── Auto-ensure special subjects exist in DB ───────────────────────────
    # INTERNSHIP must be in subjects so we can store it with tid=NULL, room=NULL
    # HON SEMINAR is NOT stored (per-student optional, not a fixed class slot)
    SPECIAL_AUTO_SUBJECTS = ["INTERNSHIP"]
    for special in SPECIAL_AUTO_SUBJECTS:
        found = any(normalize(s[1]) == normalize(special) for s in subjects)
        if not found and not dry_run:
            cursor.execute(
                "INSERT INTO subjects (sname, sem) VALUES (%s, %s)",
                (special.capitalize(), sem)
            )
            conn.commit()
            print(f"[AUTO] Inserted missing subject '{special}' into subjects table")
        elif not found:
            print(f"[WARN] '{special}' not in subjects table (will be skipped in dry-run)")
    # Reload after potential auto-inserts
    subjects = load_subjects(cursor)

    # ── Process each slot ─────────────────────────────────────────────────
    temp_entries = []
    warnings     = []

    for slot in schedule:
        time_str = slot.get("time", "")
        parsed   = parse_time(time_str)
        if parsed is None:
            continue                                     # BREAK or malformed time

        # Skip explicit break rows
        if any(k in normalize(time_str) for k in ["break", "lunch"]):
            continue

        start, end = parsed

        for day in DAYS:
            cell_text = slot.get(day)
            if not cell_text:
                continue

            cell_text = cell_text.strip()
            cell_norm = normalize(cell_text)

            # Skip BREAK / LUNCH
            if any(k in cell_norm for k in IGNORE_CELLS):
                continue

            # ── INTERNSHIP ─────────────────────────────────────────────────
            # Rules: tid=NULL, room=NULL, batch=NULL — still stored in DB
            if "internship" in cell_norm:
                _, sid = match_subject("INTERNSHIP", subjects)
                if sid:
                    entry = {
                        "day":   day.capitalize(),
                        "sid":   sid,
                        "tid":   None,
                        "batch": None,
                        "room":  None,
                        "start": start,
                        "end":   end,
                    }
                    if entry not in temp_entries:
                        temp_entries.append(entry)
                else:
                    warnings.append(
                        f"[SKIP] INTERNSHIP has no SID [{day.upper()} {start}] — add 'Internship' to subjects table"
                    )
                continue

            # ── HON SEMINAR standalone cells (Saturday carry-over / optional) ──
            # Per notes: 'As per availability and mutual convenience'
            # HON SEMIAR as a standalone cell = not a fixed scheduled slot → skip
            # HON AI / HON SML / HON EAC are REAL subjects → handled by parse_cell
            if cell_norm in {"honsemiar", "honseminar"}:
                # This only appears on Saturday (already excluded) or as filler
                continue

            # ── Parse cell (HON AI, HON SML, HON EAC, LP II, DSBDAL, etc.) ──
            parsed_entries = parse_cell(cell_text, subjects)

            if not parsed_entries:
                warnings.append(f"[WARN] Unmatched cell  [{day.upper()} {start}-{end}]: '{cell_text}'")
                continue

            for subj_name, sid, batch, room_override in parsed_entries:

                is_practical = batch is not None
                tid  = None
                room = None

                if is_practical:
                    # Look up in practical_staff
                    key = (normalize(subj_name), batch)
                    entry = practical_index.get(key)
                    if entry:
                        staff_name = entry["staff"]
                        if dry_run:
                            tid  = get_teacher_id(cursor, staff_name)
                        else:
                            tid  = auto_insert_teacher(cursor, conn, staff_name)
                        room = room_override or entry["lab"]
                    else:
                        warnings.append(
                            f"[WARN] No practical entry  [{day.upper()} {start}] {subj_name} batch={batch}"
                        )
                        room = room_override

                else:
                    # Theory — look up in theory_staff; try exact then partial
                    staff_name = theory_index.get(normalize(subj_name))
                    if not staff_name:
                        for t_norm, t_staff in theory_index.items():
                            if normalize(subj_name) in t_norm or t_norm in normalize(subj_name):
                                staff_name = t_staff
                                break

                    if staff_name:
                        if dry_run:
                            tid = get_teacher_id(cursor, staff_name)
                        else:
                            tid = auto_insert_teacher(cursor, conn, staff_name)
                    else:
                        warnings.append(
                            f"⚠ No theory staff   [{day.upper()} {start}] {subj_name}"
                        )

                    room = room_override or classroom

                record = {
                    "day":   day.capitalize(),
                    "sid":   sid,
                    "tid":   tid,
                    "batch": batch,
                    "room":  room,
                    "start": start,
                    "end":   end,
                }

                if record not in temp_entries:
                    temp_entries.append(record)

    # ── Merge consecutive slots ────────────────────────────────────────────
    print(f"[INFO] Before merge : {len(temp_entries)} rows")
    final_entries = merge_slots(temp_entries)
    print(f"[INFO] After  merge : {len(final_entries)} rows")

    # ── Print warnings ────────────────────────────────────────────────────
    if warnings:
        print(f"\n{'='*60}")
        print(f"[WARN] {len(warnings)} warnings (review before inserting):")
        for w in warnings:
            print(" ", w)
        print('='*60)

    # ── DRY RUN ───────────────────────────────────────────────────────────
    if dry_run:
        print("\n[DRY RUN] Preview only - no changes written to DB\n")
        print(f"{'DAY':<12} {'START':<8} {'END':<8} {'SID':<6} {'TID':<6} {'BATCH':<6} {'ROOM':<12}")
        print("-" * 70)
        for e in final_entries:
            print(
                f"{e['day']:<12} {e['start']:<8} {e['end']:<8} "
                f"{str(e['sid']):<6} {str(e['tid']):<6} {str(e['batch']):<6} {str(e['room']):<12}"
            )
        cursor.close()
        conn.close()
        return

    # ── INSERT ────────────────────────────────────────────────────────────
    inserted = 0
    skipped  = 0

    for e in final_entries:
        # Duplicate guard
        cursor.execute("""
            SELECT COUNT(*) FROM timetable
            WHERE cid=%s AND sid=%s AND day=%s AND start_time=%s AND end_time=%s
              AND COALESCE(batch,'') = COALESCE(%s,'')
        """, (cid, e["sid"], e["day"], e["start"], e["end"], e["batch"]))

        if cursor.fetchone()[0] > 0:
            skipped += 1
            continue

        cursor.execute("""
            INSERT INTO timetable
              (cid, sid, tid, day, start_time, end_time, batch, room, sem, academic_year)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            cid,
            e["sid"],
            e["tid"],
            e["day"],
            e["start"],
            e["end"],
            e["batch"],
            e["room"],
            sem,
            academic_year,
        ))
        inserted += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n[OK] Inserted : {inserted} rows")
    if skipped:
        print(f"[SKIP] Skipped  : {skipped} duplicates")


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Parse timetable JSON and store to DB")
    ap.add_argument("--json",     default="uploads/timetable.json", help="Path to timetable JSON")
    ap.add_argument("--cid",      type=int, default=1,               help="Class ID (cid)")
    ap.add_argument("--sem",      type=int, default=5,               help="Semester number")
    ap.add_argument("--year",     default="2025-26",                 help="Academic year")
    ap.add_argument("--dry-run",  action="store_true",               help="Preview without writing to DB")
    args = ap.parse_args()

    parse_and_store(
        json_path=args.json,
        cid=args.cid,
        sem=args.sem,
        academic_year=args.year,
        dry_run=args.dry_run,
    )