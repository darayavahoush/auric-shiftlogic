"""
Free (zero-model-call) repair of an extraction that cannot be right.

Model slips are mostly direction/polarity flips and missed or invented lines. The solver knows when an
extraction is *impossible* (0 worlds with a conflict set smaller than 3, which the brief says never occurs;
or more than 4 worlds, which the task never produces). In those cases try the smallest typed edits
(flip polarity, swap direction, drop a line) and keep one that lands on a legal answer.

It never fires on a legal extraction (1-4 worlds, or 0 worlds whose conflict sets are all >= 3 long),
so it cannot damage a correct read.  ASSUMPTION (from the brief, visible set): true conflict sets have >= 3 statements.
"""
import itertools
from typing import Any, Dict, List, Optional, Tuple
from src.solver import Constraint, generate_all_worlds

FLIP = {"BLOCK_EQ": "BLOCK_NEQ", "BLOCK_NEQ": "BLOCK_EQ", "STATION_EQ": "STATION_NEQ", "STATION_NEQ": "STATION_EQ"}
SWAP = ("ORDER_LT", "ORDER_GT", "IMMEDIATE_BEFORE", "IMMEDIATE_AFTER")


def _variants(c: Constraint) -> List[Tuple[str, Optional[Constraint]]]:
    out: List[Tuple[str, Optional[Constraint]]] = []
    if c.kind in FLIP:
        out.append(("flip", Constraint(FLIP[c.kind], c.args, c.source_line)))
    elif c.kind in SWAP:
        out.append(("flip", Constraint(c.kind, (c.args[1], c.args[0]), c.source_line)))
    elif c.kind == "ORDER_STATION_PERSON":
        out.append(("flip", Constraint("ORDER_LT", (c.args[1], c.args[0]), c.source_line)))
    out.append(("drop", None))
    return out


class _Ctx:
    def __init__(self, staff, holders):
        self.worlds = generate_all_worlds(staff, holders)
        self.full = (1 << len(self.worlds)) - 1
        self.cache: Dict[Any, int] = {}

    def mask(self, c: Constraint) -> int:
        k = (c.kind, c.args)
        m = self.cache.get(k)
        if m is None:
            m = 0
            for i, w in enumerate(self.worlds):
                if c.check(w.blocks, w.stations, w.station_blocks):
                    m |= 1 << i
            self.cache[k] = m
        return m


def _and(ms: List[int], full: int) -> int:
    x = full
    for m in ms:
        x &= m
    return x


def _min_conflict_sets(ms: List[int], full: int, max_size: int = 6) -> List[Tuple[int, ...]]:
    res: List[Tuple[int, ...]] = []
    for r in range(1, max_size + 1):
        for combo in itertools.combinations(range(len(ms)), r):
            s = set(combo)
            if any(set(c) <= s for c in res):
                continue
            if _and([ms[i] for i in combo], full) == 0:
                res.append(combo)
    return res


def repair(staff: List[str], holders: List[str], constraints: List[Constraint],
           max_edits: int = 2, tie: str = "fewest_worlds", allow_drop_for_overconstrained: bool = True):
    """Returns (constraints_to_solve, info). info['action'] in {'none','edited','gave_up'}."""
    ctx = _Ctx(staff, holders)
    cons = list(constraints)
    ms = [ctx.mask(c) for c in cons]
    n0 = bin(_and(ms, ctx.full)).count("1")
    info: Dict[str, Any] = {"worlds_before": n0, "action": "none", "edits": []}
    if 1 <= n0 <= 4:
        return cons, info

    if n0 == 0:
        sets = _min_conflict_sets(ms, ctx.full)
        if sets and min(len(s) for s in sets) >= 3:
            return cons, info                                  # a legal "inconsistent": leave it alone
        pool = sorted({i for s in sets if len(s) < 3 for i in s}) or list(range(len(cons)))
    else:
        pool = list(range(len(cons)))                          # >4 worlds: any line might be the misread one

    def evaluate(edit_set):
        new_ms, new_cons = [], []
        for i, (c, m) in enumerate(zip(cons, ms)):
            e = edit_set.get(i)
            if e is None:
                new_cons.append(c); new_ms.append(m)
            elif e[1] is not None:
                new_cons.append(e[1]); new_ms.append(ctx.mask(e[1]))
        return new_cons, new_ms

    found: List[Tuple[int, int, Any, Any]] = []
    for k in range(1, max_edits + 1):
        for idxs in itertools.combinations(pool, k):
            opts = [_variants(cons[i]) for i in idxs]
            for choice in itertools.product(*opts):
                if n0 > 4 and not allow_drop_for_overconstrained and any(c[0] == "drop" for c in choice):
                    continue
                if n0 > 4 and any(c[0] == "drop" for c in choice):
                    continue                                   # dropping a line cannot shrink an over-wide solution set
                edit_set = dict(zip(idxs, choice))
                new_cons, new_ms = evaluate(edit_set)
                n = bin(_and(new_ms, ctx.full)).count("1")
                if 1 <= n <= 4:
                    n_drops = sum(1 for c in choice if c[0] == "drop")
                    found.append((k, n_drops, n, edit_set, new_cons))
                elif n == 0 and n0 == 0:
                    sets2 = _min_conflict_sets(new_ms, ctx.full)
                    if sets2 and min(len(s) for s in sets2) >= 3:
                        found.append((k, 9, 99, edit_set, new_cons))   # still inconsistent but now legal
        if found:
            break
    if not found:
        info["action"] = "gave_up"
        return cons, info
    if tie == "fewest_worlds":
        found.sort(key=lambda t: (t[0], t[1], t[2]))
    elif tie == "most_worlds":
        found.sort(key=lambda t: (t[0], t[1], -t[2]))
    else:
        found.sort(key=lambda t: (t[0], t[1]))
    k, nd, n, edit_set, new_cons = found[0]
    info.update(action="edited", edits=[(cons[i].kind, cons[i].args, e[0]) for i, e in edit_set.items()],
                worlds_after=n if n != 99 else 0, n_candidates=len(found))
    return new_cons, info
