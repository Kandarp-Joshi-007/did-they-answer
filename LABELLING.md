# Labelling rules

Labels use the QEvasion taxonomy (Thomas et al., EMNLP 2024 Findings): three clarity
levels, nine techniques. Every label is judged for the one question shown, even when the
reply covers several grouped questions.

Rules added for Dáil written answers, applied to every label in `data/labels.jsonl`:

| Situation | Label |
|---|---|
| Hands the question to another body with nothing else ("the HSE will reply directly") | Declining to answer, `referred = true` |
| Answers and also refers part to another body | Label what was answered, `referred = true` |
| "Not held", "not collected", "not possible to quantify" | Claims ignorance |
| "Could not be collated in time, will write to the Deputy" | Declining to answer, note starts `deferred:` |
| Vague timing ("shortly", "in due course") for a "when" question | General |
| Only points to a website or an earlier reply instead of giving the figures | Deflection |
| Answer is "none" or "no plans" | Explicit — a direct answer, even if unwelcome |
| Answer sits in a table missing from the text | Explicit, note says `table not in text` |
| "Details supplied" hides what was asked, so the reply can't be judged | Best guess, `unsure = true` |

The first 400 labels (sample drawn from March 2023, seed 42) were made by Claude
(`labeller: claude-opus-5-5`), not by a person. A human should relabel a subset to
measure agreement before these are reported as ground truth.
