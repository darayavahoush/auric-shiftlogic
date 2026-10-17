#!/usr/bin/env python3
"""
Comparative Call-Budget Evaluation for ShiftLogic.

Measures accuracy and decision changes across call budget tiers (1x, 3x, 10x)
on a balanced stratified subset of items, logging what each additional call achieves.
"""
import os
import sys
import json
import time
from typing import Dict, Any, List
from dotenv import load_dotenv
from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.fsm_controller import FSMController
from score import score, find_items

load_dotenv(os.path.join(ROOT, ".env"))

def main():
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("MODEL", "ibm-granite/granite-4.2-8b")

    if not api_key:
        sys.exit("Error: OPENROUTER_API_KEY not configured.")

    client = OpenAI(api_key=api_key, base_url=base_url)
    controller = FSMController(client, model)

    all_items = json.load(open(os.path.join(ROOT, "items.json")))
    key = json.load(open(os.path.join(ROOT, "visible_key.json")))

    # Select a balanced stratified set of 12 items (4 unique, 4 ambiguous, 4 inconsistent)
    target_ids = [
        "B2-002", "B2-007", "B2-009", "B2-011",  # Unique
        "B2-001", "B2-003", "B2-006", "B2-014",  # Ambiguous
        "B2-000", "B2-004", "B2-005", "B2-010"   # Inconsistent
    ]
    items = [it for it in all_items if it["id"] in target_ids]
    eval_key = {it["id"]: key[it["id"]] for it in items}

    print("=" * 70)
    print(f"ShiftLogic: Call-Budget Accuracy & Ablation Analysis")
    print(f"Evaluating {len(items)} balanced items (4 unique, 4 ambiguous, 4 inconsistent)")
    print("=" * 70)

    results_by_budget = {}

    for budget in ["1x", "3x"]:
        print(f"\n>>> Running Evaluation under Budget: {budget} <<<")
        answers = {}
        calls_used_list = []
        t0 = time.time()

        for idx, it in enumerate(items, 1):
            iid = it["id"]
            truth = key[iid]["case"]
            res = controller.run_item(iid, it["text"], budget=budget)
            calls = res.get("telemetry", {}).get("calls_used", 1)
            calls_used_list.append(calls)
            worlds = res.get("telemetry", {}).get("world_count", 0)

            entry = {"case": res["case"]}
            if res["case"] == "unique":
                entry["assignment"] = res.get("assignment", {})
            elif res["case"] == "ambiguous":
                entry["assignments"] = res.get("assignments", [])
            else:
                entry["conflicts"] = res.get("conflicts", [])
            answers[iid] = entry

            match_symbol = "✓" if res["case"] == truth else "✗"
            print(f"  [{idx:02d}/{len(items):02d}] {iid}: got={res['case'].upper():<12} "
                  f"truth={truth.upper():<12} [{match_symbol}] | Worlds: {worlds:<3} | Calls: {calls}")

        dur = time.time() - t0
        scores = score(eval_key, answers, items)
        avg_calls = sum(calls_used_list) / len(calls_used_list)
        results_by_budget[budget] = {
            "macro_exact_match": scores["macro_exact_match"],
            "micro_exact_match": scores["exact_match"],
            "per_case_rate": scores.get("per_case_rate", {}),
            "per_case": scores.get("per_case", {}),
            "avg_calls": avg_calls,
            "total_calls": sum(calls_used_list),
            "duration": dur,
            "answers": answers
        }

    print("\n" + "=" * 70)
    print("ACCURACY PER CALL BUDGET SUMMARY")
    print("=" * 70)
    print(f"{'Budget':<8} | {'Avg Calls':<10} | {'Macro Exact':<12} | {'Unique':<10} | {'Ambiguous':<10} | {'Inconsistent':<12}")
    print("-" * 70)
    for b, d in results_by_budget.items():
        cr = d["per_case_rate"]
        u = cr.get("unique", 0) or 0
        a = cr.get("ambiguous", 0) or 0
        i = cr.get("inconsistent", 0) or 0
        print(f"{b:<8} | {d['avg_calls']:<10.2f} | {d['macro_exact_match']:<12.1%} | {u:<10.1%} | {a:<10.1%} | {i:<12.1%}")
    print("=" * 70)

    # Save summary json
    out_path = os.path.join(ROOT, "budget_comparison_results.json")
    with open(out_path, "w") as f:
        json.dump(results_by_budget, f, indent=2, default=str)
    print(f"\nDetailed metrics saved to: {out_path}")

if __name__ == "__main__":
    main()
