import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Rough what-if: corrupt GOLD constraints at a given per-line error rate / decoy leakage, then compare
plain solve vs solve+repair. Errors in a real model are correlated, so treat absolute numbers as indicative."""
import json, random, sys
sys.path.insert(0, ROOT); sys.path.insert(0, DEV)
from src.solver import solve, Constraint, BLOCK_TO_IDX, BLOCKS, STATIONS
from src.repair import repair
import score as S

def to_c(l):
    a = list(l["args"])
    if l["kind"] in ("BLOCK_EQ", "BLOCK_NEQ"): a[1] = BLOCK_TO_IDX[a[1]]
    return Constraint(l["kind"], tuple(a), l["text"])

FLIP = {"BLOCK_EQ": "BLOCK_NEQ", "BLOCK_NEQ": "BLOCK_EQ", "STATION_EQ": "STATION_NEQ", "STATION_NEQ": "STATION_EQ"}
def corrupt(c, rng, staff):
    r = rng.random()
    if r < 0.30: return None                                   # missed line
    if r < 0.75:                                               # flip polarity / direction
        if c.kind in FLIP: return Constraint(FLIP[c.kind], c.args, c.source_line)
        if c.kind in ("ORDER_LT", "ORDER_GT", "IMMEDIATE_BEFORE", "IMMEDIATE_AFTER"): return Constraint(c.kind, (c.args[1], c.args[0]), c.source_line)
        if c.kind == "ORDER_STATION_PERSON": return Constraint("ORDER_LT", (c.args[1], c.args[0]), c.source_line)
        if c.kind == "ORDER_PERSON_STATION": return Constraint("ORDER_LT", (c.args[0], c.args[1]), c.source_line)
        if c.kind == "BETWEEN": return Constraint("BETWEEN", (c.args[1], c.args[0], c.args[2]), c.source_line)   # wrong middle
    a = list(c.args)                                           # wrong entity
    for i, v in enumerate(a):
        if v in staff:
            a[i] = rng.choice([s for s in staff if s not in a]); break
    return Constraint(c.kind, tuple(a), c.source_line)

def leak(rng, staff, holders, text):
    r = rng.random(); p = rng.choice(staff)
    if r < 0.5: return Constraint("BLOCK_NEQ", (p, rng.randrange(5)), text)
    if r < 0.75: return Constraint("BLOCK_EQ", (p, rng.randrange(5)), text)
    return Constraint("STATION_EQ", (rng.choice(holders), rng.choice(STATIONS)), text)

def finalize(r):
    case = r["case"]
    if case == "under_constrained": return {"case": "ambiguous", "assignments": [w.format_assignment() for w in r["valid_worlds"][:4]]}
    e = {"case": case}
    if case == "unique": e["assignment"] = r["assignment"]
    elif case == "ambiguous": e["assignments"] = r["assignments"]
    else: e["conflicts"] = r["conflicts"]
    return e

def trial(d, e, dl, seed, use_repair, tie="fewest_worlds"):
    rng = random.Random(seed)
    items = json.load(open(f"{d}/items.json")); key = json.load(open(f"{d}/key.json")); gold = json.load(open(f"{d}/gold_lines.json"))
    ans = {}
    for it in items:
        g = gold[it["id"]]; cons = []
        for l in g["lines"]:
            if l["kind"]:
                c = to_c(l)
                if rng.random() < e: c = corrupt(c, rng, g["staff"])
                if c is not None: cons.append(c)
            elif rng.random() < dl:
                cons.append(leak(rng, g["staff"], g["holders"], l["text"]))
        if use_repair: cons, _ = repair(g["staff"], g["holders"], cons, tie=tie)
        ans[it["id"]] = finalize(solve(g["staff"], g["holders"], cons))
    return S.score(key, ans, items)["macro_exact_match"]

if __name__ == "__main__":
    d = sys.argv[1]; T = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for e, dl in [(0.02, 0.0), (0.05, 0.0), (0.05, 0.10), (0.07, 0.15), (0.10, 0.20)]:
        b = [trial(d, e, dl, s, False) for s in range(T)]
        out = [f"e={e:.2f} d={dl:.2f}  plain {sum(b)/T:.1%}"]
        for tie in ("fewest_worlds", "most_worlds"):
            r = [trial(d, e, dl, s, True, tie) for s in range(T)]
            out.append(f"repair[{tie}] {sum(r)/T:.1%}")
        print("  ".join(out), flush=True)
