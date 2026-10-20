#!/usr/bin/env python3
"""Zero-leakage audit for a phrasing pool (default: blind). Exits 1 if ANY check fails.

Corpus = everything the model can see or the author has tuned against:
  system prompt (src/decompiler_v2.SYSTEM_PROMPT), shots.json, pool.json (kNN lines), visible items.json,
  earlier pools (templates.VISIBLE, pools.NEW / decoys), and the earlier test sets (paraphrase_new, paraphrase_fresh).
Checks on the pool's templates:
  1. declared decisive phrase is not a substring of the corpus
  2. no word 3-gram (placeholders break fragments) of any template occurs in the corpus
  3. no template equals / masks-equal an earlier-pool template
  4. staff names (and hedges / wrappers) not already in the corpus  (hedges are reported, not failed: the scorer's
     known-hedge list is intentionally reused for some)
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

def norm(t):
    t = t.replace("’", "'").lower()
    return re.sub(r"[^a-z0-9' ]+", " ", t)

def words(t): return norm(t).split()

def corpus_texts():
    out = [D.SYSTEM_PROMPT]
    shots = json.load(open(os.path.join(ROOT, "src/shots.json")))
    for sh in shots.values():
        out += [r["text"] for r in sh["lines"]]
    out += [p["text"] for p in json.load(open(os.path.join(ROOT, "src/pool.json")))]
    for f in ("items.json", "paraphrase_new/items.json", "paraphrase_fresh/items.json", "paraphrase_visiblectl/items.json"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p): out += [it["text"] for it in json.load(open(p))]
    out += [t for _, t, _ in VISIBLE] + [t for _, t, _ in P.NEW]
    for d in (P.NEW_DECOY, P.VIS_DECOY): out += [t for v in d.values() for t in v]
    return out

def fragments(tpl):
    return [f for f in re.split(r"\{[A-Z]\}", tpl) if f.strip()]

def ngrams(ws, n): return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}

def mask(t):
    t = re.sub(r"\b\d\d:00\b", "T", t); t = re.sub(r"\b(intake|calibration|packing)\b", "S", t, flags=re.I)
    return " ".join(words(t))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--items", default=None); a = ap.parse_args()
    texts = corpus_texts(); blob = " " + " ".join(" ".join(words(t)) for t in texts) + " "
    cw = [words(t) for t in texts]; c3 = set().union(*[ngrams(w, 3) for w in cw]); cwords = set().union(*[set(w) for w in cw])
    fails = []; info = []
    all_t = [(k, t) for k, t, _ in B.BLIND] + [("DECOY:" + k, t) for k, v in B.BLIND_DECOY.items() for t in v if k != "CHAT"]
    chat = [("DECOY:CHAT", t) for t in B.BLIND_DECOY["CHAT"]]
    for kind, t in all_t + chat:
        # 1
        ph = B.BLIND_PHRASE.get(t)
        if ph and (" " + " ".join(words(ph)) + " ") in blob: fails.append(f"[phrase in corpus] '{ph}' <- {t}")
        if not ph and kind != "DECOY:CHAT": fails.append(f"[no decisive phrase declared] {t}")
        # 2
        for fr in fragments(t):
            ws = words(fr)
            for g in ngrams(ws, 3):
                if g in c3: fails.append(f"[3-gram in corpus] '{g}' <- {t}")
    # 3
    prior = {mask(t) for _, t, _ in VISIBLE} | {mask(t) for _, t, _ in P.NEW}
    prior |= {mask(t) for d in (P.NEW_DECOY, P.VIS_DECOY) for v in d.values() for t in v}
    for _, t in all_t + chat:
        if mask(re.sub(r"\{[A-Z]\}", "P", t)) in prior: fails.append(f"[template equals earlier template] {t}")
    # 4
    for n in B.BLIND_NAMES:
        if n.lower() in cwords: fails.append(f"[name in corpus] {n}")
    for h in B.BLIND_HEDGES + B.BLIND_WRAPPERS:
        if " ".join(words(h)) in blob: info.append(f"hedge/wrapper already in corpus (allowed): '{h.strip()}'")
    # generated items
    if a.items:
        cmasked = {mask(l) for t in texts for l in t.split("\n")}
        n_checked = 0
        for it in json.load(open(os.path.join(ROOT, a.items) if not os.path.isabs(a.items) else a.items)):
            for l in it["text"].split("\n\n", 1)[1].split("\n"):
                n_checked += 1
                body = re.sub(r"^[^:]{0,60}: ", "", l)
                for h in B.BLIND_HEDGES + P.NEW_HEDGES + P.VIS_HEDGES:
                    if body.lower().startswith(h.lower()): body = body[len(h):]
                if mask(body) in cmasked: fails.append(f"[rendered line in corpus] {l}")
        info.append(f"checked {n_checked} generated lines")
    for i in info: print("info:", i)
    if fails:
        print(f"FAIL: {len(fails)} leakage findings"); [print("  ", f) for f in sorted(set(fails))]; sys.exit(1)
    print(f"PASS: {len(all_t) + len(chat)} templates, 0 leakage findings (corpus {len(texts)} texts, {len(c3)} distinct 3-grams)")

if __name__ == "__main__": main()
