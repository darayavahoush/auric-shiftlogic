#!/usr/bin/env python3
"""Zero-leakage audit for a phrasing pool. Exits 1 if ANY check fails.

  python3 dev/audit_leakage.py --pool blind --items paraphrase_blind/items.json
  python3 dev/audit_leakage.py --pool d     --items paraphrase_d/items.json
  python3 dev/audit_leakage.py --pool d --negative-control      # must exit 0 *because* it detects planted leaks

Corpus depends on the pool audited. Always: system prompt, shots.json, pool.json (kNN lines), visible items, pools A/B (templates.VISIBLE,
pools.NEW / decoys) and earlier test sets (paraphrase_new, paraphrase_fresh, paraphrase_visiblectl).
For pool d the corpus ALSO includes pool C (blind) templates, names, and its generated sets (paraphrase_blind, paraphrase_blind2), because
those were scored and may have shaped later decisions. Pool c (blind) is audited against the original corpus only, so its published PASS stays valid.
Checks on the pool's templates:
  1. declared decisive phrase is not a substring of the corpus (templates with no single decisive phrase may declare None; the n-gram check covers them)
  2. no word 3-gram (placeholders break fragments) of any template occurs in the corpus
  3. no template equals / masks-equal an earlier-pool template
  4. staff names not already in the corpus (hedges / wrappers already in corpus are reported, not failed)
And, if --items is given, on the generated items: no rendered line (masked) occurs in the corpus.
"""
import argparse, json, os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEV = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT); sys.path.insert(0, DEV)
import src.decompiler_v2 as D
from templates import VISIBLE
import pools as P
import pool_blind as B
import pool_d as PD
import pool_e as PE
import src.decompiler_v3 as D3

def norm(t):
    t = t.replace("’", "'").lower()
    return re.sub(r"[^a-z0-9' ]+", " ", t)
def words(t): return norm(t).split()

def pool_def(name):
    if name == "blind":
        return dict(bind=B.BLIND, decoy=B.BLIND_DECOY, phrase=B.BLIND_PHRASE, names=B.BLIND_NAMES, hedges=B.BLIND_HEDGES, wrappers=B.BLIND_WRAPPERS)
    if name == "d":
        return dict(bind=PD.D_BIND, decoy=PD.D_DECOY, phrase=PD.D_PHRASE, names=PD.D_NAMES, hedges=PD.D_HEDGES, wrappers=PD.D_WRAPPERS)
    if name == "e":
        return dict(bind=PE.E_BIND, decoy=PE.E_DECOY, phrase=PE.E_PHRASE, names=PE.E_NAMES, hedges=PE.E_HEDGES, wrappers=PE.E_WRAPPERS)
    raise SystemExit("unknown pool " + name)

def earlier_pools(name):
    """Pool definitions that count as 'earlier' (part of the corpus) for the pool being audited."""
    return {"blind": [], "d": [pool_def("blind")], "e": [pool_def("blind"), pool_def("d")]}[name]

def sub_ph(t): return re.sub(r"\{[A-Z]\}", "x", t)

def corpus_texts(name):
    out = [D.SYSTEM_PROMPT] + ([D3.SYSTEM_PROMPT] if name == "e" else [])
    shots = json.load(open(os.path.join(ROOT, "src/shots.json")))
    for sh in shots.values(): out += [r["text"] for r in sh["lines"]]
    out += [p["text"] for p in json.load(open(os.path.join(ROOT, "src/pool.json")))]
    sets = ["items.json", "paraphrase_new/items.json", "paraphrase_fresh/items.json", "paraphrase_visiblectl/items.json"]
    if name in ("d", "e"): sets += ["paraphrase_blind/items.json", "paraphrase_blind2/items.json"]
    if name == "e": sets += ["paraphrase_d/items.json", "paraphrase_d2/items.json"]
    for f in sets:
        p = os.path.join(ROOT, f)
        if os.path.exists(p): out += [it["text"] for it in json.load(open(p))]
    out += [t for _, t, _ in VISIBLE] + [t for _, t, _ in P.NEW]
    for d in (P.NEW_DECOY, P.VIS_DECOY): out += [t for v in d.values() for t in v]
    for ep in earlier_pools(name):
        out += [sub_ph(t) for _, t, _ in ep["bind"]] + [sub_ph(t) for v in ep["decoy"].values() for t in v]
    return out

def fragments(tpl): return [f for f in re.split(r"\{[A-Z]\}", tpl) if f.strip()]
def ngrams(ws, n): return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}
def mask(t):
    t = re.sub(r"\b\d\d:00\b", "T", t); t = re.sub(r"\b(intake|calibration|packing)\b", "S", t, flags=re.I)
    return " ".join(words(t))

def audit(name, items=None, extra_bind=(), extra_phrase=None, quiet=False):
    pd = pool_def(name)
    texts = corpus_texts(name)
    blob = " " + " ".join(" ".join(words(t)) for t in texts) + " "
    cw = [words(t) for t in texts]; c3 = set().union(*[ngrams(w, 3) for w in cw]); cwords = set().union(*[set(w) for w in cw])
    fails, info = [], []
    phrase = dict(pd["phrase"]); phrase.update(extra_phrase or {})
    all_t = [(k, t) for k, t, _ in list(pd["bind"]) + list(extra_bind)] + [("DECOY:" + k, t) for k, v in pd["decoy"].items() for t in v if k != "CHAT"]
    chat = [("DECOY:CHAT", t) for t in pd["decoy"]["CHAT"]]
    for kind, t in all_t + chat:
        ph = phrase.get(t)
        if ph and (" " + " ".join(words(ph)) + " ") in blob: fails.append(f"[phrase in corpus] '{ph}' <- {t}")
        if t not in phrase and kind != "DECOY:CHAT": fails.append(f"[no decisive phrase declared] {t}")
        for fr in fragments(t):
            for g in ngrams(words(fr), 3):
                if g in c3: fails.append(f"[3-gram in corpus] '{g}' <- {t}")
    prior = {mask(t) for _, t, _ in VISIBLE} | {mask(t) for _, t, _ in P.NEW}
    prior |= {mask(t) for d in (P.NEW_DECOY, P.VIS_DECOY) for v in d.values() for t in v}
    for ep in earlier_pools(name):
        prior |= {mask(sub_ph(t)) for _, t, _ in ep["bind"]} | {mask(sub_ph(t)) for v in ep["decoy"].values() for t in v}
    for _, t in all_t + chat:
        if mask(re.sub(r"\{[A-Z]\}", "P", t)) in prior: fails.append(f"[template equals earlier template] {t}")
    for n in pd["names"]:
        if n.lower() in cwords: fails.append(f"[name in corpus] {n}")
    for h in pd["hedges"] + pd["wrappers"]:
        if " ".join(words(h)) in blob: info.append(f"hedge/wrapper already in corpus (allowed): '{h.strip()}'")
    if items:
        cmasked = {mask(l) for t in texts for l in t.split("\n")}
        n_checked = 0
        ip = items if os.path.isabs(items) else os.path.join(ROOT, items)
        for it in json.load(open(ip)):
            for l in it["text"].split("\n\n", 1)[1].split("\n"):
                n_checked += 1
                body = re.sub(r"^[^:]{0,60}: ", "", l)
                for h in pd["hedges"] + P.NEW_HEDGES + P.VIS_HEDGES + B.BLIND_HEDGES + PD.D_HEDGES + PE.E_HEDGES:
                    if body.lower().startswith(h.lower()): body = body[len(h):]
                if mask(body) in cmasked: fails.append(f"[rendered line in corpus] {l}")
        info.append(f"checked {n_checked} generated lines")
    summary = f"{len(all_t) + len(chat)} templates, corpus {len(texts)} texts, {len(c3)} distinct 3-grams"
    return fails, info, summary

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="blind", choices=["blind", "d", "e"])
    ap.add_argument("--items", default=None)
    ap.add_argument("--negative-control", action="store_true",
                    help="plant known-leaky templates (a phrase copied from the prompt, from a visible item, from pool C) and require the audit to flag all of them")
    a = ap.parse_args()
    if a.negative_control:
        planted = [("BLOCK_EQ", "{A} takes the {T} block, as agreed.", ("A", "T")),   # filled below from real corpus text
                   ]
        texts = corpus_texts(a.pool)
        leaks = []
        # 1: lifted verbatim from the system prompt (first long sentence-like span)
        sp = [w for w in re.split(r"[.\n]", (D3.SYSTEM_PROMPT if a.pool == "e" else D.SYSTEM_PROMPT)) if len(w.split()) >= 6][3].strip()
        leaks.append(("BLOCK_EQ", "{A} is on {T}. " + sp + ".", ("A", "T")))
        # 2: a visible template reworded only by placeholders
        vis = VISIBLE[0][1]; leaks.append((VISIBLE[0][0], vis, VISIBLE[0][2]))
        # 3: a pool C template (only counts as a leak for pool d)
        for ep in earlier_pools(a.pool): leaks.append(("BLOCK_EQ", ep["bind"][0][1], ep["bind"][0][2]))
        fails, _, _ = audit(a.pool, extra_bind=leaks, extra_phrase={t: " ".join(words(t)[:3]) for _, t, _ in leaks})
        flagged = [l for _, l, _ in leaks if any(l in f for f in fails)]
        print(f"negative control: planted {len(leaks)} leaky templates, audit flagged {len(flagged)}")
        for _, l, _ in leaks: print("  ", "FLAGGED" if l in flagged else "MISSED ", "|", l[:90])
        sys.exit(0 if len(flagged) == len(leaks) else 1)
    fails, info, summary = audit(a.pool, a.items)
    for i in info: print("info:", i)
    if fails:
        print(f"FAIL: {len(fails)} leakage findings"); [print("  ", f) for f in sorted(set(fails))]; sys.exit(1)
    print(f"PASS: {summary}, 0 leakage findings")

if __name__ == "__main__": main()
