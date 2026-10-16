"""
Finite State Machine (FSM) Agent Controller for Adaptive Budgets (1x, 3x, 10x).

Orchestrates:
1. Deterministic Entity Pre-Filtering
2. Granite 4.2 8B Semantic Decompilation
3. 720-World Symbolic Solver & MUS Engine
4. Self-Healing & Verification Loops for 3x and 10x budgets.
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

        # Tier 1: Deterministic Pre-Filtering
        parsed = prefilter_item(item_id, raw_text)

        # Call 1: Primary Decompilation
        constraints = decompile_constraints(self.client, self.model, parsed)
        calls_used = 1

        # Symbolic Solver Pass
        result = solve(parsed.header.staff, parsed.header.station_holders, constraints)

        # If budget allows and anomalies exist, enter repair loops
        if max_calls > 1 and calls_used < max_calls:
            # Anomaly 1: Under-constrained (too many worlds remaining)
            if result["world_count"] > 4:
                # Identify candidate lines that yielded no extracted constraint
                extracted_lines = {c.source_line for c in constraints}
                unextracted = [t for idx, t in parsed.candidate_lines if t not in extracted_lines]
                
                if unextracted and calls_used < max_calls:
                    repair_prompt = f"""Staff: {', '.join(parsed.header.staff)}.
The initial pass missed some constraints, leaving too many possibilities.
Inspect these specific lines and extract ANY schedule or station constraints:
""" + "\n".join(f"{i+1}. {l}" for i, l in enumerate(unextracted))

                    raw = call_granite(self.client, self.model, item_id, repair_prompt)
                    calls_used += 1
                    
                    repair_json = extract_json_array(raw)
                    if repair_json:
                        # Add newly found constraints
                        # (same mapping as decompiler)
                        from src.decompiler import BLOCK_TO_IDX
                        for entry in repair_json:
                            k = entry.get("kind")
                            a = entry.get("args")
                            l_idx = entry.get("line_idx")
                            if k and a and isinstance(l_idx, int) and 0 <= l_idx - 1 < len(unextracted):
                                s_line = unextracted[l_idx - 1]
                                # Create and append constraint
                                if k in ("BLOCK_EQ", "BLOCK_NEQ") and len(a) >= 2 and str(a[1]) in BLOCK_TO_IDX:
                                    constraints.append(Constraint(k, (str(a[0]).strip(), BLOCK_TO_IDX[str(a[1])]), s_line))
                                elif k in ("STATION_EQ", "STATION_NEQ", "ORDER_LT", "ORDER_GT", "IMMEDIATE_AFTER", "IMMEDIATE_BEFORE") and len(a) >= 2:
                                    constraints.append(Constraint(k, (str(a[0]).strip(), str(a[1]).strip()), s_line))
                                elif k == "BETWEEN" and len(a) >= 3:
                                    constraints.append(Constraint(k, (str(a[0]).strip(), str(a[1]).strip(), str(a[2]).strip()), s_line))

                        # Re-solve
                        result = solve(parsed.header.staff, parsed.header.station_holders, constraints)

            # For 10x budget: additional consistency checks if still under-constrained
            if max_calls >= 10 and result["world_count"] > 4 and calls_used < max_calls:
                # Sample another independent pass to find consensus
                extra_c = decompile_constraints(self.client, self.model, parsed)
                calls_used += 1
                # Union distinct constraints
                existing_descs = {(c.kind, c.args) for c in constraints}
                for ec in extra_c:
                    if (ec.kind, ec.args) not in existing_descs:
                        constraints.append(ec)
                        existing_descs.add((ec.kind, ec.args))
                result = solve(parsed.header.staff, parsed.header.station_holders, constraints)

        # Format clean return payload according to example_answers.json
        case = result["case"]
        if case == "unique":
            return {
                "case": "unique",
                "assignment": result["assignment"]
            }
        elif case == "ambiguous":
            return {
                "case": "ambiguous",
                "assignments": result["assignments"]
            }
        else: # inconsistent
            return {
                "case": "inconsistent",
                "conflicts": result.get("conflicts", [])
            }
