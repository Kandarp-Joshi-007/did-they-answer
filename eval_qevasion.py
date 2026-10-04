"""Run Jev on the QEvasion test set (308 US presidential interview Q&A pairs) and score it.

Each row asks about one specific sub-question inside a longer interview exchange, so the
state carries the full exchange plus the sub-question to judge. Raw answers are cached in
data/qevasion/jev_test.jsonl, so re-running only calls Jev for rows not yet judged.

Usage:  python eval_qevasion.py
"""
import collections
import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev import QUESTIONS, api_key, decide

HERE = Path(__file__).parent
TEST = HERE / "data" / "qevasion" / "test.jsonl"
OUT = HERE / "data" / "qevasion" / "jev_test.jsonl"
CLARITY = ["Clear Reply", "Ambivalent", "Clear Non-Reply"]

# Same questions as for the Dáil, reworded for interviews; the HSE hand-off question doesn't apply.
INTERVIEW_QUESTIONS = copy.deepcopy({k: QUESTIONS[k] for k in ("clarity", "technique")})
INTERVIEW_QUESTIONS["clarity"]["instructions"] = (
    "Does the interviewee's answer address the specific sub-question?")
INTERVIEW_QUESTIONS["technique"]["instructions"] = (
    "Which best describes how the answer handles the specific sub-question?")


def judge(row, key):
    state = {
        "interview_question": row["interview_question"],
        "interview_answer": row["interview_answer"],
        "sub_question_to_judge": row["question"].strip(),
    }
    out = decide(state, INTERVIEW_QUESTIONS, key)
    return {"index": row["index"], "answers": out["answers"], "usage": out["usage"],
            "latency_ms": out["latency_ms"], "model": out["model"]}


def run():
    key = api_key()
    rows = [json.loads(l) for l in TEST.open(encoding="utf-8")]
    done = {json.loads(l)["index"] for l in OUT.open(encoding="utf-8")} if OUT.exists() else set()
    todo = [r for r in rows if r["index"] not in done]
    print(f"{len(todo)} rows to judge ({len(done)} cached)")
    with ThreadPoolExecutor(4) as pool, OUT.open("a", encoding="utf-8") as f:
        for res in pool.map(lambda r: judge(r, key), todo):
            f.write(json.dumps(res, ensure_ascii=False) + "\n")


def macro_f1(gold, pred, labels):
    f1s = []
    for c in labels:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s)


def report():
    gold = {r["index"]: r for r in map(json.loads, TEST.open(encoding="utf-8"))}
    res = [json.loads(l) for l in OUT.open(encoding="utf-8")]
    g = [gold[r["index"]]["clarity_label"] for r in res]
    p = [r["answers"]["clarity"]["choice"] for r in res]
    conf = [max(r["answers"]["clarity"]["probabilities"].values()) for r in res]
    n = len(res)

    print(f"\nQEvasion test, n={n}")
    print(f"clarity accuracy  {sum(a == b for a, b in zip(g, p)) / n:.3f}")
    print(f"clarity macro-F1  {macro_f1(g, p, CLARITY):.3f}")
    print(f"majority baseline {max(collections.Counter(g).values()) / n:.3f}  (always 'Ambivalent')")

    print("\nconfusion (rows = gold, cols = Jev)")
    print(" " * 16 + "".join(f"{c:>16}" for c in CLARITY))
    for a in CLARITY:
        print(f"{a:>16}" + "".join(f"{sum(x == a and y == b for x, y in zip(g, p)):>16}" for b in CLARITY))

    # Technique: counted right if it matches any of the three annotators.
    def norm(t):
        return "Partial" if t.startswith("Partial") else t
    hit = sum(r["answers"]["technique"]["choice"] in
              {norm(gold[r["index"]][f"annotator{k}"]) for k in (1, 2, 3)} for r in res)
    print(f"\ntechnique matches any annotator  {hit / n:.3f}")

    # Calibration of the clarity answer: does stated probability match how often it's right?
    print("\ncalibration (clarity, top probability)")
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
        print(f"{lo:>5.1f}–{min(hi, 1):.1f}{len(idx):>6}{mp:>9.2f}{acc:>10.2f}")
    print(f"expected calibration error {ece:.3f}")

    tokens = sum(r["usage"]["input_tokens"] for r in res)
    cost = sum(r["usage"]["cost"] for r in res)
    lat = sorted(r["latency_ms"] for r in res)
    print(f"\ninput tokens {tokens:,} · cost ${cost:.4f} · median latency {lat[n // 2]} ms")


if __name__ == "__main__":
    run()
    report()
