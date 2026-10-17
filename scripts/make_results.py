#!/usr/bin/env python3
"""Build ui/results.json for the dashboard's Scorecard tab.

Usage:
    python3 scripts/make_results.py answers_1x.json [answers_3x.json answers_10x.json]

Budget labels (1x/3x/10x) are read from each file name. Every number comes straight
from score.py; nothing is typed in by hand.
"""
import json, os, re, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from score import score, find_items  # noqa: E402

KEY = os.path.join(ROOT, "visible_key.json")


def main(paths):
    if not paths:
        sys.exit(__doc__)
    key = json.load(open(KEY))
    items = find_items(KEY, None)
    runs = {}
    for p in paths:
        m = re.search(r"(\d+)x", os.path.basename(p))
        if not m:
            sys.exit(f"Cannot tell the budget from file name: {p}")
        runs[f"{m.group(1)}x"] = score(key, json.load(open(p)), items)
    out = {"generated": datetime.date.today().isoformat(), "runs": runs}
    dest = os.path.join(ROOT, "ui", "results.json")
    json.dump(out, open(dest, "w"), indent=2)
    print(f"Wrote {dest}")
    for b, r in runs.items():
        print(f"  {b}: macro exact match {r['macro_exact_match']:.1%}")


if __name__ == "__main__":
    main(sys.argv[1:])
