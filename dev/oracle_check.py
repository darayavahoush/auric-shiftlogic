import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
import json, sys, itertools
sys.path.insert(0, ROOT)
from src.solver import Constraint, generate_all_worlds, BLOCK_TO_IDX
from templates import *
import score as S

def masks_for(staff, holders, cons, worlds):
    ms = []
    for c in cons:
        m = 0
        for i, w in enumerate(worlds):
            if c.check(w.blocks, w.stations, w.station_blocks): m |= (1 << i)
        ms.append(m)
    return ms

def to_constraint(kind, args, line):
    a = list(args)
    if kind in ("BLOCK_EQ","BLOCK_NEQ"): a[1] = BLOCK_TO_IDX[a[1]]
    return Constraint(kind, tuple(a), line)

def all_minimal_unsat(ms, full):
    n = len(ms); allm = full
    def sat(sub):
        x = full
        for i in sub: x &= ms[i]
        return x != 0
    res = []
    for r in range(1, n + 1):
        for combo in itertools.combinations(range(n), r):
            if any(set(c) <= set(combo) for c in res): continue
            if not sat(combo): res.append(combo)
        if r >= 6 and not res: pass
        if r > 8: break
    return res

def solve_lines(staff, holders, lines, parse):
    worlds = generate_all_worlds(staff, holders)
    full = (1 << len(worlds)) - 1
    cons = []
    for l in lines:
        p = parse(l)
        if p: cons.append(to_constraint(p[0], p[1], l))
    ms = masks_for(staff, holders, cons, worlds)
    x = full
    for m in ms: x &= m
    n = bin(x).count("1")
    return worlds, cons, ms, x, n

if __name__ == "__main__":
    import re
    items = json.load(open(ROOT + "/items.json")); key = json.load(open(ROOT + "/visible_key.json"))
    for label, table in [("core only", VISIBLE), ("core + unmet-request as NEQ", VISIBLE + UNMET)]:
        parse = build_parser(table)
        ok = 0; bad = []
        for it in items:
            head, body = it["text"].split("\n\n", 1)
            staff = re.search(r"rota: ([^.]*)\.", head).group(1).split(", ")
            holders = re.search(r"station are ([^;]*);", head).group(1).split(", ")
            lines = body.split("\n")
            worlds, cons, ms, x, n = solve_lines(staff, holders, lines, parse)
            k = key[it["id"]]
            got = "unique" if n == 1 else "ambiguous" if 2 <= n <= 4 else "inconsistent" if n == 0 else "under"
            good = got == k["case"]
            if good and got != "inconsistent":
                sel = [w for i, w in enumerate(worlds) if x >> i & 1]
                got_as = sorted(json.dumps(w.format_assignment(), sort_keys=True) for w in sel)
                want_as = sorted(json.dumps(a, sort_keys=True) for a in k["assignments"])
                good = got_as == want_as
            if good and got == "inconsistent":
                mus = all_minimal_unsat(ms, (1 << len(worlds)) - 1)
                got_sets = sorted(sorted(set(cons[i].source_line for i in c)) for c in mus)
                want_sets = sorted(sorted(set(s)) for s in k["conflict_line_sets"])
                # compare modulo hedge/wrapper normalisation
                norm = lambda L: sorted(S.squash_stmt(s) for s in L)
                good = sorted(map(norm, got_sets)) == sorted(map(norm, want_sets))
            ok += good
            if not good: bad.append((it["id"], k["case"], got, n))
        print(label, ok, "/ 60", bad[:12])
