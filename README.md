# Did They Answer?

TDs send Irish ministers thousands of written parliamentary questions every month. This
project has an AI decision model, [Jev](https://docs.typesafe.ai) by TypeSafe AI, read each
reply and judge one thing: did it actually answer the question? A daily job keeps it current.

**Site:** https://did-they-answer.netlify.app

## Findings (as of 4 October 2026)

From 40,600 judged replies: March of every year 2012–2026, plus every month since January 2024
(1,000 random questions per month).

- **TDs ask far more questions.** About 7,200 written questions a month over the last 12
  months, against about 4,100 a month in 2024 (+73%).
- **Fewer replies clearly answer.** Of ministers' own replies, 38.9% clearly answered the
  question over the last 12 months, against 44.6% in 2024. Replies covering several questions
  at once rose from 19% to 34%, and they answer each question less clearly. But single-question
  replies fell too, from 46.0% to 42.6%.
- **Passing questions on has nearly doubled.** 26% of questions were passed to another body
  (the HSE, the NTA and others) over the last 12 months, against 14% in March 2012–13. Health
  passes on about two thirds of its questions.

Passing a question to an agency is normal procedure, so it is counted separately and never as
dodging. The site shows departments and trends, and deliberately does not rank ministers.

## How far to trust it

| Check | Result |
|---|---|
| Agreement with a person, 40 replies labelled blind | 72.5% (Cohen's κ 0.59) |
| Agreement with 400 Irish replies labelled with written rules ([LABELLING.md](LABELLING.md)) | 81.0% |
| Those 400 labels vs the same person | 87.5% (κ 0.81) |
| Calibration error, Irish written replies | 0.03 (well calibrated) |
| Calibration error, US presidential interviews ([QEvasion](https://huggingface.co/datasets/ailsntua/QEvasion)) | 0.10 (overconfident) |
| Accuracy on QEvasion | 70.5%, against 66.9% for always guessing the most common answer |
| "Passed to another body" detected | 85 of 85 |

Good enough to measure trends across thousands of replies; not good enough to judge a single
reply on its own. The 400 rule-based labels were made with an AI assistant, which is why a
person relabelled a blind sample to check them.

## How it works

1. `fetch_pqs.py` pulls questions from the Oireachtas open data API and each reply from its
   Akoma Ntoso XML. One reply often answers several grouped questions.
2. `jev.py` sends the question and reply to Jev with three typed questions: clarity
   (clear / partly / not answered), technique (the nine-way taxonomy from Thomas et al.,
   EMNLP 2024), and whether it was passed to another body. Jev returns probabilities, not text.
3. `run_years.py` and `run_months.py` judged the historical samples; `compact.py` merged them
   into `data/judgments.jsonl`.
4. `daily.py` runs every day in GitHub Actions: it fetches the last three weeks (replies arrive
   late), judges anything newly answered, and rebuilds `site/data.json`. Netlify serves `site/`.
5. `eval_qevasion.py`, `eval_irish.py`, `label_server.py` and `compare_human.py` are the
   evaluation: benchmark, labelled sample, labelling tool, and human agreement check.

Cost: the whole history cost about $1.80 in Jev calls (about 1,050 input tokens per reply at
$0.042 per million). The daily job costs about a cent a day, with a per-run cap.

## Running it

Python 3.12, standard library only. Set `TYPESAFE_API_KEY` (or `OPENROUTER_API_KEY`).

```
python daily.py          # fetch, judge, rebuild site/data.json
python build_site.py     # rebuild site/data.json only
```

## Data and licences

Contains Oireachtas data licensed under the
[Oireachtas (Open Data) PSI Licence](https://www.oireachtas.ie/en/open-data/license/).
© Houses of the Oireachtas. The QEvasion dataset is CC BY-NC-ND 4.0 and is not redistributed
here; only Jev's answers and summary scores are. Independent project, not endorsed by the Houses
of the Oireachtas or TypeSafe AI.
