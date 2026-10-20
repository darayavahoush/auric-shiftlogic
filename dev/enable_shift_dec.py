#!/usr/bin/env python3
"""Idempotent: make src/pipeline_v2.py and eval_lines.py pick the decompiler module from SHIFT_DEC (v2 | v2_base | v3).
Safe to run on a repo whose files you have edited; it only replaces the one import line."""
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OLD = "import src.decompiler_v2 as D"
NEW = 'import importlib, os\nD = importlib.import_module("src.decompiler_" + os.environ.get("SHIFT_DEC", "v2"))   # SHIFT_DEC=v3 selects the slot-form decompiler'
for f in ("src/pipeline_v2.py", "eval_lines.py"):
    p = os.path.join(ROOT, f); s = open(p).read()
    if "SHIFT_DEC" in s: print(f, "already switched"); continue
    if OLD not in s: sys.exit(f"{f}: expected line not found: {OLD}")
    open(p, "w").write(s.replace(OLD, NEW, 1)); print(f, "switched")
