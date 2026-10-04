#!/bin/sh
# One month (March) per year, 2012 to 2026: a cross-year sample without downloading everything.
cd "$(dirname "$0")"
for y in $(seq 2012 2026); do
  [ -f "data/pqs_$y-03-01_$y-03-31.jsonl" ] || python fetch_pqs.py "$y-03-01" "$y-03-31"
done
