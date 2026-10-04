"""Local page for hand-labelling whether a reply answers its question.

Draws a fixed random sample of answered questions once, then serves a labelling page.
Each label is appended to data/labels.jsonl as you save it (the last label for an id wins),
so you can stop and come back at any time.

Usage:  python label_server.py data/pqs_2023-03-01_2023-03-31.jsonl [--n 400]
        python label_server.py --check     # blind human check of 50 already-labelled items
Then open http://127.0.0.1:8765

--check draws 50 items from the labelled sample, balanced across the three clarity levels,
and saves to data/labels_human.jsonl, so the existing labels are never shown.
"""
import argparse
import json
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
SAMPLE = HERE / "data" / "label_sample.jsonl"
LABELS = HERE / "data" / "labels.jsonl"
PAGE = HERE / "label.html"
CHECK_SAMPLE = HERE / "data" / "check_sample.jsonl"
CHECK_LABELS = HERE / "data" / "labels_human.jsonl"
serve_sample, serve_labels, labeller = SAMPLE, LABELS, "claude-opus-5-5"


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def make_check_sample(n=50, seed=7):
    """Balanced across clarity levels; hand-offs capped because they are trivially easy."""
    labels = {l["id"]: l for l in read_jsonl(LABELS)}
    rows = [r for r in read_jsonl(SAMPLE) if r["id"] in labels]
    rng = random.Random(seed)
    picked = []
    for clarity in ("Clear Reply", "Ambivalent", "Clear Non-Reply"):
        pool = [r for r in rows if labels[r["id"]]["clarity"] == clarity]
        handoffs = [r for r in pool if labels[r["id"]]["referred"]]
        others = [r for r in pool if not labels[r["id"]]["referred"]]
        k = n // 3 + (clarity == "Clear Reply") * (n % 3)
        take = rng.sample(handoffs, min(4, len(handoffs)))
        picked += take + rng.sample(others, min(k - len(take), len(others)))
    rng.shuffle(picked)
    CHECK_SAMPLE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in picked),
                            encoding="utf-8")
    return picked


def make_sample(source, n, seed=42):
    rows = [r for r in read_jsonl(Path(source)) if r["reply"]]
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    SAMPLE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sample), encoding="utf-8")
    return sample


class Handler(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self.send(PAGE.read_text(encoding="utf-8"), "text/html")
        elif self.path == "/api/items":
            labels = {l["id"]: l for l in read_jsonl(serve_labels)}
            self.send(json.dumps({"items": read_jsonl(serve_sample), "labels": labels}, ensure_ascii=False))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/label":
            return self.send_error(404)
        label = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        label.setdefault("labeller", labeller)
        with serve_labels.open("a", encoding="utf-8") as f:
            f.write(json.dumps(label, ensure_ascii=False) + "\n")
        self.send('{"ok": true}')

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", help="pqs_*.jsonl to sample from (only needed the first time)")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--check", action="store_true", help="blind human check of 50 labelled items")
    args = ap.parse_args()

    global serve_sample, serve_labels, labeller
    if args.check:
        serve_sample, serve_labels, labeller = CHECK_SAMPLE, CHECK_LABELS, "human"
        if CHECK_SAMPLE.exists():
            print(f"using existing check sample ({len(read_jsonl(CHECK_SAMPLE))} items)")
        else:
            print(f"drew {len(make_check_sample())} items into {CHECK_SAMPLE}")
    elif SAMPLE.exists():
        print(f"using existing sample {SAMPLE} ({len(read_jsonl(SAMPLE))} items)")
    elif args.source:
        print(f"drew {len(make_sample(args.source, args.n))} items into {SAMPLE}")
    else:
        raise SystemExit("no sample yet: pass a pqs_*.jsonl file")

    print(f"labelling at http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
