"""Download every month in a range (default Jan 2024 - Sep 2026) with fetch_pqs.py, skipping ones already on disk.

Usage:  python fetch_months.py [2024-01] [2026-09]
"""
import calendar
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def months(start, end):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


if __name__ == "__main__":
    start, end = (sys.argv[1:3] + ["2024-01", "2026-09"][len(sys.argv[1:3]):])[:2]
    for y, m in months(start, end):
        a = f"{y}-{m:02d}-01"
        b = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
        if (HERE / "data" / f"pqs_{a}_{b}.jsonl").exists():
            continue
        subprocess.run([sys.executable, str(HERE / "fetch_pqs.py"), a, b], check=True)
