#!/usr/bin/env python3
"""Offline checks for decompiler_v3 (no API): gold -> slot form -> parse -> same semantics; end-to-end through
pipeline_v2 with a fake client that answers with the gold slot forms (must score 100%), and with a fake that
swaps first/second on every ORDER line (must NOT score 100%, proves the direction slot is what carries the answer)."""
import json, os, sys, random
os.environ["SHIFT_DEC"] = "v3"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
import src.decompiler_v3 as V
from src.pipeline_v2 import run_item
from eval_lines import sem
import score as S

def gold_sets():
    out = []
    for d in sys.argv[1:] or ["paraphrase_new", "paraphrase_fresh", "paraphrase_blind", "paraphrase_d"]:
        p = os.path.join(ROOT, d, "gold_lines.json")
        if os.path.exists(p): out.append((d, json.load(open(p))))
    return out

def main():
    bad = tot = 0
    for d, gold in gold_sets():
        for iid, g in gold.items():
            lines = [(r["idx"], r["text"]) for r in g["lines"]]
            raw = V.shot_assistant({"lines": g["lines"]}, echo=True)
            ver = V.parse_verdicts(raw, g["staff"], lines)
            for r in g["lines"]:
                v = ver[r["idx"]]; tot += 1
                if r["kind"]:
                    ok = v.status == "constraint" and sem(v.kind, v.args, g["staff"], g["holders"]) == sem(r["kind"], r["args"], g["staff"], g["holders"])
                else:
                    ok = v.status == "skip" and v.skip == (r["decoy"] or "chat").lower()
                if not ok:
                    bad += 1
                    if bad < 6: print("MISMATCH", d, iid, r["text"], "|", V.fmt_form(r), "|", v)
    print(f"roundtrip: {tot} lines, {bad} mismatches")
    # tolerance of the parser
    st = ["Ayesha", "Daniel", "Ingrid", "Lukas", "Meera"]
    for s_ in ["ON person=ayesha block=11:00 neg=NO", "ON person=Ayesha block=11 neg=yes", "ORDER first=Daniel second=Meera gap=any.",
               "BETWEEN middle=Ingrid ends=Lukas, Meera", "BETWEEN middle=Ingrid ends=Lukas and Meera", "AT person=Lukas station=Intake neg=no", "ORDER first=intake second=Lukas gap=any", "skip:Wish"]:
        v = V.parse_one(1, s_, st, ""); print(f"  {s_!r:55} -> {v.status} {v.kind} {v.args} {v.skip}")
    for s_ in ["ORDER first=Daniel second=Daniel gap=any", "ORDER first=Daniel second=Meera gap=maybe", "ON person=Nobody block=11:00 neg=no", "BEFORE(Daniel, Meera)", "ORDER first=Lukas second=intake gap=any"]:
        v = V.parse_one(1, s_, st, ""); assert v.status in ("invalid",), (s_, v); print(f"  {s_!r:55} -> {v.status} (ok, rejected)")
    # end to end with fake client
    class Fake:
        def __init__(s, items, gold, mutate=None): s.gold, s.items, s.mutate = gold, items, mutate; s.n = 0
        class _C:
            def __init__(s, o): s.o = o
            class _M:
                def __init__(s, t): s.message = type("M", (), {"content": t})
            def create(s, **kw):
                s.o.n += 1; iid = kw["extra_headers"]["X-Item-Id"]; g = s.o.gold[iid]
                rows = [dict(r) for r in g["lines"]]
                if s.o.mutate: rows = s.o.mutate(rows)
                return type("R", (), {"choices": [s._M(V.shot_assistant({"lines": rows}))]})
        @property
        def chat(s): return type("X", (), {"completions": Fake._C(s)})
    for d, gold in gold_sets():
        items = json.load(open(os.path.join(ROOT, d, "items.json"))); key = json.load(open(os.path.join(ROOT, d, "key.json")))
        for name, mut in (("gold", None), ("swap_order", lambda rows: [dict(r, args=r["args"][::-1]) if r["kind"] in ("ORDER_LT", "ORDER_GT", "IMMEDIATE_BEFORE", "IMMEDIATE_AFTER") else r for r in rows])):
            cl = Fake(items, gold, mut); ans = {}
            for it in items:
                a, calls = run_item(cl, "m", it["id"], it["text"], "1x", use_repair=False, knn=3, knn_backend="tfidf"); ans[it["id"]] = a
                assert calls == 1
            r = S.score(key, ans, items); print(f"  e2e {d} {name:11} macro={r['macro_exact_match']:.3f}  calls={cl.n}")
if __name__ == "__main__": main()
