"""Daily update: fetch the last three weeks of written Dáil questions, judge the new answers, rebuild the site data.

Runs in GitHub Actions once a day. Replies are often published days after the question date,
so each run looks back WINDOW_DAYS and judges anything answered since that isn't judged yet.
Live coverage starts at LIVE_START; earlier months come from the one-off samples.

Every answered question in the window is judged (not sampled): ~250-400 a day, about 1 cent.
A per-run budget cap stops it from ever spending more than MAX_RUN_COST.

Writes: data/judgments.jsonl (appended), data/daily_asked.json, data/recent.jsonl, site/data.json
Usage:  python daily.py [--today YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import build_site
from compact import compact, read_jsonl
from examples import clean_question, link
from fetch_pqs import fetch_rows
from jev import api_key, judge_pq

HERE = Path(__file__).parent
DATA = HERE / "data"
LIVE_START = "2026-10-01"
WINDOW_DAYS = 21
RECENT_DAYS = 45
MAX_RUN_COST = 0.25  # dollars


def main(today):
    start = max(LIVE_START, (dt.date.fromisoformat(today) - dt.timedelta(days=WINDOW_DAYS)).isoformat())
    rows = fetch_rows(start, today)

    asked_path = DATA / "daily_asked.json"
    asked = json.loads(asked_path.read_text()) if asked_path.exists() else {}
    for day in {r["date"] for r in rows}:
        asked[day] = sum(r["date"] == day for r in rows)
    asked_path.write_text(json.dumps(dict(sorted(asked.items())), indent=1))

    done = {j["id"] for j in read_jsonl(DATA / "judgments.jsonl")}
    todo = [r for r in rows if r["reply"] and r["id"] not in done]
    print(f"{len(rows)} questions since {start}, {len(todo)} newly answered to judge")

    key = api_key()
    spent, lock = [0.0], threading.Lock()

    def judge(row):
        with lock:
            if spent[0] >= MAX_RUN_COST:
                return None
        try:
            out = judge_pq(row, key)
        except Exception as e:  # picked up again on the next run
            print(f"failed {row['id']}: {e}")
            return None
        with lock:
            spent[0] += out["usage"]["cost"]
        return row, out

    new = []
    with ThreadPoolExecutor(8) as pool:
        for res in pool.map(judge, todo):
            if res:
                row, out = res
                new.append((row, compact(row, out, "daily")))

    with (DATA / "judgments.jsonl").open("a", encoding="utf-8") as f:
        for _, j in sorted(new, key=lambda x: (x[1]["date"], x[1]["id"])):
            f.write(json.dumps(j, ensure_ascii=False) + "\n")

    # Text for the "latest answers" feed: only recent questions, replies trimmed.
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=RECENT_DAYS)).isoformat()
    recent = [r for r in read_jsonl(DATA / "recent.jsonl") if r["date"] >= cutoff]
    recent += [{**j, "question": clean_question(row["question"]), "reply": row["reply"][:1500],
                "link": link(row["id"])} for row, j in new]
    recent.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    with (DATA / "recent.jsonl").open("w", encoding="utf-8") as f:
        for r in recent:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"judged {len(new)} for ${spent[0]:.4f}")
    build_site.main()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=dt.date.today().isoformat())
    main(ap.parse_args().today)
