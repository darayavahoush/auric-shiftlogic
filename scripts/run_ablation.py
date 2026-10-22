#!/usr/bin/env python3
"""
Component ablation at 1x / 3x / 10x, reproducible, resumable, and without touching the production code path.

Why a sample bank: every prompt-level variant is sampled ONCE, K times per item (K <= 10), and every budget is then derived
offline from those samples exactly as ./run does it (1x = one sample; 3x / 10x = independent samples, each solved on its own,
then a modal vote on the final answer). Post-processing ablations (repair, fuzzy name matching, voting) re-use the SAME
samples, so they are paired comparisons with no extra calls. `selftest` proves the offline path equals pipeline_v2.run_item.

  # 1) see the cost first
  python3 scripts/run_ablation.py plan --items items.json --samples 10
  # 2) collect (resumable; Ctrl-C safe). Uses the .env endpoint, max_retries=0, X-Item-Id on every call
  python3 scripts/run_ablation.py collect --items items.json --key visible_key.json --tag visible --samples 10 --workers 3
  # 3) table (no model calls)
  python3 scripts/run_ablation.py report --items items.json --key visible_key.json --tag visible --samples 10 --out results/ablation_visible.md
  # 4) check the offline path against the real pipeline (fake endpoint, no key needed)
  python3 scripts/run_ablation.py selftest

Prompt-level variants (need samples):  full | fixed10 | no_shots | no_glossary | base_prompt | no_echo | direct
Post-processing ablations (free, from `full`):  no_repair | no_fuzzy | no_vote
"""
import argparse, collections, importlib, json, math, os, random, re, statistics as st, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
import score as S
from src.prefilter import prefilter_item
import src.pipeline_v2 as P
import src.decompiler_v2 as DV2

PROMPT_CFGS = {
    "full":        dict(mod="v2", knn=3, echo=True, desc="patched prompt + glossary + 3 shots + kNN(3) neighbours"),
    "fixed10":     dict(mod="v2", knn=0, echo=True, desc="no kNN: the fixed 10 labelled shots instead"),
    "no_shots":    dict(mod="v2", knn=0, echo=True, shots=False, desc="no kNN and no shots (glossary + format only)"),
    "no_glossary": dict(mod="v2", knn=3, echo=True, glossary=False, desc="word families / skip-reason / hedge text removed"),
    "base_prompt": dict(mod="v2_base", knn=3, echo=True, desc="pre-patch prompt (decompiler_v2_base)"),
    "no_echo":     dict(mod="v2", knn=3, echo=False, desc="model does not copy each line back before its verdict"),
    "direct":      dict(kind="direct", desc="NO solver, NO extraction: Granite answers the item directly (the harness-less baseline)"),
}
POST_CFGS = {  # all from the 'full' bank
    "full":        dict(repair=False, fuzzy=True, vote=True),
    "with_repair": dict(repair=True, fuzzy=True, vote=True),
    "no_fuzzy":    dict(repair=False, fuzzy=False, vote=True),
    "no_vote":     dict(repair=False, fuzzy=True, vote=False),
}
BUDGET_N = {"1x": 1, "3x": 3, "10x": 10}
FAILED = "__CALL_FAILED__"

# ----------------------------------------------------------------------------- helpers
def mod_for(name):
    return importlib.import_module("src.decompiler_" + name)

def minimal_prompt(full_prompt):
    cut = full_prompt.split("WORD FAMILIES")[0]
    return cut + ("SKIP reasons: chat, past, wish, open, unmet. Use SKIP:<reason> for any line that is not a statement of today's roster.")

def exact_person(tok, staff):  # the pre-fuzzy behaviour: exact, then unique prefix
    t = tok.strip().strip("'\"` ").rstrip(".,;")
    for s in staff:
        if s.lower() == t.lower(): return s
    hits = [s for s in staff if s.lower().startswith(t.lower())] if len(t) >= 3 else []
    return hits[0] if len(hits) == 1 else None

DIRECT_SYSTEM = ("You solve shift-rota puzzles. Read the notes. Hedges like 'I'm fairly sure' are as binding as plain statements. "
                 "Reply with ONLY one JSON object, one of:\n"
                 '{"case":"unique","assignment":{"<name>":{"block":"11:00","station":"intake"},"<name with no station>":{"block":"13:00"}}}\n'
                 '{"case":"ambiguous","assignments":[ {...}, {...} ]}   (2 to 4 complete assignments, ALL consistent ones)\n'
                 '{"case":"inconsistent","conflicts":["<statement copied verbatim>", "..."]}   (statements that cannot all hold)\n'
                 "Every assignment names every person on the rota.")

def direct_messages(text):
    return [{"role": "system", "content": DIRECT_SYSTEM}, {"role": "user", "content": text}]

def parse_direct(raw):
    try:
        m = re.search(r"\{.*\}", raw, re.S); a = json.loads(m.group(0))
        if a.get("case") == "unique" and isinstance(a.get("assignment"), dict): return {"case": "unique", "assignment": a["assignment"]}
        if a.get("case") == "ambiguous" and isinstance(a.get("assignments"), list): return {"case": "ambiguous", "assignments": a["assignments"]}
        if a.get("case") == "inconsistent": return {"case": "inconsistent", "conflicts": [str(c) for c in a.get("conflicts", [])]}
    except Exception:
        pass
    return {"case": "inconsistent", "conflicts": []}

def build_messages(cfg_name, item):
    cfg = PROMPT_CFGS[cfg_name]
    if cfg.get("kind") == "direct": return direct_messages(item["text"])
    D = mod_for(cfg["mod"]); pi = prefilter_item(item["id"], item["text"])
    saved = (D.SYSTEM_PROMPT, D.load_shots)
    try:
        if cfg.get("glossary") is False: D.SYSTEM_PROMPT = minimal_prompt(saved[0])
        if cfg.get("shots") is False: D.load_shots = lambda *a, **k: {}
        return D.messages_for_item(pi, echo=cfg["echo"], exclude_ids=(item["id"],), knn=cfg["knn"], knn_backend="tfidf")
    finally:
        D.SYSTEM_PROMPT, D.load_shots = saved

def knn_flags(D, pi, raw, item_id, backend="tfidf"):
    """identical to the block in pipeline_v2.run_item (only used by repair)"""
    flagged = set()
    try:
        from src.knn import Retriever
        R = D._RETRIEVER.get(backend) or D._RETRIEVER.setdefault(backend, Retriever(backend))
        S_ = R._sims(pi.all_lines)
        for j, p in enumerate(R.pool):
            if p["item"] == item_id: S_[:, j] = -1
        _, v_dict = D.decompile_v2(pi, raw)
        for idx, l_text in pi.candidate_lines:
            top = S_[idx - 1].argsort()[::-1][:3]
            votes = sum(1 for j in top if R.pool[j]["kind"])
            v = v_dict.get(idx)
            if (votes >= 2) != (v is not None and v.status == "constraint"): flagged.add(l_text)
    except Exception:
        flagged = set()
    return flagged

# ----------------------------------------------------------------------------- bank
def bank_path(tag, cfg): return os.path.join(ROOT, "results", "ablation", f"bank_{tag}_{cfg}.jsonl")

def load_bank(tag, cfg):
    out = {}
    p = bank_path(tag, cfg)
    if os.path.exists(p):
        for line in open(p):
            if line.strip():
                r = json.loads(line); out[(r["item"], r["sample"])] = r["raw"]
    return out

def cmd_plan(a):
    items = json.load(open(a.items)); cfgs = a.configs.split(",")
    calls = len(items) * a.samples * len(cfgs)
    print(f"{len(items)} items x {a.samples} samples x {len(cfgs)} prompt variants {cfgs} = {calls} model calls")
    print(f"at ~15 s/call and {a.workers} workers: about {calls * 15 / a.workers / 3600:.1f} h; post-processing ablations are free")
    print("NOTE: these calls exceed the per-item budget of any single ./run; if the organisers' proxy meters ablation runs, "
          "ask first or use --header-prefix.")

def cmd_collect(a):
    from dotenv import load_dotenv; from openai import OpenAI
    load_dotenv()
    client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                    max_retries=0, timeout=300.0)
    model = os.environ.get("MODEL", "ibm-granite/granite-4.2-8b")
    items = json.load(open(a.items)); lock = threading.Lock()
    for cfg in a.configs.split(","):
        os.makedirs(os.path.dirname(bank_path(a.tag, cfg)), exist_ok=True)
        have = load_bank(a.tag, cfg); jobs = []
        msgs = {it["id"]: build_messages(cfg, it) for it in items}
        for it in items:
            for s in range(a.samples):
                if (it["id"], s) not in have: jobs.append((it, s))
        print(f"[{cfg}] {len(jobs)} calls to make ({len(have)} already banked)", flush=True)
        fh = open(bank_path(a.tag, cfg), "a")
        done = [0]
        def one(job):
            it, s = job
            time.sleep(a.sleep)
            try:
                r = client.chat.completions.create(model=model, messages=msgs[it["id"]], temperature=1.0, top_p=0.95, timeout=300.0,
                        extra_headers={"X-Item-Id": a.header_prefix + it["id"]}, extra_body={"reasoning": {"enabled": False}})
                raw = r.choices[0].message.content or ""
            except Exception as e:
                print(f"  call failed {it['id']}#{s}: {str(e)[:80]}", file=sys.stderr); raw = FAILED
            with lock:
                done[0] += 1
                fh.write(json.dumps({"item": it["id"], "sample": s, "raw": raw}) + "\n"); fh.flush()
                if done[0] % 10 == 0 or done[0] == len(jobs):
                    print(f"  [{cfg}] {done[0]}/{len(jobs)} banked", flush=True)
        with ThreadPoolExecutor(a.workers) as ex: list(ex.map(one, jobs))
        fh.close()

# ----------------------------------------------------------------------------- offline answers
class Offline:
    def __init__(self, items, tag):
        self.items = {it["id"]: it for it in items}; self.tag = tag; self.cache = {}; self.banks = {}
    def bank(self, cfg):
        if cfg not in self.banks: self.banks[cfg] = load_bank(self.tag, cfg)
        return self.banks[cfg]
    def answer(self, prompt_cfg, post, item_id, sample):
        """one sample -> (answer, legal) or None if the call failed (as in run_item)"""
        key = (prompt_cfg, tuple(sorted(post.items())), item_id, sample)
        if key in self.cache: return self.cache[key]
        raw = self.bank(prompt_cfg).get((item_id, sample))
        if raw is None: return "MISSING"
        if raw == FAILED: res = None
        elif PROMPT_CFGS[prompt_cfg].get("kind") == "direct": res = (parse_direct(raw), True)
        else:
            D = mod_for(PROMPT_CFGS[prompt_cfg]["mod"]); P.D = D
            saved = D._person
            if not post["fuzzy"]: D._person = exact_person
            try:
                it = self.items[item_id]; pi = prefilter_item(item_id, it["text"])
                fl = knn_flags(D, pi, raw, item_id) if post["repair"] else set()
                a, legal, _ = P.answer_from_raw(item_id, it["text"], raw, post["repair"], knn_flagged=fl)
                res = (a, legal)
            finally:
                D._person = saved
        self.cache[key] = res; return res
    def item_answer(self, prompt_cfg, post, item_id, samples):
        got = [self.answer(prompt_cfg, post, item_id, s) for s in samples]
        if any(g == "MISSING" for g in got): return "MISSING"
        got = [g for g in got if g is not None]
        if not got: return {"case": "inconsistent", "conflicts": []}
        pool = [a for a, l in got if l] or [a for a, _ in got]
        if not post["vote"]: return pool[0]
        best = collections.Counter(P._vote_key(a) for a in pool).most_common(1)[0][0]
        return next(a for a in pool if P._vote_key(a) == best)

def score_run(off, key, items, prompt_cfg, post, samples):
    ans = {}
    for it in items:
        a = off.item_answer(prompt_cfg, post, it["id"], samples)
        if a == "MISSING": return None
        ans[it["id"]] = a
    r = S.score(key, ans, items); return r["macro_exact_match"], r["per_case_rate"]

def runs_for(budget, samples, max_runs_1x):
    n = BUDGET_N[budget]; k = samples // n
    if budget == "1x": k = min(k, max_runs_1x)
    return [list(range(r * n, (r + 1) * n)) for r in range(k)]

def avail_samples(off, cfg, items, cap):
    """number of samples 0..k-1 banked for EVERY item of this variant (variants may have been collected with different K)"""
    bank = off.bank(cfg); k = 0
    while k < cap and all((it["id"], k) in bank for it in items): k += 1
    return k

def cmd_report(a):
    items = json.load(open(a.items)); key = json.load(open(a.key)); off = Offline(items, a.tag)
    rows = []
    variants = [(p, "full", PROMPT_CFGS[p]["desc"]) for p in PROMPT_CFGS if os.path.exists(bank_path(a.tag, p))]
    if os.path.exists(bank_path(a.tag, "full")):
        variants += [("full", n, f"post-processing: {n}") for n in ("with_repair", "no_fuzzy", "no_vote")]
    hdr = "| component removed / variant | " + " | ".join(f"{b} macro (runs)" for b in BUDGET_N) + " |\n|---|" + "---|" * len(BUDGET_N)
    lines = [f"Ablation on `{a.items}` ({len(items)} items, key `{a.key}`), samples/item banked: {a.samples}.",
             "Each cell: mean macro exact match +/- standard error across independent runs (n = number of runs; a variant collected with fewer samples has fewer/no 3x, 10x runs). "
             "1x runs = single samples; 3x runs = disjoint triples; 10x = one run of 10.", "", hdr]
    for pc, post_name, desc in variants:
        post = POST_CFGS[post_name]; cells = []
        for b in BUDGET_N:
            vals = []
            for smp in runs_for(b, avail_samples(off, pc, items, a.samples), a.max_runs_1x):
                r = score_run(off, key, items, pc, post, smp)
                if r: vals.append(r[0])
            if not vals: cells.append("n/a")
            elif len(vals) == 1: cells.append(f"{100*vals[0]:.1f}% (n=1)")
            else: cells.append(f"{100*st.mean(vals):.1f}% ± {100*st.stdev(vals)/len(vals)**.5:.1f} (n={len(vals)})")
        label = post_name if post_name != "full" else pc
        lines.append(f"| **{label}** — {desc} | " + " | ".join(cells) + " |")
    out = "\n".join(lines); print(out)
    if a.out: open(a.out, "w").write(out + "\n")

# ----------------------------------------------------------------------------- selftest
def cmd_selftest(a):
    import unittest.mock
    items = json.load(open(os.path.join(ROOT, "paraphrase_fresh", "items.json")))[:9]
    gold = json.load(open(os.path.join(ROOT, "paraphrase_fresh", "gold_lines.json")))
    sys.path.insert(0, ROOT)
    from eval_lines import noisy_raw
    rec = collections.defaultdict(list); rng = random.Random(3)
    class MockCompletions:
        def create(self, **kwargs):
            iid = kwargs.get("extra_headers", {}).get("X-Item-Id")
            raw = noisy_raw(gold[iid], 0.15, 0.2, rng)
            rec[iid].append(raw)
            choice = type("Choice", (), {"message": type("Msg", (), {"content": raw})()})()
            return type("Resp", (), {"choices": [choice]})()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": MockCompletions()})()})()
    live = {}
    with unittest.mock.patch("time.sleep", return_value=None):
        for b in ("1x", "3x", "10x"):
            rec.clear(); P.D = DV2
            for it in items:
                # fresh sample sequence per budget: the offline path replays exactly what the live path received
                ans, calls = P.run_item(client, "m", it["id"], it["text"], b, exclude_ids=(it["id"],), knn=3, knn_backend="tfidf")
                assert calls == BUDGET_N[b], (b, calls)
                live[(b, it["id"])] = (ans, list(rec[it["id"]]))
    bad = 0
    for (b, iid), (ans, raws) in live.items():
        off = Offline(items, "selftest"); off.banks["full"] = {(iid, i): r for i, r in enumerate(raws)}
        mine = off.item_answer("full", POST_CFGS["full"], iid, list(range(BUDGET_N[b])))
        if mine != ans: bad += 1; print("MISMATCH", b, iid)
    print(f"selftest: {len(live)} (budget,item) pairs compared offline-vs-live: {'ALL IDENTICAL' if not bad else str(bad) + ' MISMATCHES'}")
    sys.exit(1 if bad else 0)

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("plan", cmd_plan), ("collect", cmd_collect), ("report", cmd_report), ("selftest", cmd_selftest)):
        p = sub.add_parser(name); p.set_defaults(fn=fn)
        p.add_argument("--items", default="items.json"); p.add_argument("--key", default="visible_key.json"); p.add_argument("--tag", default="visible")
        p.add_argument("--samples", type=int, default=10); p.add_argument("--workers", type=int, default=2)
        p.add_argument("--configs", default="full,fixed10,no_shots,no_glossary,base_prompt,direct")
        p.add_argument("--sleep", type=float, default=0.3); p.add_argument("--header-prefix", default="")
        p.add_argument("--max-runs-1x", type=int, default=10); p.add_argument("--out", default=None)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__": main()
