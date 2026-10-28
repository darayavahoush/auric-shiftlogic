# ShiftLogic: Complete Engineering Journey, Architecture, & Technical Report
**Project:** Auric AI "ShiftLogic" Benchmark & Take-Home Assessment  
**Author:** Ananya Sridhar  
**Target Model:** `ibm-granite/granite-4.2-8b` (Temperature: `1.0`, Top-P: `0.95`, Reasoning / Thinking: `Disabled`)  
**Production Repository:** `https://github.com/darayavahoush/auric-shiftlogic` (Final Commit: `97f315c`)  
**Document Purpose:** An exhaustive, end-to-end explanation of the problem, the core architectural hypothesis, the engineering iterations, empirical findings, negative results, and production deliverables.

---

## Table of Contents
1. [Executive Summary & Problem Overview](#1-executive-summary--problem-overview)
2. [Anatomy of the Puzzle & Why Naive LLMs Fail](#2-anatomy-of-the-puzzle--why-naive-llms-fail)
3. [The Core Architectural Hypothesis: Neuro-Symbolic Separation](#3-the-core-architectural-hypothesis-neuro-symbolic-separation)
4. [Detailed Pipeline Architecture & Implementation](#4-detailed-pipeline-architecture--implementation)
   - [Stage 1: Deterministic Pre-Filtering](#stage-1-deterministic-pre-filtering)
   - [Stage 2: Model-Based Decompiler (Natural Language to AST)](#stage-2-model-based-decompiler-natural-language-to-ast)
   - [Stage 3: The 720-World Symbolic Solver](#stage-3-the-720-world-symbolic-solver)
   - [Stage 4: Multi-Call Budget Scaling & Late Modal Voting](#stage-4-multi-call-budget-scaling--late-modal-voting)
5. [The Discovery of "Last Verdict Wins" (+8.6% Lift)](#5-the-discovery-of-last-verdict-wins-86-lift)
6. [What We Built, Tested, and Discarded (Negative Results)](#6-what-we-built-tested-and-discarded-negative-results)
   - [The Multi-Turn FSM Repair Failure](#the-multi-turn-fsm-repair-failure)
   - [The 0-Call Heuristic Repair Trap (Overfitting In-Sample)](#the-0-call-heuristic-repair-trap-overfitting-in-sample)
   - [The Slot-Form Decompiler (v3) Blind Tournament](#the-slot-form-decompiler-v3-blind-tournament)
   - [Rule-Based Ellipsis Expansion](#rule-based-ellipsis-expansion)
7. [Multi-Author Generalization & Empirical Benchmark Results](#7-multi-author-generalization--empirical-benchmark-results)
8. [The Compounding Error Law in Text-to-Logic Systems](#8-the-compounding-error-law-in-text-to-logic-systems)
9. [One-Month Roadmap (Strictly No Fine-Tuning)](#9-one-month-roadmap-strictly-no-fine-tuning)
10. [Technical Interview Preparation: Core Trade-Offs & Defense](#10-technical-interview-preparation-core-trade-offs--defense)

---

## 1. Executive Summary & Problem Overview

The **ShiftLogic** benchmark is designed by Auric AI to evaluate whether modern AI engineers can build high-performing, reliable systems on top of **small, fixed, open-weight models** without relying on proprietary mega-models (like GPT-4 or Claude 3.5 Sonnet) or fine-tuning.

### The Challenge
- **Model**: Strictly fixed to `ibm-granite/granite-4.2-8b` (an 8-billion parameter dense instruct model).
- **Environment**: Self-hosted, air-gapped simulation where fine-tuning is prohibited.
- **Budget Limits**: Call budgets are strictly metered per item:
  - **1x Budget**: $\le 1$ model call per puzzle.
  - **3x Budget**: $\le 3$ model calls per puzzle.
  - **10x Budget**: $\le 10$ model calls per puzzle.
- **Protocol Constraints**: Every call must carry an `X-Item-Id` HTTP header, disable internal thinking tokens (`reasoning: {"enabled": False}`), use `max_retries=0` (preventing sneaky re-tries behind the SDK), and run at high entropy (`temperature=1.0`, `top_p=0.95`).
- **Baseline Gap**:
  - Prompted directly without an external harness, **Granite 4.2 8B scores 0.0% macro exact match**.
  - Frontier **Claude Sonnet 5** achieves **67.5%** on the same direct generation prompt.
  - The goal is to close as much of this 67.5% gap as possible purely through software architecture.

### The Final Shipped Results
Through a strict **neuro-symbolic decomposition**, ShiftLogic transformed Granite 4.2 8B from a complete failure into a state-of-the-art solver:
- **Visible 60 Items (Live Entrypoint Run)**:
  - **1x Budget**: **96.67%** (58/60 exact match)
  - **3x Budget**: **98.33%** (59/60 exact match)
  - **10x Budget**: **100.00%** (60/60 exact match)
  - **0 unparsed outputs, 0 fallback states, 0 HTTP failures**.
- **Cross-Register Generalization (Blind Held-Out Sets)**:
  - **Formal Prose (Pool D)**: **93.8% (1x) $	o$ 95.0% (10x)**
  - **Conversational Hand-Over Fragments (Pool E2)**: **61.8% (1x) $	o$ 71.7% (10x)**
  - **Overall realistic held-out projection**: **~70% (range: 65% – 95%)**.

---

## 2. Anatomy of the Puzzle & Why Naive LLMs Fail

### The Puzzle Domain
Each problem instance represents a daily roster handover log for a facility bay. The puzzle defines:
1. **5 Staff Members**: e.g., Daniel, Rohan, Nadia, Priya, Samuel.
2. **5 Chronological Time Blocks**: Strictly disjoint 2-hour slots: `07:00`, `09:00`, `11:00`, `13:00`, `15:00`.
   - Every staff member must be assigned to exactly one time block (a bijection $f: 	ext{Staff} \leftrightarrow 	ext{Time}$).
3. **3 Specific Stations**: `intake`, `calibration`, `packing`.
   - Exactly 3 staff members are assigned to stations (one person per station); the remaining 2 staff members have no station.
4. **Shift Notes Text**: 15–25 lines of raw, human-written shift notes.

### Required Output Cases
The output must classify the puzzle into one of three mutually exclusive categories:
1. `unique`: Exactly one joint assignment of staff to blocks and stations satisfies all constraints. The system must output the complete dictionary mapping every staff member to their time block and station (if applicable).
2. `ambiguous`: Multiple valid schedules satisfy all constraints. The system must output between 2 and 4 complete, distinct valid assignments.
3. `inconsistent`: No valid schedule exists that satisfies all statements simultaneously. The system must identify the **Minimal Unsatisfiable Core (MUS)**—the exact verbatim lines from the text that contradict each other.

### Why Direct LLM Prompting Collapses to 0.0%
When an LLM is prompted to read the shift notes and directly output JSON schedules, Granite 4.2 8B fails 100% of the time because of three fundamental mathematical and cognitive limitations:

1. **The Combinatorial Permutation Space**:
   $$	ext{Total Possible Assignments} = 5! 	imes 3! = 120 	imes 6 = 720 	ext{ possible worlds}$$
   An 8B auto-regressive model cannot simulate a 720-element boolean constraint satisfaction problem in its forward pass. It cannot maintain state across 20 interconnected clauses.
2. **Hallucination of Infeasible States**:
   Granite routinely assigns two people to the same time slot (violating the bijection), assigns four people to three stations, or forgets unassigned staff members.
3. **Inability to Prove Inconsistency**:
   Proving that a puzzle is `inconsistent` requires proving that $orall w \in \Omega, w \models 
eg(igwedge C_i)$. An LLM cannot prove the absence of a solution across 720 permutations; it simply gives up or hallucinates a partial schedule.

---

## 3. The Core Architectural Hypothesis: Neuro-Symbolic Separation

The central breakthrough of ShiftLogic is recognizing what an 8B model is **good at** versus what it is **terrible at**:

```
+-----------------------------------------------------------------------------+
|                          THE NEURO-SYMBOLIC DIVIDE                          |
+------------------------------------+----------------------------------------+
|   WHAT THE LLM DOES (NEURAL)       |   WHAT THE SOLVER DOES (SYMBOLIC)      |
+------------------------------------+----------------------------------------+
| - Local semantic clause extraction | - Combinatorial search (720 worlds)    |
| - Named entity recognition         | - Global consistency verification      |
| - Grammatical tense classification | - Proving inconsistency (empty worlds) |
| - Identifying conversational skips | - Minimal Unsatisfiable Core (MUS)     |
| - Disambiguating phrasing styles   | - Zero hallucinations (exact boolean)  |
+------------------------------------+----------------------------------------+
```

### The Architectural Axiom
> **Constraint extraction is strictly model-based; constraint solving is strictly symbolic.**

Instead of asking Granite to solve the puzzle, we treat Granite as a **semantic decompiler** (or lexical parser). Granite is asked only to evaluate **one sentence at a time** and translate it into a structured, typed Abstract Syntax Tree (AST) constraint or classify it as non-binding conversational noise. 

Once the constraints are compiled, they are passed to a high-speed, deterministic symbolic solver that evaluates all 720 possible permutations in **less than 1 millisecond**.

---

## 4. Detailed Pipeline Architecture & Implementation

The production pipeline (`src/pipeline_v2.py`) consists of four distinct, decoupled stages:

```
                  +-----------------------------------+
                  |         Raw Shift Notes           |
                  +-----------------+-----------------+
                                    |
                                    v
                  +-----------------------------------+
                  |    Stage 1: Pre-Filter            |
                  |  - Parse Staff, Blocks, Stations  |
                  |  - Prune zero-entity noise lines  |
                  +-----------------+-----------------+
                                    |
                                    v
                  +-----------------------------------+
                  |    Stage 2: Model Decompiler      |
                  |  - kNN In-Context Retrieval (k=3) |
                  |  - Line-by-line Echo + Verdict    |
                  |  - Last-Verdict-Wins Parsing      |
                  |  - Levenshtein-1 Fuzzy Normalizer |
                  +-----------------+-----------------+
                                    |
                                    v
                  +-----------------------------------+
                  |    Stage 3: Symbolic Solver       |
                  |  - Vectorized 720-World Search    |
                  |  - Unique / Ambiguous / Conflict  |
                  |  - Greedy MUS Conflict Extraction |
                  +-----------------+-----------------+
                                    |
                  +-----------------+-----------------+
                  | (Budget > 1x: Independent Samples)|
                  v                                   v
+-----------------------------------------------------------------------------+
|                      Stage 4: Late Modal Voting                             |
|  - Independent solves on each sample                                        |
|  - Plurality vote on structured answer (case, assignments/conflicts)        |
+-----------------------------------------------------------------------------+
                                    |
                                    v
                  +-----------------------------------+
                  |        Final answers.json         |
                  +-----------------------------------+
```

### Stage 1: Deterministic Pre-Filtering
Before making any model calls, `src/prefilter.py` parses the structured header of each item:
- Extracts the 5 staff names (e.g., `Daniel`, `Rohan`, `Nadia`, `Priya`, `Samuel`).
- Extracts the stations explicitly declared (e.g., `intake`, `calibration`, `packing`).
- Identifies the ordered list of 5 time blocks (`07:00` through `15:00`).
- Prunes lines containing zero mentions of staff, stations, or relative order tokens (e.g., *"Good morning team, let us have a safe shift today"*), preventing unnecessary token processing.

### Stage 2: Model-Based Decompiler (Natural Language to AST)
The decompiler (`src/decompiler_v2.py`) constructs a prompt where Granite is asked to output a verdict for each candidate line in the format:
`<line_number>: <ECHO_OF_LINE> => <VERDICT>`

#### The Typed AST Constraints
The grammar allows exactly 7 operational constraint types:
1. `ON(person, block)`: Person works on the specified time block (e.g., `ON(Daniel, 09:00)`).
2. `NOT_ON(person, block)`: Person does not work on that block.
3. `AT(person, station)`: Person covers the specified station (e.g., `AT(Rohan, intake)`).
4. `NOT_AT(person, station)`: Person does not cover that station.
5. `BEFORE(entity1, entity2)`: Entity 1 works earlier in the day than Entity 2 (where entities can be people or stations).
6. `NEXT(entity1, entity2)`: Entity 1 works on the block immediately preceding Entity 2.
7. `BETWEEN(entity1, middle, entity2)`: `middle` works between `entity1` and `entity2` (regardless of which comes first).

#### The Skip Categories
Lines that do not represent active, binding shift directives are classified into typed skip reasons:
- `SKIP:chat`: Social pleasantries, weather commentary, or equipment notes.
- `SKIP:past`: Notes about previous shifts or historical rotas (*"Yesterday Priya was on intake"*).
- `SKIP:wish`: Counterfactual desires or unmet requests (*"Samuel hoped he could work packing today, but it was not possible"*).
- `SKIP:open`: Unresolved queries (*"Does anyone know if Daniel is working?"*).
- `SKIP:unmet`: Conditional clauses whose prerequisites failed.

#### In-Context Demonstration Retrieval (kNN with TF-IDF)
Rather than relying on a static set of few-shot examples, ShiftLogic uses a $k$-Nearest Neighbors retriever (`src/knn.py`). For each candidate line, the system computes TF-IDF similarity against a labelled bank of 600+ vetted sentences and dynamically injects the top 3 nearest exemplars into the prompt. This grounds Granite in similar syntactic patterns (e.g., passive phrasing, temporal prepositions) without exceeding token limits.

#### Levenshtein-1 Fuzzy Entity Resolution
Granite occasionally outputs surface misspellings (e.g., `Pryia` instead of `Priya` or `Cormack` instead of `Cormac`). A deterministic post-processor checks every extracted entity against the valid staff roster:
- Exact match $	o$ accepted.
- Unique prefix match (length $\ge 3$) $	o$ resolved.
- Levenshtein distance $\le 1$ with unique nearest neighbor $	o$ resolved.
This completely prevents unparsed entity errors.

### Stage 3: The 720-World Symbolic Solver
The symbolic solver (`src/solver.py`) is the mathematical engine of ShiftLogic:
1. **World Generation**:
   At startup, the solver creates all 720 permutations:
   $$\Omega = \{ (p_1, \dots, p_5) \in 	ext{Permutations}(	ext{Staff}) \} 	imes \{ (s_1, s_2, s_3) \in 	ext{Permutations}(	ext{Stations}) \}$$
2. **Vectorized Boolean Filtering**:
   Each AST constraint is compiled into a boolean mask across the 720 worlds:
   - `ON(P, B)` retains worlds where $w[	ext{person}] == B$.
   - `BEFORE(A, B)` retains worlds where $	ext{block}(A) < 	ext{block}(B)$.
   - `BETWEEN(A, M, B)` retains worlds where $\min(	ext{pos}(A), 	ext{pos}(B)) < 	ext{pos}(M) < \max(	ext{pos}(A), 	ext{pos}(B))$.
3. **Case Determination**:
   - $|\Omega_{	ext{surviving}}| == 1$: Output `unique` with the formatted schedule.
   - $2 \le |\Omega_{	ext{surviving}}| \le 4$: Output `ambiguous` with all surviving schedules.
   - $|\Omega_{	ext{surviving}}| == 0$: Puzzle is `inconsistent`.
4. **Minimal Unsatisfiable Core (MUS) Extraction**:
   When zero worlds survive, the system must cite the exact conflicting statements. It uses a **greedy deletion filter**:
   - Start with the full set of constraints $C = \{c_1, c_2, \dots, c_m\}$.
   - For each constraint $c_i$, test if $C \setminus \{c_i\}$ is still unsatisfiable ($|\Omega| == 0$).
   - If it is still unsatisfiable, $c_i$ is redundant to the contradiction and is removed.
   - The remaining minimal set is the exact unsatisfiable core, and the corresponding verbatim source lines are returned in `conflicts`.

### Stage 4: Multi-Call Budget Scaling & Late Modal Voting
At budgets $3x$ and $10x$, the system queries the model $K$ independent times ($K=3$ or $K=10$) with `temperature=1.0`.

#### Why Late Answer Voting Beats Constraint Voting
In early experiments, we tested voting at the **constraint level** (e.g., if a constraint appeared in $\ge 50\%$ of runs, include it). **This was disastrous**: merging constraints from two different interpretations produced hybrid constraint sets that were mutually contradictory, artificially turning valid puzzles into false `inconsistent` errors.

ShiftLogic implements **Late Modal Voting**:
1. Each of the $K$ model outputs is decompiled and solved **completely independently**.
2. Each run produces a fully formed candidate answer `(case, content)`.
3. The system takes a plurality vote over the structured answer tuple.
4. If a tie occurs between legal and illegal assignments, legal assignments take precedence.
This ensures that every answer considered in the vote was internally consistent and validated by the solver.

---

## 5. The Discovery of "Last Verdict Wins" (+8.6% Lift)

During deep error analysis on conversational and spoken shift notes (Pool E), we uncovered a critical behavioral quirk of Granite 4.2 8B:

### The Phenomenon: "Thinking Aloud" Inside Output Formats
On ambiguous, spoken lines, Granite frequently starts writing a provisional verdict, reasons through the sentence, and then corrects itself a few tokens later:
```
14: Samuel said he might relieve Cormac => NEXT(Cormac, Samuel) OR NEXT(Samuel, Cormac) - wait, this was only a suggestion => SKIP:wish
```
Or:
```
8: Before lunch packing is handled by Cormac => NEXT(packing, Cormac) ... actually packing is a station, so BEFORE(packing, Cormac)
```

### The Bug in the Early Parser
Originally, `parse_verdicts` processed model output line by line and recorded the verdict for line `i` using:
```python
if idx in want and idx not in got:
    got[idx] = parse_one(idx, ...)
```
Because of `idx not in got`, the parser kept the **first** verdict Granite emitted—locking in the unresolved provisional guess and discarding the model's final correction!

### The Fix
We updated `parse_verdicts` so that the **last valid verdict** for each line index wins:
```python
if idx in want:
    v = parse_one(idx, m.group(2), staff, want[idx])
    if v.status in ("constraint", "skip") or idx not in got:
        got[idx] = v
```

### The Empirical Lift
This zero-call, inference-free parser fix produced an immediate, massive leap on held-out spoken text:

| Evaluation Suite | First Verdict Wins (Old) | Last Verdict Wins (Final) | Net Lift |
| :--- | :---: | :---: | :---: |
| **Pool E1 (Dev Half, 1x)** | 42.8% | **50.6%** | **+7.8%** |
| **Pool D (Formal Blind, 1x)** | 93.5% | **93.8%** | **+0.3%** (No harm) |
| **Pool E2 (Spoken Blind, 1x)** | 53.7% ± 1.4 | **61.8% ± 1.4** | **+8.1%** |
| **Pool E2 (Spoken Blind, 3x)** | 60.0% | **68.3%** | **+8.3%** |
| **Pool E2 (Spoken Blind, 10x)**| 66.7% | **71.7%** | **+5.0%** |

---

## 6. What We Built, Tested, and Discarded (Negative Results)

A critical requirement of the Auric brief is documenting what was tried, how it was evaluated, and why it was removed.

### 1. The Multi-Turn FSM Repair Failure
- **Hypothesis**: If the symbolic solver detects an inconsistency ($|\Omega| = 0$), pass the conflicting source lines back to Granite in a multi-turn conversation and ask it to re-evaluate which line it misparsed.
- **Empirical Result**:
  - **1x**: 45.0%
  - **3x**: 48.3%
  - **10x**: 56.7%
- **Root Cause**: Granite lacks meta-reasoning capabilities. When told its constraints contradicted, it panicked, hallucinated non-existent details, or flipped correct constraints into incorrect ones, entering infinite retry loops.
- **Decision**: Completely discarded in favor of independent sampling + late modal voting.

### 2. The 0-Call Heuristic Repair Trap (Overfitting In-Sample)
- **Hypothesis**: Use kNN similarity to flag suspect constraints. If the solver finds zero surviving worlds, search for a single constraint flip that yields a valid unique world.
- **The In-Sample Mirage**:
  - On the 60 visible items, heuristic repair boosted 1x score from 97.8% to **98.8%** and 3x/10x to **100.0%**.
- **The Out-of-Sample Reality Check**:
  - On blind formal text (Pool D), disabling repair **improved** accuracy from 92.8% to **93.8%** at 1x and from 93.3% to **95.0%** at 10x. Removing repair fixed 6 item-runs and broke none ($p = 0.031$).
  - On clean text, heuristic repair was "fixing" true inconsistencies by inventing false valid worlds!
- **Decision**: Disabled by default (`use_repair=False`). Retained only as an opt-in CLI flag (`--repair`).

### 3. The Slot-Form Decompiler (v3) Blind Tournament
- **Hypothesis**: Rather than free-form AST calls, force Granite to emit fixed slot tables (`[LINE] | [TYPE] | [ARG1] | [ARG2]`).
- **Pre-Registered Tournament**: Run a 120-item blind tournament on Pool E comparing `v2_base`, `v2_patched`, and `v3` across 6 runs with a pre-registered adoption threshold (+5 net items, $p < 0.10$).
- **Tournament Result**:
  - `v2_base`: 46.7% [37.5, 55.8]
  - `v2_patched`: 40.8% [32.5, 50.0]
  - `v3`: 43.3% [34.2, 52.5]
  - Paired comparison: `v3` vs `v2_patched` = net +3 items ($p = 0.73$).
- **Decision**: Failed the pre-registered threshold. Discarded to maintain code simplicity.

### 4. Rule-Based Ellipsis Expansion
- **Hypothesis**: In spoken handover notes, staff omit names in follow-up sentences (e.g., *"Daniel takes 09:00. Relieved by Priya."*). Pre-process text with regex to expand ellipses before passing to Granite.
- **Finding**: Hardcoded regex text replacement introduced severe boundary errors on complex sentences, misattributing subjects.
- **Decision**: Rejected. All text interpretation must remain model-based.

---

## 7. Multi-Author Generalization & Empirical Benchmark Results

We benchmarked ShiftLogic across five distinct datasets to test resilience against different human authoring registers:

```
+-----------------------------------------------------------------------------------------------+
|                               MULTI-AUTHOR BENCHMARK SCORECARD                                |
+-----------------------+-----------------------------+-------------+---------------+-----------+
| Dataset Suite         | Register / Author Style     | Sample Size | Line Accuracy | 1x Score  | 10x Score |
+-----------------------+-----------------------------+-------------+---------------+-----------+
| Visible 60 Items      | Templated, formal shifts    | 60 items    | 98.8%         | 96.67%*   | 100.0%*   |
| Pool D (Blind)        | Nominalised, formal prose   | 60 items    | 97.8%         | 93.8%     | 95.0%     |
| Pool C (Blind)        | Clipped active declarative  | 120 items   | 96.0%         | 65.0%     | --        |
| Pool E1 (Dev Half)    | Spoken handover fragments   | 60 items    | 90.2%         | 50.6%     | --        |
| Pool E2 (Blind Test)  | Spoken handover fragments   | 60 items    | 92.4%         | 61.8%     | 71.7%     |
+-----------------------+-----------------------------+-------------+---------------+-----------+
```
*\*Visible scores reflect live entrypoint `./run` executions. Section 3 ablation reports the mean across 10 banked draws (97.8% ± 0.6).*

### Full Production Ablation Table (Visible 60 Items)
Generated via `scripts/run_ablation.py report`:

| Component Removed / Variant | 1x Macro (runs) | 3x Macro (runs) | 10x Macro (runs) | Key Finding |
| :--- | :---: | :---: | :---: | :--- |
| **ShiftLogic (Full Production)** | **97.8% ± 0.6** ($n=10$) | **98.9% ± 0.6** ($n=3$) | **98.3%** ($n=1$) | Shipped default (repair off, kNN=3, fuzzy, voting) |
| **Pre-Patch Prompt (`base_prompt`)** | 97.0% ± 0.3 ($n=5$) | 96.7% ($n=1$) | — | Modest in-sample gain; no out-of-sample lift |
| **Without Fuzzy Matcher (`no_fuzzy`)**| 97.8% ± 0.6 ($n=10$) | 98.9% ± 0.6 ($n=3$) | 98.3% ($n=1$) | In-sample names clean; protects OCR/typos |
| **Without Majority Voting (`no_vote`)**| 97.8% ± 0.6 ($n=10$) | 98.3% ± 1.0 ($n=3$) | 96.7% ($n=1$) | 10x drops from 98.3% to 96.7% without voting |
| **With 0-Call Repair (`with_repair`)**| 98.8% ± 0.4 ($n=10$) | 100.0% ± 0.0 ($n=3$) | 100.0% ($n=1$) | In-sample ceiling; degrades held-out formal ($p=0.031$) |
| **Direct Granite Baseline (`direct`)** | **0.0% ± 0.0** ($n=5$) | **0.0%** ($n=1$) | — | Total combinatorial collapse |

*Frontier Claude Sonnet 5 scored 67.5% in the brief baseline under direct zero-shot prompting.*

---

## 8. The Compounding Error Law in Text-to-Logic Systems

A fundamental insight from this engineering journey is the mathematical relationship between **line-level extraction accuracy** ($p$) and **puzzle-level exact match** ($P_{	ext{item}}$).

Each puzzle contains an average of $L pprox 18$ candidate lines that must all be classified with near-perfection for the solver to derive the correct assignment. If line errors are independent:
$$P_{	ext{item}} pprox p^L$$

```
+--------------------+--------------------------------+
| Line Accuracy (p)  | Expected Item Exact Match (p^18) |
+--------------------+--------------------------------+
|       99.5%        |             91.4%              |
|       98.8% (Vis)  |             80.5% (pre-solver) |
|       97.8% (PoolD)|             66.8% (pre-solver) |
|       96.0% (PoolC)|             47.9%              |
|       92.0% (PoolE)|             22.2%              |
+--------------------+--------------------------------+
```

### Why ShiftLogic Beats the Compounding Law
Notice that ShiftLogic achieves **93.8%** on Pool D (where $p^{18} pprox 66.8\%$) and **61.8%** on Pool E2 (where $p^{18} pprox 22.2\%$). It beats the raw compounding law through three architectural defenses:
1. **Redundancy Tolerance**: Shift notes typically contain 18 lines, but only 7–9 independent constraints are mathematically required to reduce 720 worlds to 1. Missing a redundant constraint does not break the puzzle.
2. **Late Modal Voting**: Sampling $K=10$ times allows the plurality vote to recover items where random noise corrupted a line in a single run.
3. **Exact Solver Pruning**: The symbolic solver cannot hallucinate; it only eliminates worlds strictly disproven by extracted constraints.

---

## 9. One-Month Roadmap (Strictly No Fine-Tuning)

Per the brief's operational constraints (*"self-hosted, air-gapped, and we do not fine-tune"*), all production hardening must be inference-time architectural improvements:

### 1. Grammar-Constrained Decoding (CFG Logits Masking)
- **Mechanism**: Integrate Outlines or vLLM logits processors at inference time. Enforce an exact Context-Free Grammar (CFG) on the token generation layer:
  `LINE -> INT ":" TEXT "=>" (CONSTRAINT | SKIP)`
- **Impact**: Mathematically guarantees well-formed AST outputs and eliminates 100% of formatting or delimiter slips.

### 2. Dense Multi-Register Retrieval Bank (2,000+ Lines)
- **Mechanism**: Expand the in-context demonstration pool from 60 visible items to 2,000+ verified sentences spanning messy colloquial, fragmented, and nominalized styles.
- **Impact**: Dynamically grounds non-formal text (like Pool E) with structurally identical examples, closing the remaining 20% gap on spoken handovers.

### 3. Calibrated Operator Logprob Verification
- **Mechanism**: Inspect token-level log probabilities on relational operators (`BEFORE` vs `AFTER`, `NEXT` vs `BEFORE`).
- **Impact**: When the model emits a verdict with high entropy (low confidence), trigger an isolated verification call for that specific line rather than re-sampling the entire item.

### 4. SAT-Guided Targeted Conflict Re-Querying
- **Mechanism**: When the solver detects an inconsistency ($|\Omega| = 0$), inspect the Minimal Unsatisfiable Core (typically 3–4 lines).
- **Impact**: Instead of re-running all 20 lines at 3x or 10x budget, spend the remaining budget re-querying Granite *specifically* on the 3 lines in the conflict core.

---

## 10. Technical Interview Preparation: Core Trade-Offs & Defense

### Question 1: "Why did you choose late answer voting over voting on extracted constraints?"
> **Defense**: Voting on extracted constraints merges disjoint interpretations into an artificial Frankenstein set. If Run 1 interprets an ambiguous statement as `ON(A, 09:00)` and Run 2 interprets it as `ON(B, 09:00)`, merging both constraints yields an empty world ($|\Omega|=0$), creating an artificial inconsistency. By solving each sample independently and voting only on the completed schedule, we guarantee that every candidate schedule is internally consistent.

### Question 2: "Your 0-call repair got 100% on the visible items. Why on earth did you disable it?"
> **Defense**: Relying on visible items is the classic in-sample trap. When evaluated on blind formal prose (Pool D), removing repair fixed 6 items and broke zero ($p = 0.031$). The heuristic was flipping legitimate constraints to 'force' a solution, manufacturing false consistency on unseen text. In production, scientific integrity means disabling a feature that overfits in-sample while degrading out-of-sample reality.

### Question 3: "Why not use an agent framework like LangChain or LangGraph?"
> **Defense**: Multi-agent loops and agentic frameworks depend on the model having strong meta-reasoning and reflection capabilities. Our empirical testing showed Granite 4.2 8B enters hallucination loops when asked to critique its own logic (scoring under 50% in multi-turn FSM mode). For weak 8B models, strict linear decomposition into single-sentence compilation paired with an external symbolic solver is orders of magnitude more reliable and computationally efficient.

### Question 4: "What is the true expected performance of this system on completely unseen notes?"
> **Defense**: Our blind evaluations show that performance is heavily dependent on author register. On formal or templated notes, ShiftLogic achieves **93%–95%**. On messy, fragmented spoken notes, it achieves **62% at 1x and 72% at 10x**. Across unconstrained real-world facility notes, the realistic central projection is **~70%**.

---
*End of Report.*
