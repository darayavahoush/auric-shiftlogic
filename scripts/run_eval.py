#!/usr/bin/env python3
"""
Official Evaluation Harness for ShiftLogic.

Executes the full neuro-symbolic pipeline against a benchmark dataset,
records item-by-item logs, computes formal scores via score.py,
and updates ui/results.json for the dashboard Scorecard tab.

Usage:
    python3 scripts/run_eval.py --budget 1x --out answers_1x.json
    python3 scripts/run_eval.py --budget 3x --out answers_3x.json
    python3 scripts/run_eval.py --budget 10x --out answers_10x.json
"""
import os
import sys
import json
import time
import argparse
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.fsm_controller import FSMController
from score import score, find_items

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="ShiftLogic Evaluation Harness")
    parser.add_argument("--budget", choices=["1x", "3x", "10x"], default="1x", help="LLM call budget tier")
    parser.add_argument("--items", default=os.path.join(ROOT, "items.json"), help="Path to items.json")
    parser.add_argument("--key", default=os.path.join(ROOT, "visible_key.json"), help="Path to visible_key.json")
    parser.add_argument("--out", default=None, help="Output path for answers JSON")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for fast diagnostic runs")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent worker threads")
    parser.add_argument("--no-guards", action="store_true", help="Disable deterministic syntactic guards for ablation")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("MODEL", "ibm-granite/granite-4.2-8b")

    if not api_key:
        sys.exit("Error: OPENROUTER_API_KEY is not configured in .env. Please add it to run the harness.")

    client = OpenAI(api_key=api_key, base_url=base_url)

    items = json.load(open(args.items, "r", encoding="utf-8"))
    if args.limit:
        items = items[:args.limit]

    out_file = args.out or os.path.join(ROOT, f"answers_{args.budget}.json")

    print("=" * 65)
    print(f"ShiftLogic Eval Harness | Budget: {args.budget} | Model: {model}")
    print(f"Total Items: {len(items)} | Workers: {args.workers} | Destination: {out_file}")
    print(f"Guards: {'Enabled' if not args.no_guards else 'Disabled (Ablation)'}")
    print("=" * 65)

    answers: Dict[str, Any] = {}
    calls_map: Dict[str, int] = {}
    t0 = time.time()

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    lock = threading.Lock()

    def process_single(item):
        item_id = item["id"]
        raw_text = item["text"]
        controller = FSMController(client, model, use_regex_guards=not args.no_guards)
        t_item_0 = time.time()
        try:
            res = controller.run_item(item_id, raw_text, budget=args.budget)
            telemetry = res.get("telemetry", {})
            calls_used = telemetry.get("calls_used", 1)
            entry = {"case": res["case"]}
            if res["case"] == "unique":
                entry["assignment"] = res.get("assignment", {})
            elif res["case"] == "ambiguous":
                entry["assignments"] = res.get("assignments", [])
            else:
                entry["conflicts"] = res.get("conflicts", [])
            worlds = telemetry.get("world_count", 0)
        except Exception as e:
            print(f"[{item_id}] UNEXPECTED ERROR: {e}", file=sys.stderr)
            entry = {"case": "ambiguous", "assignments": []}
            calls_used = 1
            worlds = 720
            res = {"case": "ambiguous"}

        dt = time.time() - t_item_0
        return item_id, entry, calls_used, worlds, dt, res["case"]

    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_single, item): item["id"] for item in items}
        for future in as_completed(futures):
            item_id, entry, calls_used, worlds, dt, case_str = future.result()
            with lock:
                answers[item_id] = entry
                calls_map[item_id] = calls_used
                completed += 1
                # Incremental save
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(answers, f, indent=2)

                print(f"[{completed:02d}/{len(items):02d}] {item_id}: {case_str.upper():<12} "
                      f"| Worlds: {worlds:<4} | Calls: {calls_used} | Latency: {dt:.1f}s")

    total_time = time.time() - t0
    total_calls = sum(calls_map.values())
    print("=" * 65)
    print(f"Finished {len(items)} items in {total_time:.1f}s (Avg: {total_time/len(items):.2f}s/item)")
    print(f"Total API Calls: {total_calls} (Avg: {total_calls/len(items):.2f} calls/item)")
    print("=" * 65)

    # Score if visible key exists
    if os.path.exists(args.key):
        print("\nScoring run against visible key...")
        key = json.load(open(args.key, "r", encoding="utf-8"))
        items_ref = find_items(args.key, args.items)
        scores = score(key, answers, items_ref)

        print(f"  Macro Exact Match: {scores['macro_exact_match']:.1%}")
        print(f"  Micro Exact Match: {scores['exact_match']:.1%}")
        print("  By Case:")
        for k, v in scores.get("per_case", {}).items():
            rate = scores.get("per_case_rate", {}).get(k, 0.0) or 0.0
            print(f"    {k:<12}: {rate:.1%} ({v['correct']}/{v['n']})")

        # Automatically update results.json for UI scorecard
        try:
            import subprocess
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_results.py"), out_file], check=True)
            print("Successfully updated ui/results.json for Dashboard Scorecard.")
        except Exception as e:
            print(f"Notice: Could not update ui/results.json: {e}")


if __name__ == "__main__":
    main()
