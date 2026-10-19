# Dev-only analysis kit (never import from `run`)
- gold_annotate.py   template-bound oracle: maps the visible set's ~65 binding sentence forms to typed constraints.
                     With the plain 720-world solver it scores 100% (60/60) on visible_key.json via score.py.
- gold_constraints.json  per-item gold constraints (line number, text, kind, args) for all 60 visible items.
- sim.py / sim2.py   numpy error-injection simulator on the gold set (per-line error e, decoy leakage d, typed-edit repair).
Paths assume the repo at /home/claude/auric-shiftlogic; edit the two sys.path/ITEMS paths at the top.
Use: compare Granite's per-line output to gold_constraints.json to get real per-line accuracy and an error taxonomy.
