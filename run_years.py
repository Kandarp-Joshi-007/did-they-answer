"""Judge a random sample of written Dáil questions from March of each year, and report the trend.

For each data/pqs_YYYY-03-01_YYYY-03-31.jsonl it samples up to N answered questions (fixed seed)
and asks Jev the same three questions as jev.py. Results are cached in data/jev_years.jsonl,
so re-running only judges questions not yet judged.

Rates are reported with hand-offs ("the HSE will reply directly") counted separately, because
they are procedure rather than evasion. "No reply" rates are not reported: older months were
later backfilled with replies, so they are not comparable with recent ones.

Usage:  python run_years.py [--n 1000] [--report-only]
"""
import argparse
import collections
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev import api_key, judge_pq

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = DATA / "jev_years.jsonl"


def read_jsonl(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def months():
    return sorted(DATA.glob("pqs_*-03-01_*-03-31.jsonl"))


def sample(path, n, seed=1):
    rows = [r for r in read_jsonl(path) if r["reply"]]
    return random.Random(seed).sample(rows, min(n, len(rows)))


def run(n):
    key = api_key()
    done = {r["id"] for r in read_jsonl(OUT)}
    todo = [r for p in months() for r in sample(p, n) if r["id"] not in done]
    print(f"{len(todo)} questions to judge ({len(done)} cached)")

    def judge(row):
        try:
            out = judge_pq(row, key)
        except Exception as e:  # keep going; failed rows are retried on the next run
            return {"id": row["id"], "error": str(e)}
        return {"id": row["id"], "date": row["date"], "to": row["to"],
                "answers": out["answers"], "usage": out["usage"],
                "provider": out["provider"]}

    failed = 0
    with ThreadPoolExecutor(8) as pool, OUT.open("a", encoding="utf-8") as f:
        for res in pool.map(judge, todo):
            if "error" in res:
                failed += 1
                continue
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(f"done, {failed} failed (re-run to retry)")


def report():
    res = read_jsonl(OUT)
    by_year = collections.defaultdict(list)
    for r in res:
        by_year[r["date"][:4]].append(r)

    print(f"\n{'year':<6}{'asked':>7}{'judged':>8}{'handed off':>12}"
          f"{'clear':>8}{'partly':>8}{'non-reply':>11}   (shares of non-hand-off replies)")
    for p in months():
        year = p.name[4:8]
        full = read_jsonl(p)
        rows = by_year.get(year, [])
        if not rows:
            continue
        handed = [r for r in rows if r["answers"]["referred"]["noul"] >= 0.5]
        own = [r for r in rows if r["answers"]["referred"]["noul"] < 0.5]
        c = collections.Counter(r["answers"]["clarity"]["choice"] for r in own)
        share = lambda k: c[k] / len(own) if own else 0
        print(f"{year:<6}{len(full):>7}{len(rows):>8}{len(handed) / len(rows):>12.1%}"
              f"{share('Clear Reply'):>8.1%}{share('Ambivalent'):>8.1%}{share('Clear Non-Reply'):>11.1%}")

    tokens = sum(r["usage"]["input_tokens"] for r in res)
    cost = sum(r["usage"]["cost"] for r in res)
    print(f"\n{len(res)} judged · {tokens:,} input tokens · ${cost:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    if not args.report_only:
        run(args.n)
    report()
