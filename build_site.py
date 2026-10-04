"""Build site/data.json from the judged questions and the evaluation files.

Every number on the page comes from here, computed from the data files, so nothing on the
site is typed in by hand. Shares of clear / partly / non-reply are always of the minister's
own replies: hand-offs to another body ("the HSE will reply directly") are counted apart.

Usage:  python build_site.py
"""
import collections
import datetime as dt
import json
import math
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
SITE = HERE / "site"
CLARITY = ["Clear Reply", "Ambivalent", "Clear Non-Reply"]
# Department labels as the Oireachtas data gives them, made readable. Remits shift with each
# government, so these are kept short rather than claiming an exact official title.
DEPT = {
    "Social": "Social Protection", "Climate": "Climate & Environment", "Rural": "Rural & Community",
    "Culture": "Culture & Media", "Children": "Children & Equality", "Foreign": "Foreign Affairs",
    "Public Expenditure": "Public Expenditure", "Enterprise": "Enterprise & Employment",
    "Further and Higher Education": "Further & Higher Education",
}


def read_jsonl(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def latest(path):
    return {r["id"]: r for r in read_jsonl(path)}


def wilson(k, n, z=1.96):
    """95% interval for a share, which behaves at small n and near 0 or 1."""
    if not n:
        return [0, 0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 4), round(centre + half, 4)]


def shares(rows):
    """Hand-off rate over all rows; clarity mix over the minister's own replies."""
    own = [r for r in rows if r["referred"] < 0.5]
    c = collections.Counter(r["clarity"] for r in own)
    n = len(own)
    return {
        "n": len(rows), "own": n,
        "handoff": round((len(rows) - n) / len(rows), 4) if rows else None,
        "clear": round(c["Clear Reply"] / n, 4) if n else None,
        "partly": round(c["Ambivalent"] / n, 4) if n else None,
        "non": round(c["Clear Non-Reply"] / n, 4) if n else None,
        "clear_ci": wilson(c["Clear Reply"], n),
        "grouped": round(sum(r["group_size"] > 1 for r in own) / n, 4) if n else None,
    }


# Department labels change with every government ("Minister for Health" in 2012, "Health" later;
# remits move between departments), so long-run comparisons match on a keyword instead.
DEPT_KEYS = ["Health", "Transport", "Children", "Education", "Justice", "Housing", "Environment",
             "Climate", "Social", "Agriculture", "Finance", "Foreign", "Enterprise", "Jobs", "Public",
             "Arts", "Culture", "Communications", "Defence", "Rural", "Further", "Taoiseach", "Tourism"]


def dept_key(to):
    return next((k for k in DEPT_KEYS if k.lower() in to.lower()), "Other")


def handoff_split(before, after):
    """Split the change in hand-off rate into department mix and change within departments."""
    def table(rows):
        n = collections.Counter(dept_key(r["to"]) for r in rows)
        h = collections.Counter(dept_key(r["to"]) for r in rows if r["referred"] >= 0.5)
        return {k: (n[k] / len(rows), h[k] / n[k]) for k in n}
    a, b = table(before), table(after)
    mix = within = 0.0
    for k in set(a) | set(b):
        sa, ra = a.get(k, (0, None))
        sb, rb = b.get(k, (0, None))
        ra = rb if ra is None else ra
        rb = ra if rb is None else rb
        mix += (sb - sa) * ra
        within += sb * (rb - ra)
    top = sorted((k for k in a if k in b), key=lambda k: -b[k][0] * (b[k][1] - a[k][1]))[:3]
    return {"mix": round(mix, 4), "within": round(within, 4),
            "departments": [{"name": k, "before": round(a[k][1], 4), "after": round(b[k][1], 4),
                             "share_before": round(a[k][0], 4), "share_after": round(b[k][0], 4)} for k in top]}


def mix(rows):
    """Proportions for the 1,000-dot graphic: hand-offs of all, the rest split by clarity."""
    s = shares(rows)
    return {k: s[k] for k in ("handoff", "clear", "partly", "non")}


def ece(gold, pred, conf):
    bins = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    total = 0.0
    for lo, hi in bins:
        idx = [i for i, c in enumerate(conf) if lo <= c < hi]
        if idx:
            acc = sum(gold[i] == pred[i] for i in idx) / len(idx)
            total += len(idx) / len(gold) * abs(sum(conf[i] for i in idx) / len(idx) - acc)
    return round(total, 3)


def kappa(a, b):
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    expected = sum(ca[c] * cb[c] for c in set(a) | set(b)) / n ** 2
    return round((observed - expected) / (1 - expected), 3)


def method():
    out = {}
    # QEvasion is CC BY-NC-ND, so its test set stays out of the repo. Locally the score is
    # computed and saved as a summary; in CI (no test set) the saved summary is read back.
    summary = DATA / "qevasion_summary.json"
    test = {r["index"]: r for r in read_jsonl(DATA / "qevasion" / "test.jsonl")}
    res = read_jsonl(DATA / "qevasion" / "jev_test.jsonl") if test else []
    if not res and summary.exists():
        out["qevasion"] = json.loads(summary.read_text())
    if res:
        g = [test[r["index"]]["clarity_label"] for r in res]
        p = [r["answers"]["clarity"]["choice"] for r in res]
        conf = [max(r["answers"]["clarity"]["probabilities"].values()) for r in res]
        out["qevasion"] = {"n": len(res), "accuracy": round(sum(a == b for a, b in zip(g, p)) / len(g), 3),
                           "baseline": round(max(collections.Counter(g).values()) / len(g), 3),
                           "ece": ece(g, p, conf)}
        summary.write_text(json.dumps(out["qevasion"]))

    claude = latest(DATA / "labels.jsonl")
    jev = latest(DATA / "jev_labelled.jsonl")
    ids = [i for i in claude if i in jev]
    if ids:
        g = [claude[i]["clarity"] for i in ids]
        p = [jev[i]["answers"]["clarity"]["choice"] for i in ids]
        conf = [max(jev[i]["answers"]["clarity"]["probabilities"].values()) for i in ids]
        out["irish"] = {"n": len(ids), "accuracy": round(sum(a == b for a, b in zip(g, p)) / len(g), 3),
                        "ece": ece(g, p, conf),
                        "handoffs_found": sum(claude[i]["referred"] and jev[i]["answers"]["referred"]["noul"] >= 0.5 for i in ids),
                        "handoffs": sum(claude[i]["referred"] for i in ids)}

    human = latest(DATA / "labels_human.jsonl")
    ids = [i for i in human if i in claude and i in jev and not (human[i]["referred"] and claude[i]["referred"])]
    if ids:
        h = [human[i]["clarity"] for i in ids]
        c = [claude[i]["clarity"] for i in ids]
        j = [jev[i]["answers"]["clarity"]["choice"] for i in ids]
        agree = lambda a, b: round(sum(x == y for x, y in zip(a, b)) / len(a), 3)
        out["human"] = {"n": len(human), "n_compared": len(ids),
                        "human_claude": agree(h, c), "human_claude_kappa": kappa(h, c),
                        "human_jev": agree(h, j), "human_jev_kappa": kappa(h, j)}
    return out


def main():
    judged = read_jsonl(DATA / "judgments.jsonl")
    # Full-month counts for the downloaded history; live months are summed from daily counts.
    history = json.loads((DATA / "monthly_asked.json").read_text())
    asked = dict(history)
    daily = DATA / "daily_asked.json"
    for day, n in (json.loads(daily.read_text()) if daily.exists() else {}).items():
        if day[:7] not in history:
            asked[day[:7]] = asked.get(day[:7], 0) + n

    by_month = collections.defaultdict(list)
    for j in judged:
        by_month[j["date"][:7]].append(j)

    # Long view: the March sample of every year (same month, so years compare like for like).
    yearly = []
    for year in sorted({j["date"][:4] for j in judged}):
        rows = [j for j in by_month.get(f"{year}-03", []) if j["source"] == "march-sample"]
        if rows:
            yearly.append({"year": int(year), "asked": asked.get(f"{year}-03"), **shares(rows)})

    # Monthly view from January 2024: samples, then every question once live coverage starts.
    this_month = dt.date.today().isoformat()[:7]
    monthly = []
    for month in sorted(m for m in set(asked) | set(by_month) if m >= "2024-01"):
        rows = by_month.get(month, [])
        monthly.append({"month": month, "asked": asked.get(month) or None,
                        "partial": month == this_month, **(shares(rows) if rows else {"n": 0})})

    full = [m for m in monthly if m["n"] and not m["partial"]]
    last12 = full[-12:]
    rows12 = [j for m in last12 for j in by_month[m["month"]]]
    rows24 = [j for j in judged if "2024-01" <= j["date"] < "2024-12"]
    sitting = lambda ms: [m["asked"] for m in ms if m.get("asked")]
    months24 = [m for m in monthly if m["month"].startswith("2024")]
    early = [j for j in judged if j["date"][:4] in ("2012", "2013")]
    headline = {
        "period": f"{last12[0]['month']} to {last12[-1]['month']}" if last12 else None,
        "asked_per_month_2024": round(sum(sitting(months24)) / len(sitting(months24))),
        "asked_per_month_recent": round(sum(sitting(last12)) / len(sitting(last12))),
        "clear_2024": shares(rows24)["clear"], "clear_recent": shares(rows12)["clear"],
        "handoff_2012_13": shares(early)["handoff"], "handoff_recent": shares(rows12)["handoff"],
        "single_clear_2024": shares([j for j in rows24 if j["group_size"] == 1])["clear"],
        "single_clear_recent": shares([j for j in rows12 if j["group_size"] == 1])["clear"],
        "grouped_2024": shares(rows24)["grouped"], "grouped_recent": shares(rows12)["grouped"],
        "handoff_split": handoff_split(early, rows12),
        "mix_2024": mix(rows24), "mix_recent": mix(rows12),
    }

    depts = collections.defaultdict(list)
    for j in rows12:
        depts[j["to"]].append(j)
    departments = sorted(({"name": DEPT.get(k, k), **shares(v)} for k, v in depts.items() if len(v) >= 100),
                         key=lambda d: -d["n"])

    recent = read_jsonl(DATA / "recent.jsonl")
    week = []
    if recent:
        newest = max(r["date"] for r in recent)
        cut = (dt.date.fromisoformat(newest) - dt.timedelta(days=6)).isoformat()
        week = [r for r in recent if r["date"] >= cut]

    data = {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "headline": headline, "yearly": yearly, "monthly": monthly, "departments": departments,
        "week": {**shares(week), "from": min(r["date"] for r in week), "to": max(r["date"] for r in week),
                 "departments": [[DEPT.get(k, k), n] for k, n in collections.Counter(r["to"] for r in week).most_common()]}
                if week else None,
        "latest": [{**r, "dept": DEPT.get(r["to"], r["to"])} for r in recent[:12]],
        "examples": [{**e, "dept": DEPT.get(e["to"], e["to"])}
                     for e in json.loads((DATA / "examples.json").read_text(encoding="utf-8"))],
        "method": method(),
        "totals": {"judged": len(judged), "tokens": sum(j["tokens"] for j in judged),
                   "cost": round(sum(j["tokens"] for j in judged) * 0.042 / 1e6, 2)},
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"site/data.json: {len(judged)} judged, {len(yearly)} years, {len(monthly)} months, "
          f"{len(departments)} departments, {len(recent)} recent")


if __name__ == "__main__":
    main()
