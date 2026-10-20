import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
#!/usr/bin/env python3
"""Generate reworded ShiftLogic items + exact keys + per-line gold labels.

  python gen_paraphrase.py --pool new     --n 50 --seed 7  --out paraphrase_new
  python gen_paraphrase.py --pool visible --n 30 --seed 11 --out paraphrase_visiblectl

Outputs in --out/: items.json, key.json (score.py format, beside items.json), gold_lines.json
Keys are computed by the repo's own 720-world semantics (src/solver.Constraint.check) from the
generator's *typed* constraints, so the key never depends on any parsing of the English.
"""
import argparse, itertools, json, os, random, sys
sys.path.insert(0, ROOT)
from src.solver import Constraint, generate_all_worlds, BLOCK_TO_IDX, BLOCKS, STATIONS
from pools import POOLS, PHRASE
from pool_blind import BLIND, BLIND_HEDGES, BLIND_WRAPPERS, BLIND_DECOY, BLIND_PHRASE, BLIND_NAMES
POOLS['blind'] = dict(bind=BLIND, decoy=BLIND_DECOY, hedges=BLIND_HEDGES, wrappers=BLIND_WRAPPERS, names=BLIND_NAMES)
PHRASE.update(BLIND_PHRASE)
from pool_d import D_BIND, D_HEDGES, D_WRAPPERS, D_DECOY, D_PHRASE, D_NAMES
POOLS['d'] = dict(bind=D_BIND, decoy=D_DECOY, hedges=D_HEDGES, wrappers=D_WRAPPERS, names=D_NAMES)
PHRASE.update({k: v for k, v in D_PHRASE.items() if v})
from templates import NAMES as VIS_NAMES

NEW_NAMES = ["Farah","Kiran","Omar","Zoe","Hugo","Bianca","Tobias","Leila"]
NAME_POOL = list(dict.fromkeys(VIS_NAMES + NEW_NAMES))

def lower_first(s, names):
    first = s.split(" ", 1)[0].strip(",'’")
    first = first.split("'")[0]
    return s if first in names else s[0].lower() + s[1:]

def fill(tpl, ph):
    out = tpl
    for k, v in ph.items(): out = out.replace("{%s}" % k, v)
    return out

def render_line(tpl, ph, names, hedge="", wrapper=""):
    s = fill(tpl, ph)
    s = s[0].upper() + s[1:]
    if hedge: s = hedge + lower_first(s, names)
    if wrapper: s = wrapper + s
    return s

def names_list(ns):
    return ", ".join(ns[:-1]) + " and " + ns[-1] if len(ns) > 1 else ns[0]

# -------- typed constraint space --------
def check(c, w): return c.check(w.blocks, w.stations, w.station_blocks)

def all_true_constraints(staff, holders, truth):
    """Every typed constraint (kind,args) that holds in world `truth` (and is expressible)."""
    out = []
    tb, ts = truth.blocks, truth.stations
    for p in staff:
        for bi, b in enumerate(BLOCKS):
            out.append(("BLOCK_EQ" if tb[p] == bi else "BLOCK_NEQ", (p, b)))
    for p in holders:
        for s in STATIONS:
            out.append(("STATION_EQ" if ts[p] == s else "STATION_NEQ", (p, s)))
    for a, b in itertools.permutations(staff, 2):
        if tb[a] < tb[b]: out.append(("ORDER_LT", (a, b))); out.append(("ORDER_GT", (b, a)))
        if tb[a] == tb[b] + 1: out.append(("IMMEDIATE_AFTER", (a, b))); out.append(("IMMEDIATE_BEFORE", (b, a)))
    for m, a, b in itertools.permutations(staff, 3):
        if a < b and (tb[a] < tb[m] < tb[b] or tb[b] < tb[m] < tb[a]): out.append(("BETWEEN", (m, a, b)))
    sb = truth.station_blocks
    for s in STATIONS:
        for p in staff:
            if sb[s] < tb[p]:
                out.append(("ORDER_STATION_PERSON", (s, p))); out.append(("ORDER_PERSON_STATION", (p, s)))
    return out

def false_constraints(staff, holders, truth):
    """Typed constraints that are FALSE in `truth` (candidates for an injected contradiction)."""
    out = []
    tb, ts = truth.blocks, truth.stations
    for p in staff:
        for bi, b in enumerate(BLOCKS):
            out.append(("BLOCK_NEQ" if tb[p] == bi else "BLOCK_EQ", (p, b)))
    for p in holders:
        for s in STATIONS:
            out.append(("STATION_NEQ" if ts[p] == s else "STATION_EQ", (p, s)))
    for a, b in itertools.permutations(staff, 2):
        if tb[a] > tb[b]: out.append(("ORDER_LT", (a, b)))
        if tb[a] < tb[b]: out.append(("ORDER_GT", (a, b)))
        if tb[a] != tb[b] + 1: out.append(("IMMEDIATE_AFTER", (a, b)))
    for m, a, b in itertools.permutations(staff, 3):
        if a < b and not (tb[a] < tb[m] < tb[b] or tb[b] < tb[m] < tb[a]): out.append(("BETWEEN", (m, a, b)))
    return out

def mk(kind, args):
    a = list(args)
    if kind in ("BLOCK_EQ", "BLOCK_NEQ"): a[1] = BLOCK_TO_IDX[a[1]]
    return Constraint(kind, tuple(a), "")

def mask(c, worlds):
    m = 0
    for i, w in enumerate(worlds):
        if check(c, w): m |= 1 << i
    return m

def popcount(x): return bin(x).count("1")

def minimal_unsat_sets(ms, full, max_size=6):
    n = len(ms); res = []
    for r in range(1, max_size + 1):
        for combo in itertools.combinations(range(n), r):
            cs = set(combo)
            if any(set(c) <= cs for c in res): continue
            x = full
            for i in combo: x &= ms[i]
            if x == 0: res.append(combo)
    return res

# -------- rendering a typed constraint through a pool --------
def render_constraint(rng, pool, kind, args, names, hedge_p=0.35, force_tpl=None, wrapper=False):
    cands = [t for t in pool["bind"] if t[0] == kind]
    kind_, tpl, order = force_tpl or rng.choice(cands)
    ph = dict(zip(order, args))
    hedge = rng.choice(pool["hedges"]) if rng.random() < hedge_p else ""
    wr = rng.choice(pool["wrappers"]) if wrapper else ""
    return render_line(tpl, ph, names, hedge, wr), (kind_, tpl, order)

def render_decoy(rng, pool, dtype, staff, holders, names):
    tpl = rng.choice(pool["decoy"][dtype])
    ph = {}
    ph["A"] = rng.choice(staff)
    ph["B"] = rng.choice([s for s in staff if s != ph["A"]])
    ph["T"] = rng.choice(BLOCKS)
    ph["S"] = rng.choice(STATIONS)
    k = rng.choice([2, 3, 4, 5])
    ph["L"] = names_list(rng.sample(staff, k))
    hedge = rng.choice(pool["hedges"]) if rng.random() < 0.25 else ""
    wr = ""
    return render_line(tpl, ph, names, hedge, wr), tpl

# -------- item generation --------
def build_header(rng, staff, holders, bay):
    return (f"Shift notes, Bay {bay}. 5 staff on the rota: {', '.join(staff)}. Blocks run 07:00, 09:00, 11:00, 13:00, 15:00, "
            f"one person per block, and each person works exactly one block. There are 3 stations, one person on each: "
            f"intake, calibration, packing. The people on a station are {', '.join(holders)}; the rest are on no station.")

def gen_item(rng, case, pool_name, worlds_cache):
    pool = POOLS[pool_name]
    for attempt in range(400):
        staff = rng.sample(pool.get('names', NAME_POOL), 5)
        holders = rng.sample(staff, 3)
        key_ = (tuple(staff), tuple(holders))
        if key_ not in worlds_cache: worlds_cache[key_] = generate_all_worlds(staff, holders)
        worlds = worlds_cache[key_]; full = (1 << len(worlds)) - 1
        truth = rng.choice(worlds)
        trues = all_true_constraints(staff, holders, truth)
        # weighted shuffle: kind mix follows the visible set (BETWEEN ~25% of binding lines)
        W = {"BETWEEN": 25, "ORDER_STATION_PERSON": 13, "STATION_NEQ": 11, "BLOCK_NEQ": 8, "BLOCK_EQ": 7, "STATION_EQ": 7,
             "IMMEDIATE_BEFORE": 5.5, "ORDER_GT": 4, "IMMEDIATE_AFTER": 3.7, "ORDER_LT": 3, "ORDER_PERSON_STATION": 2.5}
        # each kind's total weight is shared out over its instances so the *kind* mix, not the instance count, is matched
        cnt = {}
        for k_, _ in trues: cnt[k_] = cnt.get(k_, 0) + 1
        trues.sort(key=lambda c: -(rng.random() ** (cnt[c[0]] / W[c[0]])))
        chosen, cur = [], full
        target_hi = 1 if case == "unique" else 4
        target_lo = 1 if case == "unique" else 2
        masks = {}
        for kind, args in trues:
            if popcount(cur) <= target_hi and popcount(cur) >= target_lo: break
            m = masks.get((kind, args))
            if m is None: m = masks[(kind, args)] = mask(mk(kind, args), worlds)
            nxt = cur & m
            if nxt == cur: continue                     # redundant
            if case == "ambiguous" and popcount(nxt) < 2: continue   # would collapse to unique
            chosen.append((kind, args)); cur = nxt
            if len(chosen) > 13: break
        if not (target_lo <= popcount(cur) <= target_hi): continue
        if case != "inconsistent" and not (6 <= len(chosen) <= 12): continue
        inj = None
        if case == "inconsistent":
            # inject one false statement into a (near-)determined set -> every minimal conflict must have >= 3 members
            fals = false_constraints(staff, holders, truth); rng.shuffle(fals)
            ok = False
            for fk, fa in fals:
                allc = chosen + [(fk, fa)]
                ms = [mask(mk(*c), worlds) for c in allc]
                x = full
                for m in ms: x &= m
                if x != 0: continue
                sets = minimal_unsat_sets(ms, full, max_size=6)
                if sets and min(len(s) for s in sets) >= 3 and len(sets) <= 8:
                    inj = (fk, fa); chosen = allc; ok = True; break
            if not ok or not (7 <= len(chosen) <= 12): continue
        # ---- render lines ----
        names = set(NAME_POOL) | set(pool.get('names', []))
        lines, gold = [], []
        used_tpl = {}
        for kind, args in chosen:
            ln, tpl = render_constraint(rng, pool, kind, args, names)
            lines.append(ln); gold.append(dict(kind=kind, args=list(args), decoy=None, phrase=PHRASE.get(tpl[1])))
            used_tpl[len(lines) - 1] = tpl
        # restatements (~25%): same constraint, different template, wrapper prefix
        for i in range(len(chosen)):
            if rng.random() < 0.25:
                kind, args = chosen[i]
                alts = [t for t in pool["bind"] if t[0] == kind and t[1] != used_tpl[i][1]]
                if not alts: continue
                ln, _ = render_constraint(rng, pool, kind, args, names, force_tpl=rng.choice(alts), wrapper=True)
                lines.append(ln); gold.append(dict(kind=kind, args=list(args), decoy=None, restated=True, phrase=PHRASE.get(_[1])))
        # decoys: ~10, mix of 5 types
        n_dec = rng.choice([9, 10, 10, 11, 12])
        mix = ["CHAT"] * (n_dec - 5) + ["PAST", "WISH", "OPEN", "UNMET"] + [rng.choice(["PAST", "WISH", "OPEN", "UNMET"])]
        mix = mix[:n_dec]
        for d in mix:
            ln, _ = render_decoy(rng, pool, d, staff, holders, names)
            lines.append(ln); gold.append(dict(kind=None, args=None, decoy=d, phrase=PHRASE.get(_)))
        total = len(lines)
        if not (16 <= total <= 23): continue
        order = list(range(total)); rng.shuffle(order)
        lines = [lines[i] for i in order]; gold = [gold[i] for i in order]
        if len(set(lines)) != len(lines): continue
        # ---- key ----
        bind_idx = [i for i, g in enumerate(gold) if g["kind"]]
        cons = [mk(gold[i]["kind"], gold[i]["args"]) for i in bind_idx]
        ms = [mask(c, worlds) for c in cons]
        x = full
        for m in ms: x &= m
        n = popcount(x)
        if case == "unique" and n != 1: continue
        if case == "ambiguous" and not (2 <= n <= 4): continue
        if case == "inconsistent" and n != 0: continue
        key = {"case": case}
        if case == "inconsistent":
            sets = minimal_unsat_sets(ms, full, max_size=6)
            if not sets or min(len(s) for s in sets) < 3 or len(sets) > 12: continue
            key["assignments"] = []
            key["conflict_line_sets"] = [[lines[bind_idx[j]] for j in s] for s in sets]
        else:
            key["assignments"] = [w.format_assignment() for i, w in enumerate(worlds) if x >> i & 1]
            key["conflict_line_sets"] = []
        text = build_header(rng, staff, holders, rng.choice([2, 3, 4, 5, 6, 7])) + "\n\n" + "\n".join(lines)
        return dict(staff=staff, holders=holders, text=text, key=key, gold=gold, lines=lines)
    raise RuntimeError("could not generate " + case)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=list(POOLS), default="new")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="paraphrase_new")
    ap.add_argument("--prefix", default="P")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    cases = ["unique", "ambiguous", "inconsistent"]
    plan = [cases[i % 3] for i in range(a.n)]; rng.shuffle(plan)
    cache, items, key, gold = {}, [], {}, {}
    for i, case in enumerate(plan):
        it = gen_item(rng, case, a.pool, cache)
        iid = f"{a.prefix}-{i:03d}"
        items.append({"id": iid, "text": it["text"], "n_staff": 5, "n_stations": 3})
        key[iid] = it["key"]
        gold[iid] = {"staff": it["staff"], "holders": it["holders"],
                     "lines": [{"idx": j + 1, "text": l, **g} for j, (l, g) in enumerate(zip(it["lines"], it["gold"]))]}
    os.makedirs(a.out, exist_ok=True)
    json.dump(items, open(f"{a.out}/items.json", "w"), indent=1)
    json.dump(key, open(f"{a.out}/key.json", "w"), indent=1)
    json.dump(gold, open(f"{a.out}/gold_lines.json", "w"), indent=1)
    from collections import Counter
    print(a.out, Counter(k["case"] for k in key.values()))

if __name__ == "__main__":
    main()
