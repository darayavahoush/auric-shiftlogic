import os as _os
ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
DEV = _os.path.dirname(_os.path.abspath(__file__))
"""Dev-only oracle: gold per-line labels for the 60 visible items (template-bound; NOT for ./run)."""
import json, re, sys
from templates import build_parser, VISIBLE
parse = build_parser(VISIBLE)
UNMET = re.compile(r"lobbied for|put in for the|wanted \d\d:00 and did not|asked to move to", re.I)
PAST = re.compile(r"in the spring [A-Z]\w+ held|back in the old arrangement|last month|on the previous cycle", re.I)
WISH = re.compile(r"would have been a better fit|had taken the|had the rota gone|would have solved the parking", re.I)
OPEN = re.compile(r"nobody could remember|disagreement about|left open in the handover|came up, but nothing was minuted", re.I)
def dtype(l):
    for n, rx in (("UNMET", UNMET), ("PAST", PAST), ("WISH", WISH), ("OPEN", OPEN)):
        if rx.search(l): return n
    return "CHAT"
items = json.load(open(ROOT + "/items.json")); out = {}
for it in items:
    head, body = it["text"].split("\n\n", 1)
    staff = re.search(r"rota: ([^.]*)\.", head).group(1).split(", ")
    holders = re.search(r"station are ([^;]*);", head).group(1).split(", ")
    rows = []
    for j, l in enumerate(body.split("\n")):
        p = parse(l)
        rows.append({"idx": j + 1, "text": l, "kind": p[0] if p else None, "args": list(p[1]) if p else None,
                     "decoy": None if p else dtype(l)})
    out[it["id"]] = {"staff": staff, "holders": holders, "lines": rows}
json.dump(out, open(sys.argv[1], "w"), indent=1)
import collections
print(collections.Counter(r["decoy"] for v in out.values() for r in v["lines"]))
print(collections.Counter(r["kind"] for v in out.values() for r in v["lines"]))
