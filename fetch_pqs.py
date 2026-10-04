"""Download written Dáil questions and the minister's replies from the Oireachtas open data.

The API lists questions but not the reply text. Each question points at a debate-section
XML (Akoma Ntoso) that holds one or more questions and the reply that answers them all,
so we fetch each section once and attach its reply to every question in it.

Usage:  python fetch_pqs.py 2023-03-01 2023-03-31
Output: data/pqs_<start>_<end>.jsonl, one question per line.
"""
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.oireachtas.ie/v1/questions"
NS = {"a": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0/CSD13"}
HERE = Path(__file__).parent
CACHE = HERE / "data" / "xml_cache"
PAGE = 1000


def get(url, tries=4):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)


def list_questions(start, end):
    rows, skip = [], 0
    while True:
        url = f"{API}?date_start={start}&date_end={end}&qtype=written&limit={PAGE}&skip={skip}"
        page = json.loads(get(url))
        rows += [r["question"] for r in page["results"]]
        if len(page["results"]) < PAGE:
            return rows
        skip += PAGE


def text_of(el):
    return " ".join("".join(el.itertext()).split())


def parse_section(xml_bytes):
    """Return {pq eId: question text}, the reply text and any editor's note for one section."""
    root = ET.fromstring(xml_bytes)
    section = root.find(".//a:debateSection", NS)
    questions = {q.get("eId"): text_of(q) for q in section.findall("a:question", NS)}
    reply = "\n".join(
        text_of(p) for s in section.findall("a:speech", NS) for p in s.findall("a:p", NS)
    )
    note = " ".join(text_of(n) for n in section.findall("a:summary", NS))
    return questions, reply, note


def fetch_section(uri):
    name = uri.split("/akn/ie/debateRecord/")[1].replace("/", "_").replace("@", "")
    path = CACHE / name
    if path.exists():
        return uri, parse_section(path.read_bytes())
    data = get(uri)
    parsed = parse_section(data)
    if parsed[1]:  # cache only once answered, so "awaiting reply" sections are re-checked
        path.write_bytes(data)
    return uri, parsed


def fetch_rows(start, end):
    """All written questions in [start, end], each with its reply text (empty if not yet answered)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    qs = list_questions(start, end)
    uris = sorted({q["debateSection"]["formats"]["xml"]["uri"] for q in qs})
    print(f"{len(qs)} questions in {len(uris)} sections", file=sys.stderr)

    with ThreadPoolExecutor(8) as pool:
        sections = dict(pool.map(fetch_section, uris))

    rows = []
    for q in qs:
        questions, reply, note = sections[q["debateSection"]["formats"]["xml"]["uri"]]
        pq_id = q["uri"].rsplit("/", 1)[1]
        rows.append({
            "id": q["uri"].split("/question/")[1],
            "date": q["date"],
            "asked_by": q["by"]["showAs"],
            "to": q["to"]["showAs"],
            "topic": q["debateSection"]["showAs"],
            "question": questions.get(pq_id, q["showAs"].strip()),
            "reply": reply,  # empty while e.g. note == "Awaiting reply from Department."
            "group_size": len(questions),
            "note": note,
        })
    return rows


def main(start, end):
    rows = fetch_rows(start, end)
    out = HERE / "data" / f"pqs_{start}_{end}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    missing = sum(not r["reply"] for r in rows)
    print(f"wrote {out} ({missing} with no reply text)", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:3])
