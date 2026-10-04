"""Merge every judged question so far into one compact file the site and the daily job build on.

Reads the Jev results (jev_years.jsonl, jev_months.jsonl) and the downloaded months for their
metadata, and writes:
  data/judgments.jsonl     one line per judged question, no question/reply text
  data/monthly_asked.json  questions asked per month (all of them, not just the judged sample)

The raw pqs_*.jsonl downloads are ~500 MB and stay out of the repo; this runs once locally.
After this, the daily job appends new questions to judgments.jsonl itself.

Usage:  python compact.py
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
MONTH_FILE = re.compile(r"pqs_(\d{4}-\d{2})-01_\d{4}-\d{2}-\d{2}\.jsonl")


def read_jsonl(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def compact(row, jev, source):
    a = jev["answers"]
    return {
        "id": row["id"], "date": row["date"], "to": row["to"], "group_size": row["group_size"],
        "clarity": a["clarity"]["choice"], "clarity_p": a["clarity"]["probabilities"],
        "technique": a["technique"]["choice"], "referred": round(a["referred"]["noul"], 3),
        "tokens": jev["usage"]["input_tokens"], "provider": jev.get("provider", "openrouter"),
        "source": source,
    }


def main():
    jev = {}
    for name, source in (("jev_years.jsonl", "march-sample"), ("jev_months.jsonl", "month-sample")):
        for r in read_jsonl(DATA / name):
            jev[r["id"]] = (r, source)

    out, asked = [], {}
    for p in sorted(DATA.glob("pqs_*.jsonl")):
        m = MONTH_FILE.fullmatch(p.name)
        if not m:
            continue
        rows = read_jsonl(p)
        asked[m.group(1)] = len(rows)
        out += [compact(r, *jev[r["id"]]) for r in rows if r["id"] in jev]

    out.sort(key=lambda r: (r["date"], r["id"]))
    with (DATA / "judgments.jsonl").open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (DATA / "monthly_asked.json").write_text(json.dumps(asked, indent=1), encoding="utf-8")
    print(f"{len(out)} judgments ({len(jev) - len(out)} unmatched), {len(asked)} months counted")


if __name__ == "__main__":
    main()
