# Architecture Under a Fixed, Weak Model: The ShiftLogic System
**Auric AI Take-Home Submission** | **Target Model:** `ibm-granite/granite-4.2-8b` (`temp=1.0`, `top_p=0.95`, non-thinking)

---

## 1. Characterising the Model Before Designing Around It

Directly prompted (zero- or one-shot) to output complete shift schedules, `ibm-granite/granite-4.2-8b` scored **0.0% macro exact match** on the 60 visible items, collapsing under discrete permutations (frontier Claude Sonnet achieved 67.5% in the brief baseline under direct prompting).

Granite 4.2 8B is an 8B dense instruct model with sharp capability boundaries:
- **Combinatorial Reasoning (Failure):** Cannot navigate the $5! \times 3! = 720$ state space, hallucinating duplicate assignments and failing joint consistency over 20+ lines.
- **Local Semantic Extraction (Strength):** Reliably classifies grammatical tense, extracts entities, and separates operational shifts from conversational padding ("chat", "wish", "past rota").
- **Extraction Slips:** Passive clause inversion (*"X is relieved by Y"*), counterfactual leakage, surface typos, and provisional reasoning before revising verdicts.

**Design Thesis:** Use Granite exclusively as a semantic compiler from natural language clauses to typed AST constraints (`ON`, `NOT_ON`, `AT`, `NOT_AT`, `BEFORE`, `NEXT`, `BETWEEN`) or skip categories (`chat`, `past`, `wish`, `open`, `unmet`). Outsource all combinatorial deduction and conflict extraction to an exhaustive symbolic solver.

---

## 2. Architecture: Model-Based Extraction vs. Symbolic Solving

**Constraint extraction is strictly model-based; constraint solving is strictly symbolic.**

1. **Deterministic Pre-Filter:** Parses staff, holders, and time blocks from headers, pruning zero-entity noise lines.
2. **Model-Based Decompiler:** Emits an echo and verdict per line. Uses kNN(3) TF-IDF retrieval for in-context demonstrations, Levenshtein-1 name matching, and a *last-verdict-wins* parser that captures revised labels when Granite reasons aloud.
3. **Symbolic 720-World Solver:** Evaluates the state space ($5! \times 3! = 720$) in $<1\text{ ms}$ via vectorised boolean operations: returns the assignment if `unique` ($|\Omega| = 1$), consistent assignments if `ambiguous` ($2 \le |\Omega| \le 4$), or computes the Minimal Unsatisfiable Core (MUS) via greedy deletion if `inconsistent` ($|\Omega| = 0$).
4. **Late Voting (3x / 10x):** At higher budgets, $K$ independent model samples are decompiled and solved independently. Modal voting occurs on the final structured answer `(case, content)`.

---

## 3. Component Rationale & Empirical Ablation

```
Ablation on items.json (60 items, key visible_key.json, 10 banked samples/item)
1x = single samples; 3x = disjoint triples; 10x = full 10-sample run
```

| Component Removed / Variant | 1x Macro (runs) | 3x Macro (runs) | 10x Macro (runs) | Description / Finding |
| :--- | :---: | :---: | :---: | :--- |
| **ShiftLogic (Full Production)** | **97.8% ± 0.6** ($n=10$) | **98.9% ± 0.6** ($n=3$) | **98.3%** ($n=1$) | Patched prompt + kNN(3) + last-verdict + fuzzy + voting |
| **Pre-Patch Prompt (`base_prompt`)** | 97.0% ± 0.3 ($n=5$) | 96.7% ($n=1$) | — | Modest in-sample gain; no out-of-sample benefit shown |
| **Without Fuzzy Matcher (`no_fuzzy`)** | 97.8% ± 0.6 ($n=10$) | 98.9% ± 0.6 ($n=3$) | 98.3% ($n=1$) | Clean in-sample names; guards OCR/spelling slips |
| **Without Majority Voting (`no_vote`)** | 97.8% ± 0.6 ($n=10$) | 98.3% ± 1.0 ($n=3$) | 96.7% ($n=1$) | 10x drops from 98.3% to 96.7% without voting |
| **With 0-Call Repair (`with_repair`)** | 98.8% ± 0.4 ($n=10$) | 100.0% ± 0.0 ($n=3$) | 100.0% ($n=1$) | In-sample 100% ceiling; actively harms held-out formal text ($p=0.031$) |
| **Harness-Less Direct Granite (`direct`)** | **0.0% ± 0.0** ($n=5$) | **0.0%** ($n=1$) | — | Baseline reproduction; total permutation collapse |

*Frontier Claude Sonnet 5 scored 67.5% in the brief baseline under direct zero-shot prompting.*

**Scaling Curves Across Registers:**
- **Formal Held-Out (Pool D):** Scales monotonically: **93.8% ± 0.7 (1x) $\to$ 94.4% ± 1.5 (3x) $\to$ 95.0% (10x)**. While heuristic repair reaches 100% in-sample on visible items, it actively harms held-out formal accuracy (93.8% $\to$ 92.8% at 1x; removing repair fixes 6 item-runs and breaks 0, $p=0.031$), confirming that flipping constraints without textual evidence manufactures false consistency.
- **Colloquial Held-Out (Pool E2):** Scales from **61.8% ± 1.4 (1x) $\to$ 68.3% ± 1.0 (3x) $\to$ 71.7% (10x)** (+9.9 points). Enabling repair yields 62.3% at 1x, which is not statistically significant ($p=0.375$).
- **Voting Significance Caveat:** While multi-sample scaling provides clear gains, the paired 10x comparison between `full` (71.7%) and `no_vote` (70.0%) on Pool E2 is not statistically separable on $n=1$ ($p=0.34$, voting fixes 7 and breaks 3).
- **Direct Granite Baseline (0.0%):** Confirms all performance stems from neuro-symbolic decomposition.

---

## 4. What We Built, Tested, and Removed

- **Iterative LLM Repair (FSM Controller):** Scored **48.3% (3x)** and **56.7% (10x)** on visible items. Granite entered hallucination loops when prompted with solver contradictions. Discarded for independent sampling + late voting.
- **0-Call Heuristic Constraint Repair:** Harms accuracy on formal text ($p=0.031$) and is not significant on colloquial text ($p=0.375$). Disabled by default; kept as opt-in flag (`--repair`).
- **Slot-Form Decompiler (`v3`):** Scored 43.3% vs base 46.7% ($p=0.63$) in a 120-item blind tournament on Pool E. Failed adoption threshold (+5 net, $p<0.10$); discarded.
- **Rule-Based Ellipsis Expansion:** Regex rewriting was rejected to avoid brittle overrides. Instead, parser flexibility (*last-verdict-wins*) lifted E2 1x from 53.7% to 61.8% without modifying text.

---

## 5. Where the System Breaks & Multi-Author Generalisation

| Evaluation Suite | Register / Wording Style | Sample Size | Line Accuracy | Macro Exact Match |
| :--- | :--- | :---: | :---: | :---: |
| **Visible 60 Items** | Formal, templated shifts | 60 | 98.8% | **96.67%** (1x live) / **100.0%** (10x live) |
| **Pool D (Blind)** | Nominalised, formal prose | 60 | 97.8% | **93.8%** (1x) / **95.0%** (10x) |
| **Pool C (Blind)** | Short, active declarative | 120 | 96.0% | **65.00%** (1x) |
| **Pool E1 (Dev half)** | Spoken hand-over fragments | 60 | 90.2% | **50.60%** (1x) |
| **Pool E2 (Blind test)**| Spoken hand-over fragments | 60 | 92.4% | **61.8%** (1x) / **71.7%** (10x) |

*Note: Section 3 ablation reports the mean across 10 banked runs (97.8% ± 0.6); Section 5 visible score reflects the single-run live execution (96.67%).*

**Author Variation Reality:** Formal prose reaches **93.8% – 95.0%**, short active statements reach **65.0%**, and spoken hand-overs score **50.6% – 61.8% at 1x**, scaling to **71.7% at 10x**. Compounding 1% per-line error over ~20 lines causes a ~15–20% item drop. Central held-out projection: **~70% (range: 65% – 95%)**.

---

## 6. One-Month Roadmap (Strictly No Fine-Tuning)

Per brief constraints (*"self-hosted, air-gapped, and we do not fine-tune"*), production enhancements are architectural:

1. **Grammar-Constrained Decoding (CFG Logits Masking):** Enforce an AST grammar at inference time via Outlines/vLLM logits processors, guaranteeing well-formed AST outputs and eliminating unparseable formats.
2. **Dense Multi-Register Retrieval Bank:** Scale kNN retrieval from 60 visible items to 2,000+ validated sentences covering colloquial, passive, and spoken registers.
3. **Calibrated Operator Logprob Verification:** Inspect token logprobs on relational operators (`BEFORE` vs `AFTER`); items with high operator entropy receive targeted verification calls.
4. **SAT-Guided Conflict Re-Querying:** When inconsistent ($|\Omega|=0$), re-query Granite specifically on the 3–4 lines in the Minimal Unsatisfiable Core rather than re-sampling blind.
