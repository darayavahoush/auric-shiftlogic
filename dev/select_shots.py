import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Greedy pick of visible items whose lines cover every binding template + every decoy type,
then write src/shots.json (labelled lines = prompt DATA; the oracle itself is not shipped)."""
import json, sys, re
from templates import build_parser, VISIBLE
parse = build_parser(VISIBLE, with_idx=True)
gold = json.load(open(sys.argv[1])); K = int(sys.argv[2]) if len(sys.argv) > 2 else 10
def feats(g):
    f = set()
    for l in g["lines"]:
        p = parse(l["text"])
        if p: f.add(("T", p[2]))
        else: f.add(("D", l["decoy"]))
        if re.match(r"(It bears|Noted twice|This came up|Worth restating)", l["text"]): f.add(("W", 1))
        if re.match(r"(As far as|Speaking from|My recollection|I'm fairly|Going off)", l["text"]): f.add(("H", 1))
    return f
F = {iid: feats(g) for iid, g in gold.items()}
need = set().union(*F.values()); chosen = []; have = set()
while need - have and len(chosen) < K:
    best = max(F, key=lambda i: (len(F[i] - have), -len(gold[i]["lines"])) if i not in chosen else (-1, 0))
    if not F[best] - have: break
    chosen.append(best); have |= F[best]
print("chosen", chosen, "covered", len(have), "of", len(need), "missing", sorted(need - have))
out = {iid: {"staff": gold[iid]["staff"], "holders": gold[iid]["holders"],
             "lines": [{"idx": l["idx"], "text": l["text"], "kind": l["kind"], "args": l["args"], "decoy": l["decoy"]} for l in gold[iid]["lines"]]}
       for iid in chosen}
json.dump(out, open(sys.argv[3] if len(sys.argv) > 3 else "shots.json", "w"), indent=1)
