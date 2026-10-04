"""Pick example answers for the site, with their text, from the last 12 months of judged questions.

Only answers Jev was at least 90% sure about, and short enough to read on a page, so the
examples show the categories clearly. Writes data/examples.json. Runs once locally (it needs
the raw downloads for the text); the daily job adds its own recent examples.

Usage:  python examples.py
"""
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
PER_KIND = {"Clear Reply": 4, "Ambivalent": 4, "Clear Non-Reply": 3, "handoff": 3}


def read_jsonl(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def clean_question(q):
    """Drop the question number, the PQ reference and the stock closing phrase."""
    q = re.sub(r"^\s*\d+\.\s*", "", q)
    q = re.sub(r"\s*\[\d+/\d+\]\s*$", "", q)
    return re.sub(r";?\s*and if (he|she) will make a statement on the matter\.?$", ".", q).strip()


def link(pq_id):
    date, num = pq_id.split("/pq_")
    return f"https://www.oireachtas.ie/en/debates/question/{date}/{num}/"


def kind(j):
    return "handoff" if j["referred"] >= 0.5 else j["clarity"]


def main():
    judged = {j["id"]: j for j in read_jsonl(DATA / "judgments.jsonl") if j["date"] >= "2025-10"}
    text = {}
    for p in sorted(DATA.glob("pqs_202[56]-*.jsonl")):
        for r in read_jsonl(p):
            if r["id"] in judged:
                text[r["id"]] = r

    pools = {k: [] for k in PER_KIND}
    for i, j in judged.items():
        r = text.get(i)
        if not r or r["group_size"] > 1 or not (40 <= len(r["reply"].split()) <= 160):
            continue
        if max(j["clarity_p"].values()) < 0.9 and kind(j) != "handoff":
            continue
        if kind(j) == "handoff" and j["referred"] < 0.95:
            continue
        pools[kind(j)].append((j, r))

    rng = random.Random(3)
    examples = []
    for k, n in PER_KIND.items():
        for j, r in rng.sample(pools[k], min(n, len(pools[k]))):
            examples.append({
                "kind": k, "id": j["id"], "date": j["date"], "to": j["to"],
                "question": clean_question(r["question"]), "reply": r["reply"],
                "clarity": j["clarity"], "clarity_p": j["clarity_p"],
                "technique": j["technique"], "referred": j["referred"], "link": link(j["id"]),
            })
    (DATA / "examples.json").write_text(json.dumps(examples, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print({k: len(v) for k, v in pools.items()}, "->", len(examples), "examples")


if __name__ == "__main__":
    main()
