import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Template tables: VISIBLE (phrasing seen in items.json) used only by the dev oracle,
and NEW (disjoint wording) used to generate the paraphrase test set."""
import re

NAMES = ["Ayesha","Daniel","Ingrid","Lukas","Meera","Nadia","Priya","Rohan","Samuel","Tomas","Farah","Kiran","Omar","Zoe","Hugo","Bianca","Tobias","Leila"]
STATIONS = ["intake","calibration","packing"]

# (kind, template, arg placeholders in constraint-arg order)
VISIBLE = [
 ("BLOCK_EQ","{A} is the one who opens up at {T}.",("A","T")),
 ("BLOCK_EQ","Whoever drew the {T} block, it was {A}.",("A","T")),
 ("BLOCK_EQ","{A} takes {T}, as things stand.",("A","T")),
 ("BLOCK_EQ","The {T} block is {A}'s.",("A","T")),
 ("BLOCK_EQ","{T} is when {A} is scheduled.",("A","T")),
 ("BLOCK_EQ","{A} is on the {T} block.",("A","T")),
 ("BLOCK_NEQ","{A} is unavailable at {T}.",("A","T")),
 ("BLOCK_NEQ","{A} has a standing commitment that rules out the {T} block entirely.",("A","T")),
 ("BLOCK_NEQ","{T} is the one block {A} is definitely not on.",("A","T")),
 ("BLOCK_NEQ","You will not find {A} on the {T} block.",("A","T")),
 ("BLOCK_NEQ","The {T} block is not {A}'s.",("A","T")),
 ("BLOCK_NEQ","{A} is not on the {T} block.",("A","T")),
 ("STATION_EQ","{A} is on {S}.",("A","S")),
 ("STATION_EQ","{A} is assigned to {S}.",("A","S")),
 ("STATION_EQ","{S} is covered by {A}.",("A","S")),
 ("STATION_EQ","The {S} station is down to {A}.",("A","S")),
 ("STATION_EQ","{S} is {A}'s station.",("A","S")),
 ("STATION_EQ","{A} has {S} this week.",("A","S")),
 ("STATION_NEQ","{A} is not on {S}.",("A","S")),
 ("STATION_NEQ","{A} is not assigned to {S}.",("A","S")),
 ("STATION_NEQ","{A} has not been put on {S}.",("A","S")),
 ("STATION_NEQ","You can rule {A} out for {S}.",("A","S")),
 ("STATION_NEQ","{S} is covered by someone other than {A}.",("A","S")),
 ("STATION_NEQ","{S} is not {A}'s station.",("A","S")),
 ("ORDER_LT","{A} works earlier in the day than {B}.",("A","B")),
 ("ORDER_LT","{A} is done before {B} starts.",("A","B")),
 ("ORDER_LT","{A}'s block falls somewhere earlier than {B}'s.",("A","B")),
 ("ORDER_GT","{A} comes later in the day than {B}.",("A","B")),
 ("ORDER_GT","{A} takes over from {B} later in the day.",("A","B")),
 ("ORDER_GT","By the time {A} starts, {B} has already been on.",("A","B")),
 ("IMMEDIATE_AFTER","{A} is on the block directly after {B}.",("A","B")),
 ("IMMEDIATE_AFTER","{A} relieves {B} directly, with no block in between.",("A","B")),
 ("IMMEDIATE_BEFORE","{A} then {B}, back to back.",("A","B")),
 ("IMMEDIATE_BEFORE","{A} hands straight over to {B}.",("A","B")),
 ("IMMEDIATE_BEFORE","{A} is on the block immediately before {B}.",("A","B")),
 ("IMMEDIATE_BEFORE","There is no block between {A} and {B}, in that order.",("A","B")),
 ("IMMEDIATE_BEFORE","There is no block between {A}'s and {B}'s, in that order.",("A","B")),
 ("BETWEEN","Whichever way round {A} and {B} are, {M} is between them.",("M","A","B")),
 ("BETWEEN","{M} works at some point between {A} and {B}, not necessarily adjacent to either.",("M","A","B")),
 ("BETWEEN","{M} is on after one of {A} and {B} and before the other.",("M","A","B")),
 ("BETWEEN","{M} sits between {A} and {B} on the rota.",("M","A","B")),
 ("BETWEEN","Put {M} between {A} and {B}, though not necessarily next to either.",("M","A","B")),
 ("BETWEEN","{M}'s block falls between {A}'s and {B}'s, in one order or the other.",("M","A","B")),
 ("ORDER_STATION_PERSON","The {S} station is covered earlier in the day than {A}'s block.",("S","A")),
 ("ORDER_STATION_PERSON","Whoever has {S} is done before {A} starts.",("S","A")),
 ("ORDER_STATION_PERSON","The person on {S} precedes {A}.",("S","A")),
 ("ORDER_STATION_PERSON","Whoever is on {S} works earlier in the day than {A}.",("S","A")),
 ("ORDER_STATION_PERSON","{S} is covered before {A} comes on.",("S","A")),
 ("ORDER_PERSON_STATION","{A} is on later than whoever has {S}.",("A","S")),
]
# Lines that LOOK binding but may be decoys ("unmet request"). Tested empirically against the key.
UNMET = [
 ("BLOCK_NEQ","{A} lobbied for {T} without success.",("A","T")),
 ("BLOCK_NEQ","{A} put in for the {T} block and was turned down.",("A","T")),
 ("BLOCK_NEQ","{A} wanted {T} and did not get it.",("A","T")),
 ("BLOCK_NEQ","{A} asked to move to the {T} block; the request was declined.",("A","T")),
]
HEDGES = ["As far as I know, ","Speaking from memory, ","My recollection is that ","I'm fairly sure ","Going off the roster, "]
WRAPPERS = ["It bears repeating: ","Noted twice in the handover: ","This came up more than once, so: ",
            "Worth restating, since it came up twice in handover: "]

def _rx(tpl):
    s = re.escape(tpl)
    s = s.replace(r"\{A\}", r"(?P<A>%s)" % "|".join(NAMES)).replace(r"\{B\}", r"(?P<B>%s)" % "|".join(NAMES))
    s = s.replace(r"\{M\}", r"(?P<M>%s)" % "|".join(NAMES))
    s = s.replace(r"\{T\}", r"(?P<T>\d\d:00)").replace(r"\{S\}", r"(?P<S>%s)" % "|".join(STATIONS))
    s = s.replace("\\'", "'")
    return re.compile("^" + s + "$", re.I)

def strip_wrappers(line):
    l = line.strip()
    for w in WRAPPERS:
        if l.startswith(w): l = l[len(w):]
    for h in HEDGES:
        if l.lower().startswith(h.lower()): l = l[len(h):]
    return l

def build_parser(table, with_idx=False):
    comp = [(k, _rx(t), order) for k, t, order in table]
    def parse(line):
        l = strip_wrappers(line)
        # a wrapper may precede a hedge, and a hedge may precede nothing else: try both orders
        l2 = l
        for h in HEDGES:
            if l2.lower().startswith(h.lower()): l2 = l2[len(h):]
        for ti, (k, rx, order) in enumerate(comp):
            m = rx.match(l2)
            if m:
                args = []
                for ph in order:
                    v = m.group(ph)
                    if ph in ("A","B","M"): v = next(n for n in NAMES if n.lower()==v.lower())
                    elif ph == "S": v = v.lower()
                    args.append(v)
                return (k, tuple(args), ti) if with_idx else (k, tuple(args))
        return None
    return parse
