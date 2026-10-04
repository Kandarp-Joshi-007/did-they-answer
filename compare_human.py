"""Compare the blind human check (data/labels_human.jsonl) with Claude's labels and with Jev.

The question this answers: are Claude's 400 labels a fair stand-in for a person's? If the
human agrees with Claude about as well as with Jev, the Irish accuracy figures need a caveat;
if human-Claude agreement is high, they can be reported against Claude's labels.

Usage:  python compare_human.py
"""
import collections
import json
from pathlib import Path

HERE = Path(__file__).parent
CLARITY = ["Clear Reply", "Ambivalent", "Clear Non-Reply"]


def latest(path):
    out = {}
    if path.exists():
        for line in path.open(encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                out[row["id"]] = row
    return out


def kappa(a, b):
    """Cohen's kappa: agreement corrected for what two raters would hit by chance."""
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    expected = sum(ca[c] * cb[c] for c in set(a) | set(b)) / n ** 2
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def compare(name, a, b):
    agree = sum(x == y for x, y in zip(a, b)) / len(a)
    print(f"{name:<22} agreement {agree:.3f}   kappa {kappa(a, b):.3f}")


def main():
    human = latest(HERE / "data" / "labels_human.jsonl")
    claude = latest(HERE / "data" / "labels.jsonl")
    jev = {i: r["answers"]["clarity"]["choice"] for i, r in latest(HERE / "data" / "jev_labelled.jsonl").items()}
    ids = [i for i in human if i in claude and i in jev]
    if not ids:
        raise SystemExit("no human labels yet: run python label_server.py --check")

    h = [human[i]["clarity"] for i in ids]
    c = [claude[i]["clarity"] for i in ids]
    j = [jev[i] for i in ids]
    print(f"clarity, n={len(ids)} human-labelled questions\n")
    compare("human vs Claude", h, c)
    compare("human vs Jev", h, j)
    compare("Claude vs Jev", c, j)

    print("\nconfusion (rows = human, cols = Claude)")
    print(" " * 16 + "".join(f"{x:>16}" for x in CLARITY))
    for a in CLARITY:
        print(f"{a:>16}" + "".join(f"{sum(x == a and y == b for x, y in zip(h, c)):>16}" for b in CLARITY))

    t = sum(human[i]["technique"] == claude[i]["technique"] for i in ids) / len(ids)
    print(f"\ntechnique, human vs Claude exact agreement {t:.3f}")

    print("\ndisagreements (human / Claude / Jev):")
    for i, a, b, x in zip(ids, h, c, j):
        if a != b:
            print(f"  {i:<22} {a:<16} {b:<16} {x}")


if __name__ == "__main__":
    main()
