"""Ask Jev whether a reply answers its question.

Calls TypeSafe directly when TYPESAFE_API_KEY is set, otherwise OpenRouter with
OPENROUTER_API_KEY. Both serve the same model (Jev 1.13). Never prints or stores the key.

Usage:  python jev.py data/label_sample.jsonl 1     # judge the first N rows, print results
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

PROVIDERS = {
    # name: (key env var, endpoint, model id)
    "typesafe": ("TYPESAFE_API_KEY", "https://api.typesafe.ai/v1/systemone", "jev-1.13.0"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/alpha/decisions", "typesafe/jev-1.13"),
}
PRICE_PER_TOKEN = 0.042 / 1_000_000  # input tokens; output is free


def api_key():
    """Return (provider, key) for the first provider whose key is set."""
    for name, (env, _, _) in PROVIDERS.items():
        if os.environ.get(env):
            return name, os.environ[env]
    raise SystemExit("set TYPESAFE_API_KEY (or OPENROUTER_API_KEY) first")

# QEvasion taxonomy (Thomas et al., EMNLP 2024 Findings), same wording as label.html.
QUESTIONS = {
    "clarity": {
        "type": "choice",
        "instructions": "Does the minister's reply answer the question that was asked?",
        "criteria": {
            "Clear Reply": "The reply gives the information the question asked for.",
            "Ambivalent": "The reply responds, but only partly, vaguely, indirectly or about something else.",
            "Clear Non-Reply": "The reply openly does not give the information asked for.",
        },
    },
    "technique": {
        "type": "choice",
        "instructions": "Which best describes how the reply handles the question?",
        "criteria": {
            "Explicit": "Gives the information asked for, directly.",
            "Implicit": "The answer is there, but has to be inferred.",
            "General": "Broad talk about the topic, not the specifics asked.",
            "Partial": "Answers only part of the question.",
            "Dodging": "Ignores the question and talks about something else.",
            "Deflection": "Shifts focus to other actors, past record or wider context.",
            "Declining to answer": "Openly will not give the information.",
            "Claims ignorance": "Says the information is not held or not known.",
            "Clarification": "Asks for more detail before answering.",
        },
    },
    "referred": {
        "type": "noul",
        "instructions": "Does the reply hand the question to another body to answer directly?",
        "criteria": {
            "true": "It says another body (for example the HSE) will reply to the Deputy directly.",
            "false": "The minister's own reply is the answer.",
        },
    },
}


def decide(state, questions, key, tries=5):
    provider, key = key
    _, endpoint, model = PROVIDERS[provider]
    body = {"model": model, "state": state, "questions": questions}
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(tries):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504, 529) or attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)
            continue
        out["latency_ms"] = round((time.perf_counter() - start) * 1000)
        out["provider"] = provider
        out["usage"].setdefault("cost", out["usage"]["input_tokens"] * PRICE_PER_TOKEN)
        return out


def judge_pq(row, key):
    return decide({"question": row["question"], "reply": row["reply"]}, QUESTIONS, key)


def main(path, n):
    key = api_key()
    rows = [json.loads(l) for l in open(path, encoding="utf-8")][:n]
    for row in rows:
        out = judge_pq(row, key)
        print(json.dumps({"id": row["id"], "answers": out["answers"], "usage": out["usage"],
                          "latency_ms": out["latency_ms"], "model": out["model"]}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1)
