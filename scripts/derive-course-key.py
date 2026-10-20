#!/usr/bin/env python3
"""AthenIQ — derive course key and term from classroom brief."""

import re
import sys
from datetime import datetime


def derive_key(brief: str, explicit: str | None = None) -> str:
    """Derive course key and term from classroom brief.

    Returns a course key in the format:
    course-v1:InnotelLabs+{code}+{term}

    If explicit is provided, it is returned as-is.
    Otherwise, the course code is extracted from the brief if it mentions
    patterns like MAIC101, FAI101, etc. Otherwise the user is prompted.
    The term is derived from the current date (T1 = Sep-Jan, T2 = Feb-Aug).
    """
    if explicit:
        return explicit

    # Extract course code from brief if mentions MAIC101, FAI101, etc.
    m = re.search(r'[A-Z]{3,5}\d{3}', brief)
    if m:
        code = m.group(0)
    else:
        code = input("Enter course code (e.g. MAIC101): ").strip()

    # Derive term: current term based on month
    today = datetime.now()
    # T1 = Sep-Jan (months 1-9 in Southern hemisphere, but we use calendar year)
    # Actually: if month >= 9, it's T2 (Feb-Aug of next year), otherwise T1
    # Simpler: use the academic term convention
    if today.month >= 9:
        term = f"{today.year}_T2"
    else:
        term = f"{today.year}_T1"

    return f"course-v1:InnotelLabs+{code}+{term}"


if __name__ == "__main__":
    brief = sys.stdin.read() if not sys.isatty() else input("Brief: ")
    print(derive_key(brief))