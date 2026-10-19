import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
import json, sys, os
sys.path.insert(0, ROOT)
from src.solver import solve, Constraint, BLOCK_TO_IDX
import score as S
from templates import build_parser, VISIBLE

def gold_answers(d):
    gold = json.load(open(f"{d}/gold_lines.json")); ans = {}
    for iid, g in gold.items():
        cons = []
        for l in g["lines"]:
            if l["kind"]:
                a = list(l["args"])
                if l["kind"] in ("BLOCK_EQ", "BLOCK_NEQ"): a[1] = BLOCK_TO_IDX[a[1]]
                cons.append(Constraint(l["kind"], tuple(a), l["text"]))
        r = solve(g["staff"], g["holders"], cons)
        e = {"case": r["case"] if r["case"] != "under_constrained" else "unique"}
        if r["case"] == "unique": e["assignment"] = r["assignment"]
        elif r["case"] == "ambiguous": e["assignments"] = r["assignments"]
        elif r["case"] == "inconsistent": e["conflicts"] = r["conflicts"]
        ans[iid] = e
    return ans

d = sys.argv[1]
key = json.load(open(f"{d}/key.json")); items = json.load(open(f"{d}/items.json"))
res = S.score(key, gold_answers(d), items)
print(d, "macro", res["macro_exact_match"], "per_case", res["per_case_rate"])
if len(sys.argv) > 2 and sys.argv[2] == "roundtrip":
    parse = build_parser(VISIBLE); gold = json.load(open(f"{d}/gold_lines.json")); bad = 0; n = 0
    for iid, g in gold.items():
        for l in g["lines"]:
            p = parse(l["text"]); n += 1
            want = (l["kind"], tuple(l["args"])) if l["kind"] else None
            if p != want:
                bad += 1
                if bad < 8: print("MISMATCH", l["text"], p, want)
    print("roundtrip mismatches", bad, "of", n)
