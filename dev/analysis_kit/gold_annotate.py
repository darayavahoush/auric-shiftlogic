#!/usr/bin/env python3
"""DEV-ONLY oracle annotator (NOT part of the answering pipeline).

Maps the visible set's closed pool of sentence templates to typed constraints so we can
(1) verify an annotation reproduces visible_key.json exactly, (2) measure Granite per-line accuracy,
(3) run error-injection simulations. It is deliberately template-bound; never import it from `run`.
"""
import re, json, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.solver import Constraint, solve, BLOCK_TO_IDX

P = r"(?P<{}>Ayesha|Daniel|Ingrid|Lukas|Meera|Nadia|Priya|Rohan|Samuel|Tomas)"
S = r"(?P<s>intake|calibration|packing)"
B = r"(?P<blk>\d\d:00)"
def p(n): return P.format(n)

# (regex, builder) — builder gets match dict -> (kind, args)
R = []
def add(rx, kind, order):  # order: tuple of group names forming args; 'b' converted to idx
    R.append((re.compile(rx, re.I), kind, order))

# ---- BLOCK_EQ
add(rf"{p('p')} is the one who opens up at {B}", "BLOCK_EQ", ("p","blk"))
add(rf"{p('p')} takes {B}, as things stand", "BLOCK_EQ", ("p","blk"))
add(rf"{B} is when {p('p')} is scheduled", "BLOCK_EQ", ("p","blk"))
add(rf"the {B} block is {p('p')}'s", "BLOCK_EQ", ("p","blk"))
add(rf"whoever drew the {B} block, it was {p('p')}", "BLOCK_EQ", ("p","blk"))
add(rf"{p('p')} is on the {B} block", "BLOCK_EQ", ("p","blk"))
# ---- BLOCK_NEQ
add(rf"{p('p')} lobbied for {B} without success", "BLOCK_NEQ", ("p","blk"))
add(rf"{p('p')} has a standing commitment that rules out the {B} block entirely", "BLOCK_NEQ", ("p","blk"))
add(rf"{p('p')} put in for the {B} block and was turned down", "BLOCK_NEQ", ("p","blk"))
add(rf"{p('p')} wanted {B} and did not get it", "BLOCK_NEQ", ("p","blk"))
add(rf"{p('p')} is unavailable at {B}", "BLOCK_NEQ", ("p","blk"))
add(rf"{p('p')} is not on the {B} block", "BLOCK_NEQ", ("p","blk"))
add(rf"you will not find {p('p')} on the {B} block", "BLOCK_NEQ", ("p","blk"))
add(rf"{B} is the one block {p('p')} is definitely not on", "BLOCK_NEQ", ("p","blk"))
add(rf"the {B} block is not {p('p')}'s", "BLOCK_NEQ", ("p","blk"))
add(rf"{p('p')} asked to move to the {B} block; the request was declined", "BLOCK_NEQ", ("p","blk"))
# ---- STATION_EQ
add(rf"{S} is {p('p')}'s station", "STATION_EQ", ("p","s"))
add(rf"{S} is covered by {p('p')}", "STATION_EQ", ("p","s"))
add(rf"the {S} station is down to {p('p')}", "STATION_EQ", ("p","s"))
add(rf"{p('p')} has {S} this week", "STATION_EQ", ("p","s"))
add(rf"{p('p')} is assigned to {S}", "STATION_EQ", ("p","s"))
add(rf"{p('p')} is on {S}", "STATION_EQ", ("p","s"))
# ---- STATION_NEQ
add(rf"{S} is covered by someone other than {p('p')}", "STATION_NEQ", ("p","s"))
add(rf"{p('p')} has not been put on {S}", "STATION_NEQ", ("p","s"))
add(rf"you can rule {p('p')} out for {S}", "STATION_NEQ", ("p","s"))
add(rf"{p('p')} is not on {S}", "STATION_NEQ", ("p","s"))
add(rf"{p('p')} is not assigned to {S}", "STATION_NEQ", ("p","s"))
add(rf"{S} is not {p('p')}'s station", "STATION_NEQ", ("p","s"))
# ---- station holder earlier than person  -> ORDER_STATION_PERSON(s, p)
add(rf"the {S} station is covered earlier in the day than {p('p')}'s block", "ORDER_STATION_PERSON", ("s","p"))
add(rf"whoever is on {S} works earlier in the day than {p('p')}", "ORDER_STATION_PERSON", ("s","p"))
add(rf"the person on {S} precedes {p('p')}", "ORDER_STATION_PERSON", ("s","p"))
add(rf"{S} is covered before {p('p')} comes on", "ORDER_STATION_PERSON", ("s","p"))
add(rf"whoever has {S} is done before {p('p')} starts", "ORDER_STATION_PERSON", ("s","p"))
add(rf"{p('p')} is on later than whoever has {S}", "ORDER_STATION_PERSON", ("s","p"))
# ---- person order: ORDER_LT(earlier, later)
add(rf"{p('a')} comes later in the day than {p('b')}", "ORDER_LT", ("b","a"))
add(rf"{p('a')} takes over from {p('b')} later in the day", "ORDER_LT", ("b","a"))
add(rf"{p('a')}'s block falls somewhere earlier than {p('b')}'s", "ORDER_LT", ("a","b"))
add(rf"{p('a')} works earlier in the day than {p('b')}", "ORDER_LT", ("a","b"))
add(rf"{p('a')} is done before {p('b')} starts", "ORDER_LT", ("a","b"))
add(rf"by the time {p('a')} starts, {p('b')} has already been on", "ORDER_LT", ("b","a"))
# ---- immediate
add(rf"{p('a')} is on the block directly after {p('b')}", "IMMEDIATE_AFTER", ("a","b"))
add(rf"{p('a')} is on the block immediately before {p('b')}", "IMMEDIATE_BEFORE", ("a","b"))
add(rf"{p('a')} then {p('b')}, back to back", "IMMEDIATE_BEFORE", ("a","b"))
add(rf"{p('a')} hands straight over to {p('b')}", "IMMEDIATE_BEFORE", ("a","b"))
add(rf"{p('a')} relieves {p('b')} directly, with no block in between", "IMMEDIATE_AFTER", ("a","b"))
add(rf"there is no block between {p('a')}'s and {p('b')}'s, in that order", "IMMEDIATE_BEFORE", ("a","b"))
# ---- between (mid, x, y)
add(rf"put {p('m')} between {p('x')} and {p('y')}, though not necessarily next to either", "BETWEEN", ("m","x","y"))
add(rf"whichever way round {p('x')} and {p('y')} are, {p('m')} is between them", "BETWEEN", ("m","x","y"))
add(rf"{p('m')} sits between {p('x')} and {p('y')} on the rota", "BETWEEN", ("m","x","y"))
add(rf"{p('m')} works at some point between {p('x')} and {p('y')}, not necessarily adjacent to either", "BETWEEN", ("m","x","y"))
add(rf"{p('m')} is on after one of {p('x')} and {p('y')} and before the other", "BETWEEN", ("m","x","y"))
add(rf"{p('m')}'s block falls between {p('x')}'s and {p('y')}'s, in one order or the other", "BETWEEN", ("m","x","y"))

def annotate_line(line):
    hits = []
    for rx, kind, order in R:
        m = rx.search(line)
        if m:
            g = m.groupdict()
            args = []
            for k in order:
                v = g[k]
                args.append(BLOCK_TO_IDX[v] if k == "blk" else (v.lower() if k == "s" else v))
            # ORDER_STATION_PERSON args are (station, person) already
            hits.append((m.end() - m.start(), kind, tuple(args)))
    if not hits: return None
    hits.sort(reverse=True)           # longest match wins (e.g. 'is not on S' over 'is on S')
    return hits[0][1], hits[0][2]

def header(text):
    h = text.split('\n')[0]
    staff = [x.strip() for x in re.search(r'rota: ([^.]*)\.', h).group(1).split(',')]
    holders = [x.strip() for x in re.search(r'on a station are ([^;]*);', h).group(1).split(',')]
    return staff, holders

def gold_for_item(it):
    staff, holders = header(it['text'])
    lines = [l.strip() for l in it['text'].split('\n')[1:] if l.strip()]
    gold = []
    for i, l in enumerate(lines):
        a = annotate_line(l)
        if a: gold.append({"line_no": i + 1, "line": l, "kind": a[0], "args": list(a[1])})
    return staff, holders, lines, gold

def to_constraints(gold):
    return [Constraint(g["kind"], tuple(g["args"]), g["line"]) for g in gold]

if __name__ == "__main__":
    items = json.load(open('/home/claude/auric-shiftlogic/items.json'))
    out, answers = {}, {}
    for it in items:
        staff, holders, lines, gold = gold_for_item(it)
        r = solve(staff, holders, to_constraints(gold))
        out[it['id']] = {"staff": staff, "holders": holders, "n_lines": len(lines), "gold": gold}
        ent = {"case": r["case"]}
        if r["case"] == "unique": ent["assignment"] = r["assignment"]
        elif r["case"] == "ambiguous": ent["assignments"] = r["assignments"]
        elif r["case"] == "inconsistent": ent["conflicts"] = r["conflicts"]
        else: ent = {"case": "ambiguous", "assignments": []}
        answers[it['id']] = ent
    json.dump(out, open('gold_constraints.json', 'w'), indent=1)
    json.dump(answers, open('gold_answers.json', 'w'), indent=1)
    print("items", len(out), "avg binding lines/item", sum(len(v['gold']) for v in out.values())/len(out))
