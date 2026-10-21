# Pool E tournament, corrected

`dev/compare_runs.py` read `score()["per_item"]`, which holds CELL accuracy (a fraction) for unique items, as if it were exact
match. That inflated unique accuracy and every macro. The fixed script scores each item on its own, so it agrees with score.py.

| run (120 items, pool E = e + e2) | as reported | corrected exact | 95% CI |
|---|---|---|---|
| base    | 50.5% | 46.7% | [37.5, 55.8] |
| patched | 44.5% | 40.8% | [32.5, 50.0] |
| v3      | 50.7% | 43.3% | [34.2, 52.5] |

Paired (corrected): patched vs base net -7 (p=0.23); v3 vs base net -4 (p=0.63); v3 vs patched net +3 (p=0.73).
Pre-registered rule (v3 must beat patched by >=5 items net, p<0.10): NOT met, same verdict as before (keep patched), but
note the rule never compared against base, which is nominally best on pool E and on pool D + E pooled (59.4% vs 56.7%, 180 items).
Nothing here is statistically distinguishable; do not report any of these as an improvement.
