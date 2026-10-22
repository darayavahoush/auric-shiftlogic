Ablation on `paraphrase_e2/items.json` (60 items, key `paraphrase_e2/key.json`), samples/item banked: 10.
Each cell: mean macro exact match +/- standard error across independent runs (n = number of runs; a variant collected with fewer samples has fewer/no 3x, 10x runs). 1x runs = single samples; 3x runs = disjoint triples; 10x = one run of 10.

| component removed / variant | 1x macro (runs) | 3x macro (runs) | 10x macro (runs) |
|---|---|---|---|
| **full** — patched prompt + glossary + 3 shots + kNN(3) neighbours | 61.8% ± 1.4 (n=10) | 68.3% ± 1.0 (n=3) | 71.7% (n=1) |
| **with_repair** — post-processing: with_repair | 62.3% ± 1.2 (n=10) | 68.3% ± 1.7 (n=3) | 71.7% (n=1) |
| **no_fuzzy** — post-processing: no_fuzzy | 61.8% ± 1.4 (n=10) | 68.3% ± 1.0 (n=3) | 71.7% (n=1) |
| **no_vote** — post-processing: no_vote | 61.8% ± 1.4 (n=10) | 68.3% ± 1.0 (n=3) | 70.0% (n=1) |
