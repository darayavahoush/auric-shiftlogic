Ablation on `items.json` (60 items, key `visible_key.json`), samples/item banked: 10.
Each cell: mean macro exact match +/- standard error across independent runs (n = number of runs; a variant collected with fewer samples has fewer/no 3x, 10x runs). 1x runs = single samples; 3x runs = disjoint triples; 10x = one run of 10.

| component removed / variant | 1x macro (runs) | 3x macro (runs) | 10x macro (runs) |
|---|---|---|---|
| **full** — patched prompt + glossary + 3 shots + kNN(3) neighbours | 98.8% ± 0.4 (n=10) | 100.0% ± 0.0 (n=3) | 100.0% (n=1) |
| **base_prompt** — pre-patch prompt (decompiler_v2_base) | 97.0% ± 0.3 (n=5) | 96.7% (n=1) | n/a |
| **direct** — NO solver, NO extraction: Granite answers the item directly (the harness-less baseline) | 0.0% ± 0.0 (n=5) | 0.0% (n=1) | n/a |
| **no_repair** — post-processing: no_repair | 97.8% ± 0.6 (n=10) | 98.9% ± 0.6 (n=3) | 98.3% (n=1) |
| **no_fuzzy** — post-processing: no_fuzzy | 98.8% ± 0.4 (n=10) | 100.0% ± 0.0 (n=3) | 100.0% (n=1) |
| **no_vote** — post-processing: no_vote | 98.8% ± 0.4 (n=10) | 99.4% ± 0.6 (n=3) | 98.3% (n=1) |
