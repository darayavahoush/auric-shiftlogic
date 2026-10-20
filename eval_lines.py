#!/usr/bin/env python3
"""Per-line + end-to-end measurement of the v2 extractor against gold labels.

  python eval_lines.py --items paraphrase_new/items.json --gold paraphrase_new/gold_lines.json \
         --key paraphrase_new/key.json --samples 5 --workers 8 --out report_new.json
  python eval_lines.py ... --simulate 0.05,0.10        # no API: noisy stand-in model, to test this script

Every sample is ONE model call at temperature 1.0, top_p 0.95 (the 1x condition). Reports:
  * per-line accuracy and its error taxonomy (wrong direction/polarity, wrong args, missed, decoy leaked, invalid)
  * decoy leakage by decoy type; accuracy by constraint kind
  * lines whose decisive phrase IS / IS NOT in the prompt glossary (paraphrase set only)
  * end-to-end 1x macro score per sample (plain vs +repair) with mean and standard error over samples
"""
import argparse, json, os, random, statistics as st, sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from src.prefilter import prefilter_item
from src.solver import Constraint, generate_all_worlds, BLOCK_TO_IDX
import importlib, os
D = importlib.import_module("src.decompiler_" + os.environ.get("SHIFT_DEC", "v2"))   # SHIFT_DEC=v3 selects the slot-form decompiler
from src.pipeline_v2 import answer_from_raw
import score as S

_W = {}
def worlds(staff, holders):
    k = (tuple(staff), tuple(holders))
    if k not in _W: _W[k] = generate_all_worlds(staff, holders)
    return _W[k]

def sem(kind, args, staff, holders):
    """semantic fingerprint = the set of worlds satisfying it (so BEFORE(S,P) == ORDER_PERSON_STATION(P,S))"""
    a = list(args)
    if kind in ("BLOCK_EQ", "BLOCK_NEQ") and isinstance(a[1], str): a[1] = BLOCK_TO_IDX[a[1]]
    c = Constraint(kind, tuple(a), "")
    return frozenset(i for i, w in enumerate(worlds(staff, holders)) if c.check(w.blocks, w.stations, w.station_blocks))

def noisy_raw(g, e, d, rng):
    """simulate a model: gold verdicts with errors (for testing the harness only)"""
    rows = []
    for r in g["lines"]:
        r = dict(r)
        if r["kind"] and rng.random() < e:
            m = rng.random()
            if m < .3: r["kind"] = None; r["decoy"] = "chat"
            elif r["kind"] in ("BLOCK_EQ", "BLOCK_NEQ", "STATION_EQ", "STATION_NEQ"):
                r["kind"] = {"BLOCK_EQ": "BLOCK_NEQ", "BLOCK_NEQ": "BLOCK_EQ", "STATION_EQ": "STATION_NEQ", "STATION_NEQ": "STATION_EQ"}[r["kind"]]
            elif r["kind"] in ("ORDER_LT", "ORDER_GT", "IMMEDIATE_BEFORE", "IMMEDIATE_AFTER"): r["args"] = r["args"][::-1]
        elif not r["kind"] and rng.random() < d:
            r["kind"] = "BLOCK_NEQ"; r["args"] = [rng.choice(g["staff"]), rng.choice(["07:00", "09:00", "11:00", "13:00", "15:00"])]
        rows.append(r)
    return D.shot_assistant({"lines": rows}, echo=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True); ap.add_argument("--gold", required=True); ap.add_argument("--key", required=True)
    ap.add_argument("--samples", type=int, default=3); ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-echo", action="store_true"); ap.add_argument("--knn", type=int, default=3); ap.add_argument("--logprobs", action="store_true", help="request token logprobs (still ONE call)"); ap.add_argument("--signals-backend", default="tfidf"); ap.add_argument("--knn-backend", default="tfidf"); ap.add_argument("--simulate", default=None)
    ap.add_argument("--out", default=None); ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    items = json.load(open(a.items)); gold = json.load(open(a.gold)); key = json.load(open(a.key))
    if a.limit: items = items[:a.limit]
    client = None; model = os.environ.get("MODEL", "ibm-granite/granite-4.2-8b")
    if not a.simulate:
        from dotenv import load_dotenv; from openai import OpenAI; load_dotenv()
        client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), max_retries=0, timeout=120.0)
    prompt_text = D.SYSTEM_PROMPT.lower()
    jobs = [(it, s) for it in items for s in range(a.samples)]
    import threading
    progress_lock = threading.Lock()
    done_count = 0

    def one(job):
        nonlocal done_count
        it, s = job; g = gold[it["id"]]; pi = prefilter_item(it["id"], it["text"])
        if a.simulate:
            e, d = map(float, a.simulate.split(",")); raw = noisy_raw(g, e, d, random.Random(hash((it["id"], s)) & 0xffffffff))
        else:
            msgs = D.messages_for_item(pi, echo=not a.no_echo, exclude_ids=(it["id"],), knn=a.knn, knn_backend=a.knn_backend)
            raw, conf = "", None
            for attempt in range(4):
                try:
                    if a.logprobs:
                        raw, toks = D.call_granite_v2_lp(client, model, it["id"], msgs); conf = D.result_confidence(raw, toks)
                    else: raw = D.call_granite_v2(client, model, it["id"], msgs); conf = None
                    break
                except Exception as ex:
                    if "429" in str(ex) and attempt < 3:
                        import time
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    print("call failed", it["id"], ex, file=sys.stderr)
                    raw, conf = "", None
                    break
            import time
            time.sleep(0.3)
            with progress_lock:
                done_count += 1
                curr = done_count
            print(f"[{curr}/{len(jobs)}] {it['id']} (sample {s+1}/{a.samples}) done (raw_len={len(raw)})", flush=True)
            return it, s, g, pi, (raw, conf)
        with progress_lock:
            done_count += 1
            curr = done_count
        print(f"[{curr}/{len(jobs)}] {it['id']} (sample {s+1}/{a.samples}) done (raw_len={len(raw)})", flush=True)
        return it, s, g, pi, (raw, None)

    with ThreadPoolExecutor(a.workers) as ex: results = list(ex.map(one, jobs))

    tax = Counter(); by_kind = defaultdict(Counter); leak = defaultdict(Counter); gloss = defaultdict(Counter)
    perfect = []; per_sample = defaultdict(lambda: {"plain": {}, "repair": {}}); raws = {}
    from src.knn import Retriever
    RT = Retriever(a.signals_backend); sims_cache = {}; rows_sig = []
    for it, s, g, pi, (raw, conf) in results:
        raws[f"{it['id']}#{s}"] = raw
        if it["id"] not in sims_cache:
            S_ = RT._sims([r["text"] for r in g["lines"]])
            for j, p in enumerate(RT.pool):
                if p["item"] == it["id"]: S_[:, j] = -1
            sims_cache[it["id"]] = S_
        lines = [(r["idx"], r["text"]) for r in g["lines"]]
        verd = D.parse_verdicts(raw, g["staff"], lines); all_ok = True
        for r in g["lines"]:
            v = verd[r["idx"]]; gk = r["kind"]
            if gk:
                if v.status == "constraint":
                    ok = sem(v.kind, v.args, g["staff"], g["holders"]) == sem(gk, r["args"], g["staff"], g["holders"])
                    cls = "correct" if ok else "wrong_args_or_direction"
                elif v.status == "skip": ok, cls = False, "missed_constraint(skipped)"
                else: ok, cls = False, "invalid_or_missing"
                by_kind[gk]["n"] += 1; by_kind[gk]["ok"] += ok
            else:
                if v.status == "skip":
                    ok = True; cls = "decoy_ok" if v.skip == (r["decoy"] or "chat").lower() else "decoy_ok_wrong_reason"
                elif v.status == "constraint": ok, cls = False, "DECOY_LEAKED_AS_CONSTRAINT"; leak[r["decoy"]]["leaked"] += 1
                else: ok, cls = False, "invalid_or_missing"
                leak[r["decoy"]]["n"] += 1
            tax[cls] += 1; all_ok &= ok
            S_ = sims_cache[it["id"]][r["idx"] - 1]; top = S_.argsort()[::-1][:3]
            votes = sum(1 for j in top if RT.pool[j]["kind"]) ; knn_says_constraint = votes >= 2
            model_says_constraint = v.status == "constraint"
            rows_sig.append({"wrong": not ok, "knn_disagrees": knn_says_constraint != model_says_constraint,
                             "conf": (conf or {}).get(r["idx"])})
            if r.get("phrase") is not None:
                inside = r["phrase"].lower() in prompt_text
                gloss["phrase_in_glossary" if inside else "phrase_NOT_in_glossary"]["n"] += 1
                gloss["phrase_in_glossary" if inside else "phrase_NOT_in_glossary"]["ok"] += ok
        perfect.append(all_ok)
        for rep, name in ((False, "plain"), (True, "repair")):
            ans, legal, _ = answer_from_raw(it["id"], it["text"], raw, use_repair=rep)
            per_sample[s][name][it["id"]] = ans
    def macro(s, name):
        ids = [i["id"] for i in items]; k = {i: key[i] for i in ids}
        return S.score(k, per_sample[s][name], items)["macro_exact_match"]
    mp = [macro(s, "plain") for s in per_sample]; mr = [macro(s, "repair") for s in per_sample]
    n_lines = sum(tax.values())
    correct = tax["correct"] + tax["decoy_ok"] + tax["decoy_ok_wrong_reason"]
    rep = {"samples": a.samples, "items": len(items), "lines": n_lines, "line_accuracy": round(correct / n_lines, 4),
           "items_with_every_line_right": round(sum(perfect) / len(perfect), 4), "taxonomy": dict(tax),
           "constraint_accuracy_by_kind": {k: round(v["ok"] / v["n"], 3) for k, v in sorted(by_kind.items())},
           "decoy_leak_rate_by_type": {k: round(v["leaked"] / v["n"], 3) for k, v in sorted(leak.items())},
           "glossary_split": {k: {"lines": v["n"], "acc": round(v["ok"] / v["n"], 3)} for k, v in gloss.items()},
           "macro_1x_plain": {"mean": round(st.mean(mp), 4), "se": round(st.stdev(mp) / len(mp) ** .5, 4) if len(mp) > 1 else None},
           "macro_1x_with_repair": {"mean": round(st.mean(mr), 4), "se": round(st.stdev(mr) / len(mr) ** .5, 4) if len(mr) > 1 else None}}
    def sig_report(rows):
        n = len(rows); wr = sum(r["wrong"] for r in rows); out = {"lines": n, "error_rate": round(wr / n, 4)}
        fl = [r for r in rows if r["knn_disagrees"]]
        if fl:
            out["knn_flag"] = {"flagged": len(fl), "error_rate_when_flagged": round(sum(r["wrong"] for r in fl) / len(fl), 3),
                               "error_rate_when_not": round(sum(r["wrong"] for r in rows if not r["knn_disagrees"]) / max(1, n - len(fl)), 3),
                               "share_of_all_errors_caught": round(sum(r["wrong"] for r in fl) / max(1, wr), 3)}
        cs = sorted([r for r in rows if r["conf"] is not None], key=lambda r: r["conf"])
        if cs:
            q = max(1, len(cs) // 10)
            out["logprob_conf"] = {"lines_with_conf": len(cs), "error_rate_lowest_10pct": round(sum(r["wrong"] for r in cs[:q]) / q, 3),
                                   "error_rate_highest_90pct": round(sum(r["wrong"] for r in cs[q:]) / max(1, len(cs) - q), 3),
                                   "share_of_all_errors_in_lowest_10pct": round(sum(r["wrong"] for r in cs[:q]) / max(1, wr), 3)}
        return out
    rep["signals"] = sig_report(rows_sig)
    print(json.dumps(rep, indent=2))
    if a.out: json.dump({"report": rep, "raw_outputs": raws}, open(a.out, "w"), indent=1)

if __name__ == "__main__": main()
