"""
Finite State Machine (FSM) Agent Controller for Adaptive Budgets (1x, 3x, 10x).

Orchestrates:
1. Deterministic Entity Pre-Filtering
2. Granite 4.2 8B Semantic Decompilation
3. 720-World Exhaustive Permutation Solver & MUS Engine
4. Self-Healing & Verification Loops for 3x and 10x budgets.
5. Strict Call Budget Accounting & Rich Telemetry Trace.
"""
import sys
import re
from typing import Dict, Any, List, Optional
from openai import OpenAI
from src.types import ParsedItem
from src.prefilter import prefilter_item
from src.decompiler import (
    decompile_constraints,
    call_granite,
    extract_json_array,
    build_decompiler_prompt,
    BLOCK_TO_IDX
)
from src.solver import solve, Constraint


class FSMController:
    def __init__(self, client: OpenAI, model: str, use_regex_guards: bool = True):
        self.client = client
        self.model = model
        self.use_regex_guards = use_regex_guards
        self.calls_used = 0
        self.max_calls = 1

    def _call_granite_safe(self, item_id: str, prompt: str, temperature: float = 1.0) -> Optional[str]:
        """
        Enforces strict call budget tracking. Every attempt to contact the model
        is counted against calls_used. If calls_used >= max_calls, no request is sent.
        Catches API exceptions gracefully to avoid aborting batch evaluation.
        """
        if self.calls_used >= self.max_calls:
            return None
        self.calls_used += 1
        try:
            return call_granite(self.client, self.model, item_id, prompt, temperature=temperature)
        except Exception as e:
            print(f"[FSM Warning] Call {self.calls_used}/{self.max_calls} on {item_id} encountered API error: {e}", file=sys.stderr)
            return None

    def run_item(self, item_id: str, raw_text: str, budget: str = "1x") -> Dict[str, Any]:
        """Runs the solver pipeline for a single item within the specified call budget."""
        budget_str = budget.lower().strip()
        self.max_calls = 1 if budget_str == "1x" else (3 if budget_str == "3x" else 10)
        self.calls_used = 0

        trace = []

        # Tier 1: Deterministic Pre-Filtering
        parsed = prefilter_item(item_id, raw_text)
        trace.append({
            "step": 1,
            "title": "Tier-1 Entity & Distractor Pre-Filter",
            "calls": 0,
            "description": f"Identified 5 staff members ({', '.join(parsed.header.staff)}) and 3 station holders ({', '.join(parsed.header.station_holders)}). Purged {len(parsed.noise_lines)} noise/gossip lines, isolating {len(parsed.candidate_lines)} candidate constraint lines.",
            "details": {
                "staff": parsed.header.staff,
                "station_holders": parsed.header.station_holders,
                "candidate_count": len(parsed.candidate_lines),
                "noise_count": len(parsed.noise_lines),
                "sample_noise": [t for idx, t in parsed.noise_lines[:3]]
            }
        })

        constraints: List[Constraint] = []

        # Multi-sample consensus if 10x budget
        if self.max_calls >= 10:
            # Step 2: Draw K=5 stochastic samples at temp=1.0 for robust majority consensus
            samples: List[List[Constraint]] = []
            target_samples = min(5, self.max_calls)
            for s_idx in range(target_samples):
                prompt = build_decompiler_prompt(parsed)
                raw = self._call_granite_safe(item_id, prompt, temperature=1.0)
                if raw:
                    c_sample = decompile_constraints(
                        self.client,
                        self.model,
                        parsed,
                        temperature=1.0,
                        use_regex_guards=self.use_regex_guards,
                        raw_output=raw
                    )
                    samples.append(c_sample)

            if samples:
                from collections import Counter
                c_counts = Counter()
                c_map = {}
                for sample in samples:
                    seen = set()
                    for c in sample:
                        key = (c.kind, c.args, c.source_line)
                        if key not in seen:
                            seen.add(key)
                            c_counts[key] += 1
                            c_map[key] = c

                # Majority rule: retain constraints that appeared in >= 2 samples
                consensus_c = [c_map[k] for k, count in c_counts.items() if count >= 2]
                constraints = consensus_c if consensus_c else (samples[0] if samples else [])
            else:
                constraints = []

            trace.append({
                "step": 2,
                "title": f"Multi-Sample Majority Consensus ({len(samples)} passes, Calls: {self.calls_used})",
                "calls": self.calls_used,
                "description": f"Drawn {len(samples)} stochastic extractions at temp=1.0. Majority voting retained {len(constraints)} consensus constraints.",
                "details": {
                    "samples_drawn": len(samples),
                    "consensus_constraints": len(constraints)
                }
            })

        else:
            # 1x or 3x: Single primary decompilation call
            prompt = build_decompiler_prompt(parsed)
            raw = self._call_granite_safe(item_id, prompt, temperature=1.0)
            if raw:
                constraints = decompile_constraints(
                    self.client,
                    self.model,
                    parsed,
                    temperature=1.0,
                    use_regex_guards=self.use_regex_guards,
                    raw_output=raw
                )
            else:
                constraints = []

            extracted_summary = [
                f"{c.kind}({', '.join(str(x) for x in c.args)}) \u2190 '{c.source_line}'"
                for c in constraints
            ]

            guard_desc = "With Syntactic & Negation Guards" if self.use_regex_guards else "Pure Model Output"
            trace.append({
                "step": 2,
                "title": f"Granite 4.2 8B Semantic Decompilation ({guard_desc})",
                "calls": self.calls_used,
                "description": f"Granite 8B decomposed candidate sentences at temp=1.0, yielding {len(constraints)} formal constraints.",
                "details": {
                    "constraints_extracted": extracted_summary
                }
            })

        # Solver Pass #1
        result = solve(parsed.header.staff, parsed.header.station_holders, constraints)
        initial_worlds = result["world_count"]

        trace.append({
            "step": 3,
            "title": "720-World Exhaustive Permutation Solver",
            "calls": self.calls_used,
            "description": f"Evaluated 720 candidate assignments across the permutation state space against {len(constraints)} constraints. Surviving valid worlds: {initial_worlds}.",
            "details": {
                "initial_world_count": initial_worlds,
                "preliminary_case": result["case"],
                "elimination_steps": result.get("elimination_steps", [])
            }
        })

        # Adaptive Loops for 3x and 10x budgets
        if self.max_calls > 1 and self.calls_used < self.max_calls:
            # Loop 1: False Contradiction Audit on 0 worlds
            if result["case"] == "inconsistent" and self.calls_used < self.max_calls:
                conflict_lines = result.get("conflicts", [])
                if conflict_lines:
                    audit_prompt = f"""Staff: {', '.join(parsed.header.staff)}.
The following {len(conflict_lines)} statements caused an impossible schedule contradiction (0 valid worlds):
""" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(conflict_lines)) + """

Re-examine each statement carefully:
1. Is any statement ambient workplace chatter or personal remark rather than a binding schedule rule? (If so, omit it).
2. For any real constraint, verify that polarity/direction was not inverted (e.g. 'without success' is BLOCK_NEQ).

Output a JSON array of corrected constraints for any real rules:
[{"line_idx": 1, "kind": "BLOCK_NEQ", "args": ["..."]}]"""

                    raw = self._call_granite_safe(item_id, audit_prompt)
                    audit_json = extract_json_array(raw) if raw else None

                    if audit_json:
                        c_conflicts = set(conflict_lines)
                        retained_constraints = [c for c in constraints if c.source_line not in c_conflicts]
                        new_constraints = []
                        for entry in audit_json:
                            k = entry.get("kind")
                            a = entry.get("args")
                            l_idx = entry.get("line_idx")
                            if k and a and isinstance(l_idx, int) and 0 <= l_idx - 1 < len(conflict_lines):
                                s_line = conflict_lines[l_idx - 1]
                                if k in ("BLOCK_EQ", "BLOCK_NEQ") and len(a) >= 2 and str(a[1]) in BLOCK_TO_IDX:
                                    new_constraints.append(Constraint(k, (str(a[0]).strip(), BLOCK_TO_IDX[str(a[1])]), s_line))
                                elif k in ("STATION_EQ", "STATION_NEQ", "ORDER_LT", "ORDER_GT", "IMMEDIATE_AFTER", "IMMEDIATE_BEFORE") and len(a) >= 2:
                                    new_constraints.append(Constraint(k, (str(a[0]).strip(), str(a[1]).strip()), s_line))
                                elif k == "BETWEEN" and len(a) >= 3:
                                    new_constraints.append(Constraint(k, (str(a[0]).strip(), str(a[1]).strip(), str(a[2]).strip()), s_line))

                        candidate_constraints = retained_constraints + new_constraints
                        re_result = solve(parsed.header.staff, parsed.header.station_holders, candidate_constraints)
                        if re_result["world_count"] > 0:
                            constraints = candidate_constraints
                            result = re_result
                            trace.append({
                                "step": len(trace) + 1,
                                "title": f"FSM Contradiction Audit (Call #{self.calls_used})",
                                "calls": self.calls_used,
                                "description": f"Audited {len(conflict_lines)} conflicting statements. Rescued item from false contradiction: state space recovered to {result['world_count']} consistent worlds.",
                                "details": {
                                    "rescued_world_count": result["world_count"],
                                    "new_case": result["case"]
                                }
                            })

            # Loop 2: Under-constrained recovery on >1 worlds
            if (result.get("case") == "under_constrained" or result["world_count"] >= 2) and self.calls_used < self.max_calls:
                extracted_lines = {c.source_line for c in constraints}
                unextracted = [t for idx, t in parsed.candidate_lines if t not in extracted_lines]

                if unextracted:
                    initial_w = result["world_count"]
                    repair_prompt = f"""Staff: {', '.join(parsed.header.staff)}.
The initial pass missed some constraints, leaving candidate possibilities ({initial_w} worlds).
Inspect these specific lines and extract ANY schedule or station constraints:
""" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(unextracted))

                    raw = self._call_granite_safe(item_id, repair_prompt)
                    repair_json = extract_json_array(raw) if raw else None

                    newly_added = []
                    if repair_json:
                        def norm_st(val):
                            val_low = str(val).lower()
                            for s in ("intake", "calibration", "packing"):
                                if s in val_low:
                                    return s
                            return val_low

                        for entry in repair_json:
                            k = entry.get("kind")
                            a = entry.get("args")
                            l_idx = entry.get("line_idx")
                            if k and a and isinstance(l_idx, int) and 0 <= l_idx - 1 < len(unextracted):
                                s_line = unextracted[l_idx - 1]
                                if k in ("BLOCK_EQ", "BLOCK_NEQ") and len(a) >= 2 and str(a[1]) in BLOCK_TO_IDX:
                                    c = Constraint(k, (str(a[0]).strip(), BLOCK_TO_IDX[str(a[1])]), s_line)
                                    constraints.append(c)
                                    newly_added.append(f"{k}{c.args} from '{s_line}'")
                                elif k in ("STATION_EQ", "STATION_NEQ") and len(a) >= 2:
                                    c = Constraint(k, (str(a[0]).strip(), norm_st(a[1])), s_line)
                                    constraints.append(c)
                                    newly_added.append(f"{k}{c.args} from '{s_line}'")
                                elif k in ("ORDER_LT", "ORDER_GT", "IMMEDIATE_AFTER", "IMMEDIATE_BEFORE") and len(a) >= 2:
                                    c = Constraint(k, (str(a[0]).strip(), str(a[1]).strip()), s_line)
                                    constraints.append(c)
                                    newly_added.append(f"{k}{c.args} from '{s_line}'")
                                elif k == "BETWEEN" and len(a) >= 3:
                                    c = Constraint(k, (str(a[0]).strip(), str(a[1]).strip(), str(a[2]).strip()), s_line)
                                    constraints.append(c)
                                    newly_added.append(f"{k}{c.args} from '{s_line}'")

                        if newly_added:
                            re_res = solve(parsed.header.staff, parsed.header.station_holders, constraints)
                            if re_res["world_count"] > 0:
                                result = re_res
                                trace.append({
                                    "step": len(trace) + 1,
                                    "title": f"FSM Adaptive Repair Loop (Call #{self.calls_used})",
                                    "calls": self.calls_used,
                                    "description": f"Targeted {len(unextracted)} unextracted lines. Recovered {len(newly_added)} missed constraints, transitioning candidate worlds from {initial_w} to {result['world_count']}.",
                                    "details": {
                                        "newly_recovered": newly_added,
                                        "revised_world_count": result["world_count"]
                                    }
                                })

        # Final decision classification
        raw_case = result["case"]
        valid_w = result.get("valid_worlds", [])

        # If under-constrained (>4 worlds survive), the system honestly declares 'ambiguous'
        # rather than fabricating an arbitrary unique schedule.
        if raw_case == "under_constrained":
            case = "ambiguous"
        else:
            case = raw_case

        explanation = ""
        if case == "unique":
            explanation = "Exactly 1 world out of 720 satisfies all constraints. Emitted the complete 5-person shift roster."
        elif case == "ambiguous":
            explanation = f"Found {result['world_count']} consistent worlds out of 720. Emitted candidate schedules."
        else:
            conflicts = result.get("conflicts", [])
            explanation = f"Found 0 consistent worlds. Extracted the Minimal Unsatisfiable Core (MUS) consisting of {len(conflicts)} mutually contradictory statements."

        trace.append({
            "step": len(trace) + 1,
            "title": f"Final Verdict: {case.upper()}",
            "calls": self.calls_used,
            "description": explanation,
            "details": {
                "case": case,
                "world_count": result["world_count"]
            }
        })

        out = {
            "case": case,
            "telemetry": {
                "budget_requested": budget,
                "calls_used": self.calls_used,
                "max_calls": self.max_calls,
                "world_count": result["world_count"],
                "trace": trace
            }
        }

        if case == "unique":
            if "assignment" in result:
                out["assignment"] = result["assignment"]
            elif valid_w:
                out["assignment"] = valid_w[0].format_assignment()
            else:
                out["assignment"] = {}
        elif case == "ambiguous":
            if "assignments" in result:
                out["assignments"] = result["assignments"]
            elif valid_w:
                out["assignments"] = [w.format_assignment() for w in valid_w[:4]]
            else:
                out["assignments"] = []
        else:
            out["conflicts"] = result.get("conflicts", [])

        return out
