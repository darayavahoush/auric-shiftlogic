import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Format round trip: a 'perfect model' stub writes v2-format answers from gold labels; parse -> solve -> score.
Proves the prompt format, parser and kind mapping lose nothing. Says NOTHING about Granite's accuracy."""
import json, sys, os
sys.path.insert(0, ROOT); sys.path.insert(0, DEV)
from src.prefilter import prefilter_item
from src.solver import solve
import src.decompiler_v2 as D
import score as S

def run(items_path, key_path, gold_path, exclude=()):
    items = json.load(open(items_path)); key = json.load(open(key_path)); gold = json.load(open(gold_path))
    ans = {}; ntok = 0
    for it in items:
        if it["id"] in exclude: continue
        pi = prefilter_item(it["id"], it["text"])
        g = gold[it["id"]]
        raw = D.shot_assistant({"lines": g["lines"]}, echo=True)     # perfect model output
        cons, verdicts = D.decompile_v2(pi, raw)
        r = solve(pi.header.staff, pi.header.station_holders, cons)
        e = {"case": r["case"] if r["case"] != "under_constrained" else "unique"}
        if r["case"] == "unique": e["assignment"] = r["assignment"]
        elif r["case"] == "ambiguous": e["assignments"] = r["assignments"]
        elif r["case"] == "inconsistent": e["conflicts"] = r["conflicts"]
        ans[it["id"]] = e
    k2 = {i: key[i] for i in ans}
    res = S.score(k2, ans, [i for i in items if i["id"] in ans])
    return res["macro_exact_match"], len(ans)

shots = json.load(open(ROOT + "/src/shots.json"))
print("visible (excl. shot items):", run(ROOT + "/items.json", ROOT + "/visible_key.json", ROOT + "/visible_gold_lines.json", exclude=set(shots)))
print("paraphrase_new:", run(ROOT + "/paraphrase_new/items.json", ROOT + "/paraphrase_new/key.json", ROOT + "/paraphrase_new/gold_lines.json"))
print("visible-control:", run(ROOT + "/paraphrase_visiblectl/items.json", ROOT + "/paraphrase_visiblectl/key.json", ROOT + "/paraphrase_visiblectl/gold_lines.json"))
msgs = D.build_messages(["A","B","C","D","E"], ["A","B","C"], [(1,"x")], shots=shots)
import re
chars = sum(len(m["content"]) for m in msgs); print("prompt chars", chars, "~tokens", chars//4, "messages", len(msgs))
