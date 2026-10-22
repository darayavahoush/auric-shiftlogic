Ablation on `paraphrase_d/items.json` (60 items, key `paraphrase_d/key.json`), samples/item banked: 10.
Each cell: mean macro exact match +/- standard error across independent runs (n = number of runs; a variant collected with fewer samples has fewer/no 3x, 10x runs). 1x runs = single samples; 3x runs = disjoint triples; 10x = one run of 10.

| component removed / variant | 1x macro (runs) | 3x macro (runs) | 10x macro (runs) |
|---|---|---|---|
| **full** — patched prompt + glossary + 3 shots + kNN(3) neighbours | 93.8% ± 0.7 (n=10) | 94.4% ± 1.5 (n=3) | 95.0% (n=1) |
| **with_repair** — post-processing: with_repair | 92.8% ± 0.6 (n=10) | 93.3% ± 1.0 (n=3) | 93.3% (n=1) |
| **no_fuzzy** — post-processing: no_fuzzy | 93.8% ± 0.7 (n=10) | 94.4% ± 1.5 (n=3) | 95.0% (n=1) |
| **no_vote** — post-processing: no_vote | 93.8% ± 0.7 (n=10) | 93.9% ± 1.5 (n=3) | 91.7% (n=1) |
