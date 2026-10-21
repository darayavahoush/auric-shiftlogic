#!/usr/bin/env python3
"""Paired comparison of several answer files on the SAME items.

  python3 dev/compare_runs.py --key paraphrase_e/key.json --items paraphrase_e/items.json \
      --runs base=results/e_base.json patched=results/e_patched.json v3=results/e_v3.json [--also paraphrase_e2 ...]

Prints per run: macro exact match with a bootstrap 95% interval, per-case rate; and for every run vs the FIRST one: items fixed,
items broken, net, and a two-sided exact sign test on the discordant items. Several (key, items, runs) triples can be pooled with
--sets name:key:items:run1,run2,run3 (same run order in each).
"""
import argparse, json, os, random, sys
from math import comb
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
import score as S

def per_item(key, items, ans):
    """Exact (0/1) per item, computed by scoring each item on its own with score.py, so it matches score.py's
    per_case_rate by construction. (score()['per_item'] holds CELL accuracy, a fraction, for unique items.)"""
    out = {}
    for it in items:
        i = it["id"]
        a = ans.get(i, {"case": "inconsistent", "conflicts": []})
        out[i] = float(S.score({i: key[i]}, {i: a}, [it])["macro_exact_match"])
    return out

def sign_test(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)

def boot(xs, n=4000, seed=1):
    rng = random.Random(seed); m = len(xs)
    means = sorted(sum(xs[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return means[int(.025 * n)], means[int(.975 * n)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", required=True, help="name:key.json:items.json:run1.json,run2.json,...")
    ap.add_argument("--labels", default="base,patched,v3", help="comma-separated run labels, same order as the run files")
    a = ap.parse_args(); labels = a.labels.split(",")
    rows = {l: {} for l in labels}; cases = {}
    for spec in a.sets:
        name, kp, ip, runs = spec.split(":", 3)
        key = json.load(open(kp)); items = json.load(open(ip))
        for l, rp in zip(labels, runs.split(",")):
            for k, v in per_item(key, items, json.load(open(rp))).items(): rows[l][f"{name}/{k}"] = v
        for k in key: cases[f"{name}/{k}"] = key[k]["case"]
    ids = sorted(cases)
    print(f"{len(ids)} items")
    for l in labels:
        xs = [rows[l][i] for i in ids]; lo, hi = boot(xs)
        pc = {c: sum(rows[l][i] for i in ids if cases[i] == c) / max(1, sum(1 for i in ids if cases[i] == c)) for c in ("unique", "ambiguous", "inconsistent")}
        print(f"  {l:10} macro {sum(xs)/len(xs):.3f}  95% CI [{lo:.3f}, {hi:.3f}]   per case " + "  ".join(f"{c[:4]} {v:.2f}" for c, v in pc.items()))
    for l in labels[1:]:
        fixed = [i for i in ids if rows[labels[0]][i] == 0 and rows[l][i] == 1]; broke = [i for i in ids if rows[labels[0]][i] == 1 and rows[l][i] == 0]
        print(f"  {l} vs {labels[0]}: fixed {len(fixed)}  broke {len(broke)}  net {len(fixed)-len(broke):+d}  sign-test p={sign_test(len(fixed), len(broke)):.3f}")
    if len(labels) > 2:
        l1, l2 = labels[1], labels[2]
        f = sum(1 for i in ids if rows[l1][i] == 0 and rows[l2][i] == 1); b = sum(1 for i in ids if rows[l1][i] == 1 and rows[l2][i] == 0)
        print(f"  {l2} vs {l1}: fixed {f}  broke {b}  net {f-b:+d}  sign-test p={sign_test(f, b):.3f}")

if __name__ == "__main__": main()
