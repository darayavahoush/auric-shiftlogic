# Architecture Under a Fixed, Weak Model: The ShiftLogic System
**Auric AI Take-Home Submission** | **Target Model:** `ibm-granite/granite-4.2-8b` (`temp=1.0`, `top_p=0.95`, non-thinking)

---

## 1. Characterising the Model Before Designing Around It

Directly prompted (zero- or one-shot) to output complete shift schedules, `ibm-granite/granite-4.2-8b` scored **0.0% macro exact match** across repeated runs on the 60 visible items, collapsing under discrete permutations (for comparison, frontier Claude Sonnet 5 achieved 67.5% in the brief's baseline run).

Granite 4.2 8B is an 8B dense instruct model with sharp capability boundaries:
- **Combinatorial Reasoning (Failure):** The model cannot navigate the $5! \times 3! = 720$ assignment space. It hallucinates duplicate shifts, drops unassigned staff, and cannot verify joint consistency across 20+ lines.
- **Local Semantic Classification (Strength):** Isolated to single sentences, Granite reliably classifies grammatical tense, extracts named entities, and distinguishes operational directives from conversational padding ("chat", "wish", "past rota").
- **Key Extraction Slips:** Directional inversion in passive clauses (*"X is relieved by Y"*), decoy leakage on counterfactual wishes, and surface name typos.

**Design Thesis:** Use Granite exclusively as a semantic compiler from natural language clauses to typed AST constraints (`ON`, `NOT_ON`, `AT`, `NOT_AT`, `BEFORE`, `NEXT`, `BETWEEN`) or skip categories (`chat`, `past`, `wish`, `open`, `unmet`). Outsource all combinatorial deduction and conflict extraction to an exhaustive symbolic solver.

---

## 2. Architecture: Model-Based Extraction vs. Symbolic Solving

**Constraint extraction is strictly model-based; constraint solving is strictly symbolic.**

1. **Deterministic Pre-Filter:** Parses staff, station-holders, and time blocks from the structured header, pruning zero-entity noise lines.
2. **Model-Based Decompiler:** Processes candidate lines in a single prompt. For each line, Granite outputs an echo and verdict (AST constraint or typed skip reason). Uses kNN(3) TF-IDF retrieval for in-context demonstrations and a Levenshtein-1 fuzzy normaliser for staff names.
3. **Symbolic 720-World Solver:** Evaluates the finite state space ($5! \times 3! = 720$) in $<1\text{ ms}$ via vectorised boolean operations:
   - `unique` ($|\Omega| = 1$): Returns the exact valid schedule.
   - `ambiguous` ($2 \le |\Omega| \le 4$): Returns all consistent assignments.
   - `inconsistent` ($|\Omega| = 0$): Computes the Minimal Unsatisfiable Core (MUS) via greedy deletion, isolating the exact conflicting source lines.
4. **Late Voting (3x / 10x):** At higher budgets, $K$ independent model samples are decompiled and solved *independently*. Modal voting occurs on the final structured answer `(case, content)`. Voting at the constraint level was discarded to prevent merging conflicting interpretations into artificial contradictions.

---

## 3. Component Rationale & Empirical Ablation

```
Ablation on items.json (60 items, key visible_key.json, 10 samples banked per item)
1x runs = single samples; 3x runs = disjoint triples; 10x = full 10-sample run
```

| Component Removed / Variant | 1x Macro (runs) | 3x Macro (runs) | 10x Macro (runs) | Description / Finding |
| :--- | :---: | :---: | :---: | :--- |
| **ShiftLogic (Full Production)** | **98.5% ± 0.5** ($n=10$) | **99.4% ± 0.6** ($n=3$) | **100.0%** ($n=1$) | Patched prompt + kNN(3) + fuzzy + voting |
| **Pre-Patch Prompt (`base_prompt`)** | 97.0% ± 0.3 ($n=5$) | 96.7% ($n=1$) | — | Small in-sample gain; no out-of-sample lift shown |
| **Without 0-Call Repair (`no_repair`)** | 97.0% ± 0.5 ($n=10$) | 97.8% ± 0.6 ($n=3$) | 98.3% ($n=1$) | Minor in-sample margin; neutral on blind pools |
| **Without Fuzzy Matcher (`no_fuzzy`)** | 98.5% ± 0.5 ($n=10$) | 99.4% ± 0.6 ($n=3$) | 100.0% ($n=1$) | In-sample names are clean; guards OCR slips |
| **Without Majority Voting (`no_vote`)** | 98.5% ± 0.5 ($n=10$) | 99.4% ± 0.6 ($n=3$) | 98.3% ($n=1$) | 10x without voting drops 1 item (98.3%, $n=1$) |
| **Harness-Less Direct Granite (`direct`)** | **0.0% ± 0.0** ($n=5$) | **0.0%** ($n=1$) | — | Reproduces brief baseline; total permutation collapse |

*Note: Frontier Claude Sonnet 5 scored 67.5% in the brief's baseline, measured under a different direct zero-shot harness.*

**Scaling Curve Observations:**
- **In-Sample Ceiling (Visible):** The visible curve (98.5% $\to$ 99.4% $\to$ 100.0%) exhibits an expected ceiling effect on in-sample phrasing.
- **Formal Held-Out Curve (Pool D):** On 60 blind formal items (`results/ablation_poolD.md`, 10 banked runs), accuracy scales monotonically: **91.7% ± 0.4 (1x) $\to$ 92.2% ± 0.6 (3x) $\to$ 93.3% (10x)**, with voting adding +1.6% at 10x. Disabling repair (`no_repair`) performs higher (93.0% 1x $\to$ 95.0% 10x), confirming repair should be neutralized on held-out text.
- **Colloquial Held-Out Curve (Pool E2):** On 60 blind spoken items (`results/ablation_poolE2.md`, 10 banked runs), accuracy scales steeply: **53.7% ± 1.4 (1x) $\to$ 60.0% ± 1.9 (3x) $\to$ 66.7% (10x)** (+13.0 points). Late voting is decisive here, lifting 10x from 60.0% (`no_vote`) to 66.7% (+6.7 points).
- **Direct Granite Baseline (0.0%):** Direct generation scores 0.0% across all budgets, confirming that performance stems entirely from neuro-symbolic decomposition.

---

## 4. What We Built, Tested, and Removed

- **Iterative Multi-Turn LLM Repair (FSM Controller):** Scored **48.3% (3x)** and **56.7% (10x)** on visible items. Granite entered hallucination loops when prompted with abstract solver contradictions, flipping correct constraints. Discarded for independent sampling + late voting.
- **0-Call Heuristic Constraint Repair:** On blind Pool C and Pool D, flipping flagged constraints produced **0 net item flips (72.92% vs 72.92%)** and lowered 10x accuracy on Pool D (93.3% vs 95.0%). Modifying constraints without textual evidence introduces false consistency. Kept as an inactive fallback.
- **Slot-Form Decompiler (`v3`):** Evaluated in a pre-registered 120-item blind tournament on conversational fragments (Pool E). `v3` scored 43.3% vs `v2_base` 46.7% ($p=0.63$) and `v2_patched` 40.8% ($p=0.73$). None were statistically separable; `v3` failed the pre-registered adoption threshold (+5 net, $p<0.10$) and was discarded.

---

## 5. Where the System Breaks & Multi-Author Generalisation

We evaluated ShiftLogic across independent blind pools to assess resilience against unseen author styles:

| Evaluation Suite | Register / Wording Style | Sample Size | Line Accuracy | Macro Exact Match |
| :--- | :--- | :---: | :---: | :---: |
| **Visible 60 Items** | Formal, templated shifts | 60 | 98.8% | **96.67%** (single) / **100.0%** (10x) |
| **Pool D (Blind)** | Nominalised, formal prose | 60 | 97.8% | **91.7%** (1x) / **93.3%** (10x) |
| **Pool C (Blind)** | Short, active declarative | 120 | 96.0% | **65.00%** (1x) |
| **Pool E (Dev half)** | Spoken hand-over fragments | 60 | 89.8% | **42.22% ± 2.8%** (1x) |
| **Pool E2 (Blind test)**| Spoken hand-over fragments | 60 | 91.5% | **53.7%** (1x) / **66.7%** (10x) |

### Author Variation Reality
Performance is heavily governed by the linguistic register of the author:
- Formal, professional notes (Pool D) achieve **91.7% – 93.3%**.
- Clipped active statements (Pool C) achieve **65.00%**.
- Spoken hand-over fragments (Pools E/E2) score **42% – 54% at 1x**, scaling to **66.7% at 10x** via majority voting.

Because items require ~20 lines parsed with near-perfection, a 1% per-line error rate compounds to a ~15–20% item-level drop. Our central held-out projection across unconstrained styles is **~70% (range: 65% – 88%)**.

---

## 6. One-Month Roadmap (Strictly No Fine-Tuning)

Per the brief's constraints (*"self-hosted, air-gapped, and we do not fine-tune"*), production enhancements must be architectural:

1. **Grammar-Constrained Decoding (CFG Logits Masking):** Enforce an AST grammar at inference time via Outlines/vLLM logits processors, mathematically eliminating syntax and formatting slips (0.0% unparsed).
2. **Dense Multi-Register Retrieval Bank:** Scale the kNN retrieval database from 60 visible items to 2,000+ validated sentences covering colloquial, passive, and spoken registers to ground non-formal phrasing dynamically.
3. **Calibrated Operator Logprob Verification:** Inspect token logprobs on relational operators (`BEFORE` vs `AFTER`). Items with high operator entropy receive targeted verification calls within budget.
4. **SAT-Guided Conflict Re-Querying:** When the solver detects inconsistency ($|\Omega|=0$), re-query Granite specifically on the 3–4 lines isolated in the Minimal Unsatisfiable Core rather than re-sampling blind.
