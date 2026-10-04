"""Judge a random sample of written Dáil questions from every month, with a hard spending cap.

Samples up to N answered questions per downloaded month (same sampling and seed as
run_years.py, so the March samples it already judged are reused, not paid for twice).
Results go to data/jev_months.jsonl. The run stops starting new calls once this run's
spend reaches --budget dollars.

Usage:  python run_months.py [--from 2024-01] [--n 1000] [--budget 2.50] [--report-only]
"""
import argparse
import collections
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev import api_key, judge_pq
from run_years import read_jsonl, sample

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = DATA / "jev_months.jsonl"
EARLIER = DATA / "jev_years.jsonl"
MONTH_FILE = re.compile(r"pqs_(\d{4}-\d{2})-01_\d{4}-\d{2}-\d{2}\.jsonl")


def month_files(start):
    out = []
    for p in sorted(DATA.glob("pqs_*.jsonl")):
        m = MONTH_FILE.fullmatch(p.name)
        if m and m.group(1) >= start:
            out.append((m.group(1), p))
    return out


def judged():
    return {r["id"]: r for path in (EARLIER, OUT) for r in read_jsonl(path)}


def run(start, n, budget):
    key = api_key()
    done = judged()
    todo = [r for _, p in month_files(start) for r in sample(p, n) if r["id"] not in done]
    print(f"{len(todo)} questions to judge ({len(done)} already judged), budget ${budget:.2f}")

    spent, lock = [0.0], threading.Lock()

    def judge(row):
        with lock:
            if spent[0] >= budget:
                return {"id": row["id"], "skipped": True}
        try:
            out = judge_pq(row, key)
        except Exception as e:  # retried on the next run
            return {"id": row["id"], "error": str(e)}
        with lock:
            spent[0] += out["usage"]["cost"]
        return {"id": row["id"], "date": row["date"], "to": row["to"],
                "group_size": row["group_size"], "answers": out["answers"],
                "usage": out["usage"], "provider": out["provider"]}

    counts = collections.Counter()
    with ThreadPoolExecutor(8) as pool, OUT.open("a", encoding="utf-8") as f:
        for res in pool.map(judge, todo):
            kind = "skipped" if "skipped" in res else "failed" if "error" in res else "judged"
            counts[kind] += 1
            if kind == "judged":
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(f"this run: {dict(counts)}, spent ${spent[0]:.2f}")


def report(start):
    res = judged()
    print(f"\n{'month':<9}{'asked':>7}{'judged':>8}{'handed off':>12}{'grouped':>9}"
          f"{'clear':>8}{'partly':>8}{'non-reply':>11}   (shares of non-hand-off replies)")
    for month, p in month_files(start):
        full = {r["id"]: r for r in read_jsonl(p)}
        rows = [res[i] for i in full if i in res]
        if not rows:
            continue
        own = [r for r in rows if r["answers"]["referred"]["noul"] < 0.5]
        handed = len(rows) - len(own)
        grouped = sum(full[r["id"]]["group_size"] > 1 for r in own) / max(len(own), 1)
        c = collections.Counter(r["answers"]["clarity"]["choice"] for r in own)
        share = lambda k: c[k] / len(own) if own else 0
        print(f"{month:<9}{len(full):>7}{len(rows):>8}{handed / len(rows):>12.1%}{grouped:>9.0%}"
              f"{share('Clear Reply'):>8.1%}{share('Ambivalent'):>8.1%}{share('Clear Non-Reply'):>11.1%}")
    month_res = read_jsonl(OUT)
    print(f"\nmonthly run total: {len(month_res)} judged · "
          f"${sum(r['usage']['cost'] for r in month_res):.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2024-01")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--budget", type=float, default=2.50)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    if not args.report_only:
        run(args.start, args.n, args.budget)
    report(args.start)
