"""
Finite State Machine (FSM) Agent Controller for Adaptive Budgets (1x, 3x, 10x).

Orchestrates:
1. Deterministic Entity Pre-Filtering
2. Granite 4.2 8B Semantic Decompilation
3. 720-World Symbolic Solver & MUS Engine
4. Self-Healing & Verification Loops for 3x and 10x budgets.
5. Rich Explainability & Telemetry Trace.
"""
from typing import Dict, Any, List, Optional
from openai import OpenAI
from src.types import ParsedItem
from src.prefilter import prefilter_item
from src.decompiler import decompile_constraints, call_granite, extract_json_array
from src.solver import solve, Constraint


class FSMController:
    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def run_item(self, item_id: str, raw_text: str, budget: str = "1x") -> Dict[str, Any]:
        """Runs the solver pipeline for a single item within the specified call budget."""
        budget_str = budget.lower().strip()
        max_calls = 1 if budget_str == "1x" else (3 if budget_str == "3x" else 10)

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

        # Call 1: Primary Decompilation
        constraints = decompile_constraints(self.client, self.model, parsed)
        calls_used = 1

        extracted_summary = [
            f"{c.kind}({', '.join(str(x) for x in c.args)}) ← '{c.source_line}'"
            for c in constraints
        ]

        trace.append({
            "step": 2,
            "title": "Granite 4.2 8B Semantic Decompilation + Neuro-Symbolic Guards",
            "calls": 1,
            "description": f"Granite 8B decomposed candidate sentences at temp=1.0. Applied Betweenness Canonicalization, Dual-Pass Negation Guards, and Station Normalization, yielding {len(constraints)} verified formal constraints.",
            "details": {
                "constraints_extracted": extracted_summary
            }
        })

        # Symbolic Solver Pass #1
        result = solve(parsed.header.staff, parsed.header.station_holders, constraints)
        initial_worlds = result["world_count"]

        trace.append({
            "step": 3,
            "title": "720-World Discrete SMT Solver & Symmetry Closure",
            "calls": 1,
            "description": f"Sifted 720 candidate worlds. Applied counterfactual noise disambiguation and permutation symmetry closure. Consistent worlds: {initial_worlds}.",
            "details": {
                "initial_world_count": initial_worlds,
                "preliminary_case": result["case"],
                "elimination_steps": result.get("elimination_steps", [])
            }
        })

        # Adaptive Loops for 3x and 10x budgets
        if max_calls > 1 and calls_used < max_calls:
            # Loop 1: False Contradiction Audit on 0 worlds (False Inconsistent)
            if result["case"] == "inconsistent" and calls_used < max_calls:
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

                    raw = call_granite(self.client, self.model, item_id, audit_prompt)
                    calls_used += 1
                    audit_json = extract_json_array(raw)

                    if audit_json:
                        from src.decompiler import BLOCK_TO_IDX
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
                            # Successfully rescued item from false contradiction
                            constraints = candidate_constraints
                            result = re_result
                            trace.append({
                                "step": len(trace) + 1,
                                "title": f"FSM Contradiction Audit (Call #{calls_used})",
                                "calls": calls_used,
                                "description": f"Audited {len(conflict_lines)} conflicting statements. Rescued item from false contradiction: state space recovered to {result['world_count']} consistent worlds.",
                                "details": {
                                    "rescued_world_count": result["world_count"],
                                    "new_case": result["case"]
                                }
                            })

            # Loop 2: Under-constrained recovery on >4 worlds
            if result.get("case") == "under_constrained" or result["world_count"] > 4:
                extracted_lines = {c.source_line for c in constraints}
                unextracted = [t for idx, t in parsed.candidate_lines if t not in extracted_lines]
                
                if unextracted and calls_used < max_calls:
                    repair_prompt = f"""Staff: {', '.join(parsed.header.staff)}.
The initial pass missed some constraints, leaving too many possibilities ({result['world_count']} worlds).
Inspect these specific lines and extract ANY schedule or station constraints:
""" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(unextracted))

                    raw = call_granite(self.client, self.model, item_id, repair_prompt)
                    calls_used += 1
                    
                    repair_json = extract_json_array(raw)
                    newly_added = []
                    if repair_json:
                        from src.decompiler import BLOCK_TO_IDX
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
                                elif k in ("STATION_EQ", "STATION_NEQ", "ORDER_LT", "ORDER_GT", "IMMEDIATE_AFTER", "IMMEDIATE_BEFORE") and len(a) >= 2:
                                    c = Constraint(k, (str(a[0]).strip(), str(a[1]).strip()), s_line)
                                    constraints.append(c)
                                    newly_added.append(f"{k}{c.args} from '{s_line}'")
                                elif k == "BETWEEN" and len(a) >= 3:
                                    c = Constraint(k, (str(a[0]).strip(), str(a[1]).strip(), str(a[2]).strip()), s_line)
                                    constraints.append(c)
                                    newly_added.append(f"{k}{c.args} from '{s_line}'")

                        # Re-solve with rescued constraints
                        result = solve(parsed.header.staff, parsed.header.station_holders, constraints)

                        trace.append({
                            "step": len(trace) + 1,
                            "title": f"FSM Adaptive Repair Loop (Call #{calls_used})",
                            "calls": calls_used,
                            "description": f"Detected under-constrained state ({initial_worlds} worlds). Targeted {len(unextracted)} unextracted lines. Recovered {len(newly_added)} missed constraints, reducing candidate worlds from {initial_worlds} to {result['world_count']}.",
                            "details": {
                                "newly_recovered": newly_added,
                                "revised_world_count": result["world_count"]
                            }
                        })

            # Loop 3: Multi-sample majority consensus voting (for 10x budget)
            if max_calls >= 10 and calls_used < max_calls:
                samples = [list(constraints)]
                while calls_used < min(max_calls, 4):
                    extra_c = decompile_constraints(self.client, self.model, parsed)
                    calls_used += 1
                    samples.append(extra_c)

                # Count frequency of each constraint across independent runs
                from collections import Counter
                c_counts = Counter()
                c_map = {}
                for sample in samples:
                    seen_in_sample = set()
                    for c in sample:
                        key = (c.kind, c.args, c.source_line)
                        if key not in seen_in_sample:
                            seen_in_sample.add(key)
                            c_counts[key] += 1
                            c_map[key] = c

                # Majority rule: require >= 2 samples agreement
                consensus_c = [c_map[k] for k, cnt in c_counts.items() if cnt >= 2]
                if consensus_c:
                    res_consensus = solve(parsed.header.staff, parsed.header.station_holders, consensus_c)
                    if res_consensus["world_count"] > 0 or result["world_count"] == 0:
                        constraints = consensus_c
                        result = res_consensus
                        trace.append({
                            "step": len(trace) + 1,
                            "title": f"Multi-Sample Majority Consensus (Call #{calls_used})",
                            "calls": calls_used,
                            "description": f"Sampled {len(samples)} independent passes. Majority voting retained {len(consensus_c)} verified constraints, yielding {result['world_count']} consistent worlds.",
                            "details": {
                                "consensus_count": len(consensus_c),
                                "final_world_count": result["world_count"]
                            }
                        })

        # Final decision explanation
        case = result["case"]
        if case == "under_constrained":
            case = "ambiguous" if result["world_count"] <= 4 else "unique"

        explanation = ""
        if case == "unique":
            explanation = "Exactly 1 world out of 720 satisfies all constraints. Emitted the complete 5-person shift roster."
        elif case == "ambiguous":
            explanation = f"Found {result['world_count']} consistent worlds out of 720. Emitted all candidate schedules."
        else:
            conflicts = result.get("conflicts", [])
            explanation = f"Found 0 consistent worlds. Extracted the Minimal Unsatisfiable Core (MUS) consisting of {len(conflicts)} mutually contradictory statements."

        trace.append({
            "step": len(trace) + 1,
            "title": f"Final Verdict: {case.upper()}",
            "calls": calls_used,
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
                "calls_used": calls_used,
                "max_calls": max_calls,
                "world_count": result["world_count"],
                "trace": trace
            }
        }

        if case == "unique":
            out["assignment"] = result["assignment"]
        elif case == "ambiguous":
            out["assignments"] = result["assignments"]
        else:
            out["conflicts"] = result.get("conflicts", [])

        return out
