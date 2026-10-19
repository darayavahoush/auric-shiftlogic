import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Budget accounting + voting, with a fake client (no network)."""
import json, sys, random
sys.path.insert(0, ROOT); sys.path.insert(0, DEV)
import src.decompiler_v2 as D
from src.pipeline_v2 import run_item
import score as S
d = ROOT + "/paraphrase_new"
items = json.load(open(f"{d}/items.json")); key = json.load(open(f"{d}/key.json")); gold = json.load(open(f"{d}/gold_lines.json"))
sys.path.insert(0, DEV); from eval_lines import noisy_raw

class Msg:  # minimal OpenAI-shaped response
    def __init__(s, t): s.message = type("M", (), {"content": t})()
class Fake:
    def __init__(s, iid, fail=()): s.iid, s.n, s.fail, s.rng = iid, 0, set(fail), random.Random(5)
    @property
    def chat(s): return s
    @property
    def completions(s): return s
    def create(s, **kw):
        s.n += 1
        assert kw["extra_headers"]["X-Item-Id"] == s.iid and kw["extra_body"] == {"reasoning": {"enabled": False}}
        assert kw["temperature"] == 1.0 and kw["top_p"] == 0.95
        if s.n in s.fail: raise RuntimeError("429")
        return type("R", (), {"choices": [Msg(noisy_raw(gold[s.iid], 0.06, 0.10, s.rng))]})()

for budget, expect in (("1x", 1), ("3x", 3), ("10x", 10)):
    ans, tot = {}, 0
    for it in items:
        c = Fake(it["id"], fail={2} if budget != "1x" else ())      # a failed call still counts, and is NOT retried
        a, calls = run_item(c, "m", it["id"], it["text"], budget)
        assert c.n == expect == calls, (budget, c.n, calls)
        ans[it["id"]] = a
    print(budget, "requests/item =", expect, " macro vs key (simulated 6%/10% model):", S.score(key, ans, items)["macro_exact_match"])
