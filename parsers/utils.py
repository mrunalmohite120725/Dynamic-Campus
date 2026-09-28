"""
parsers/utils.py
----------------
Shared normalization helpers used by BOTH teachers_parser.py and json_to_db.py.
Keeping them in one place guarantees that the stored form and lookup form
are ALWAYS identical, preventing duplicate teacher rows.
"""

import re

# Academic title prefixes (longest-first so 'prof.' is stripped before 'pro.')
_TITLES = ["prof.", "pro.", "dr.", "mr.", "ms.", "mrs.", "prof ", "dr "]


def normalize_teacher(name: str) -> str:
    """
    Canonical teacher-name normalisation:
      1. Lowercase
      2. Strip academic title prefixes
      3. Remove all dots  (initials: 'a.d.' → 'ad')
      4. Collapse whitespace

    Examples:
      'Prof.A.A.Chandorkar' → 'aa chandorkar'
      'Prof. J.S. Mahajan'  → 'js mahajan'
      'Dr. S.N. Girme'      → 'sn girme'
      'deepika kumari'      → 'deepika kumari'
    """
    if not name:
        return ""
    name = name.lower().strip()
    for title in _TITLES:
        name = name.replace(title, "")
    name = re.sub(r'\.\s+', '.', name)   # "K. R." → "K.R." before dot removal
    name = name.replace(".", "")          # remove dots from initials
    return " ".join(name.split())         # collapse multi-spaces
