"""Run Jev on the labelled Dáil sample and compare it with the hand labels.

Raw Jev answers are cached in data/jev_labelled.jsonl, so re-running only calls Jev for
questions not yet judged. Scores are reported for all labelled questions and again with
hand-offs to another body (the HSE etc.) removed, since those are easy and inflate accuracy.

Usage:  python eval_irish.py
"""
import collections
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eval_qevasion import CLARITY, macro_f1
from jev import api_key, judge_pq

HERE = Path(__file__).parent
SAMPLE = HERE / "data" / "label_sample.jsonl"
LABELS = HERE / "data" / "labels.jsonl"
OUT = HERE / "data" / "jev_labelled.jsonl"


def read_jsonl(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def run(rows):
    key = api_key()
    done = {r["id"] for r in read_jsonl(OUT)}
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(todo)} questions to judge ({len(done)} cached)")

    def judge(row):
        out = judge_pq(row, key)
        return {"id": row["id"], "answers": out["answers"], "usage": out["usage"],
                "latency_ms": out["latency_ms"], "model": out["model"]}

    with ThreadPoolExecutor(4) as pool, OUT.open("a", encoding="utf-8") as f:
        for res in pool.map(judge, todo):
            f.write(json.dumps(res, ensure_ascii=False) + "\n")


def score(name, pairs):
    n = len(pairs)
    g = [lab["clarity"] for lab, _ in pairs]
    p = [jev["answers"]["clarity"]["choice"] for _, jev in pairs]
    conf = [max(jev["answers"]["clarity"]["probabilities"].values()) for _, jev in pairs]
    tech = sum(lab["technique"] == jev["answers"]["technique"]["choice"] for lab, jev in pairs)

    print(f"\n== {name}, n={n}")
    print(f"clarity accuracy  {sum(a == b for a, b in zip(g, p)) / n:.3f}")
    print(f"clarity macro-F1  {macro_f1(g, p, CLARITY):.3f}")
    print(f"majority baseline {max(collections.Counter(g).values()) / n:.3f}")
    print(f"technique exact   {tech / n:.3f}")
    print(" " * 16 + "".join(f"{c:>16}" for c in CLARITY))
    for a in CLARITY:
        print(f"{a:>16}" + "".join(f"{sum(x == a and y == b for x, y in zip(g, p)):>16}" for b in CLARITY))

    print(f"{'bin':>11}{'n':>6}{'mean p':>9}{'accuracy':>10}")
    ece = 0.0
    for lo in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
        hi = {0.0: 0.5, 0.9: 1.01}.get(lo, lo + 0.1)
        idx = [i for i, c in enumerate(conf) if lo <= c < hi]
        if not idx:
            continue
        mp = sum(conf[i] for i in idx) / len(idx)
        acc = sum(g[i] == p[i] for i in idx) / len(idx)
        ece += len(idx) / n * abs(mp - acc)
        print(f"{lo:>5.1f}-{min(hi, 1):.1f}{len(idx):>6}{mp:>9.2f}{acc:>10.2f}")
    print(f"expected calibration error {ece:.3f}")


def report():
    labels = {l["id"]: l for l in read_jsonl(LABELS)}  # last label per id wins
    jev = {r["id"]: r for r in read_jsonl(OUT)}
    pairs = [(labels[i], jev[i]) for i in labels if i in jev]

    score("all labelled", pairs)
    score("excluding hand-offs to another body", [x for x in pairs if not x[0]["referred"]])

    ref = [(lab["referred"], j["answers"]["referred"]["noul"] >= 0.5) for lab, j in pairs]
    tp = sum(a and b for a, b in ref)
    print(f"\nhand-off detection: {tp}/{sum(a for a, _ in ref)} found, "
          f"{sum(b and not a for a, b in ref)} false alarms")

    res = list(jev.values())
    print(f"input tokens {sum(r['usage']['input_tokens'] for r in res):,} · "
          f"cost ${sum(r['usage']['cost'] for r in res):.4f} · "
          f"median latency {sorted(r['latency_ms'] for r in res)[len(res) // 2]} ms")


if __name__ == "__main__":
    labelled = {l["id"] for l in read_jsonl(LABELS)}
    run([r for r in read_jsonl(SAMPLE) if r["id"] in labelled])
    report()
