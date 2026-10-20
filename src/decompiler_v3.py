"""
decompiler_v3: slot-form extraction. Same job as decompiler_v2 (Granite labels every line, one call per item),
different OUTPUT FORM. Instead of positional predicates (BEFORE(x, y) with an argument-order convention) the model
fills a small named-slot form per line:

    N | <line copied> => ON person=X block=HH:MM neg=no|yes
    N | <line copied> => AT person=X station=S neg=no|yes
    N | <line copied> => ORDER first=<earlier> second=<later> gap=any|none
    N | <line copied> => BETWEEN middle=M ends=A,B
    N | <line copied> => SKIP:chat|past|wish|open|unmet

Why: the decisions the model got wrong in v2 (who is earlier; which one is in the middle; is it NEXT or just BEFORE)
become separate, explicitly named slots (first=, middle=, gap=) instead of argument positions it has to remember.
Python maps slots to the repo's constraint kinds deterministically. Nothing here reads the English of a line.

Drop-in for src.decompiler_v2: same public names (SYSTEM_PROMPT, messages_for_item, call_granite_v2, decompile_v2,
parse_verdicts, shot_assistant, Verdict ...). Select with SHIFT_DEC=v3.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from src.solver import Constraint, BLOCK_TO_IDX
from src.types import ParsedItem
import src.decompiler_v2 as _V2
from src.decompiler_v2 import (  # shared plumbing, unchanged
    Verdict, format_user, load_shots, _person, _station, _block, _entity, _LEAD, verdicts_to_constraints,
    call_granite_v2, call_granite_v2_lp, result_confidence, STATIONS, SKIP_REASONS)

SYSTEM_PROMPT = """You read facility shift notes and fill in a short form for EVERY numbered line, one form per line.

SETUP. Five staff each work exactly one block: 07:00, 09:00, 11:00, 13:00, 15:00 (07:00 is earliest, 15:00 latest). Three stations (intake, calibration, packing) are each staffed by one of the listed station holders. Everything below is about TODAY'S roster.

OUTPUT, one line per input line, in order, nothing else:
N | <the line copied exactly> => FORM
FORM is exactly one of:
ON person=<name> block=<HH:MM> neg=<no|yes>
AT person=<name> station=<intake|calibration|packing> neg=<no|yes>
ORDER first=<name or station> second=<name or station> gap=<any|none>
BETWEEN middle=<name> ends=<name>,<name>
SKIP:<chat|past|wish|open|unmet>
Names exactly as in the staff list; blocks as HH:MM; stations in lower case.

HOW TO FILL IT IN. For every line ask these questions in order.
1. Is the line a plain statement about who is on what TODAY? If it is only chatter, an old arrangement, what somebody wants or thinks should happen, something undecided, or a request that did not succeed, it is a SKIP (reasons below). A hedge at the start ("As far as I know", "I believe", "If memory serves") or a repeat prefix ("Worth restating:") does not make a statement doubtful: fill in the form for the statement itself.
2. What kind of fact is it? A block (ON), a station (AT), an earlier/later relation (ORDER), or one person in the middle of two others (BETWEEN).
3. ON and AT: neg=yes when the line says the person is NOT on that block or station, otherwise neg=no.
4. ORDER: decide who works FIRST in the day. first= is always the earlier one, whichever name the sentence mentions first and whatever its grammatical subject. second= is the later one. A line about a hand-over, with one person coming on as another goes off, has the one going off as first. A station name stands for whoever staffs it. gap=none ONLY when the line says the two blocks touch (directly, immediately, straight over, right after, back to back, nobody in between); every other ordering line, including a plain "after", is gap=any.
5. BETWEEN: middle= is the one in the middle of the other two; ends= are those two, either order.

WORD FAMILIES (examples of meaning, not an exhaustive list; new wording means the same thing):
- earlier / later (ORDER): before, earlier than, ahead of, prior to, precedes, goes on before, is done before X starts -> first is that one; after, later than, follows, comes on after, starts once Y is done, takes over from, not on until after -> first is the other one
- touching (gap=none): directly/immediately/right after or before, straight over to, back to back, relieves directly, no block in between
- in the middle (BETWEEN): between, in the middle of, wedged between, "X and Y bracket M" (M is in the middle), the middle one of, neither first nor last of, flanked by, after one of them and before the other, in either order
- has a block (ON, neg=no): takes, draws, opens up at, is scheduled, belongs to, is the one at, "the 11:00 block is X's"
- not a block (ON, neg=yes): unavailable, rules out, will not find X on, definitely not on, can't do
- has a station (AT, neg=no): covers, is on, assigned to, posted to, stationed at, placed on, in charge of, running, manning, "intake is covered by X", "intake is X's station"
- not a station (AT, neg=yes): not on, not assigned to, not put on, rule X out for, covered by someone other than X

SKIP REASONS (never constraints, however much they mention names, blocks or stations):
SKIP:chat   workplace chatter with no bearing on who works which block or station: gates, keys, surveys, car-sharing, training, drills, recycling, catering, paperwork, who signed or attended something
SKIP:past   how things used to be: old arrangement, last month, previous cycle, historically
SKIP:wish   what would have been better, a better fit, if X had / had it gone the other way; also opinions about who should or ought to be somewhere: what somebody thinks is best, not what is scheduled
SKIP:open   unsettled: nobody could remember, disagreement about whether, question left open, undecided, unconfirmed
SKIP:unmet  somebody asked, wanted, requested or put in for a block or station and did not end up with it, however the outcome is worded or only implied. The line reports what they wanted, not what the roster says.
If a line is a statement of today's roster, fill in a form. If it is none of the above kinds, SKIP:chat."""


# ----------------------------- formatting -----------------------------
def fmt_form(row: Dict[str, Any]) -> str:
    k, a = row.get("kind"), row.get("args")
    if not k:
        return f"SKIP:{(row.get('decoy') or 'chat').lower()}"
    if k in ("BLOCK_EQ", "BLOCK_NEQ"): return f"ON person={a[0]} block={a[1]} neg={'yes' if k == 'BLOCK_NEQ' else 'no'}"
    if k in ("STATION_EQ", "STATION_NEQ"): return f"AT person={a[0]} station={a[1]} neg={'yes' if k == 'STATION_NEQ' else 'no'}"
    if k == "ORDER_LT": return f"ORDER first={a[0]} second={a[1]} gap=any"
    if k == "ORDER_GT": return f"ORDER first={a[1]} second={a[0]} gap=any"
    if k == "IMMEDIATE_BEFORE": return f"ORDER first={a[0]} second={a[1]} gap=none"
    if k == "IMMEDIATE_AFTER": return f"ORDER first={a[1]} second={a[0]} gap=none"
    if k == "BETWEEN": return f"BETWEEN middle={a[0]} ends={a[1]},{a[2]}"
    if k == "ORDER_STATION_PERSON": return f"ORDER first={a[0]} second={a[1]} gap=any"
    if k == "ORDER_PERSON_STATION": return f"ORDER first={a[1]} second={a[0]} gap=any"
    raise ValueError(k)


def shot_assistant(shot: Dict[str, Any], echo: bool = True) -> str:
    return "\n".join((f"{r['idx']} | {r['text']} => {fmt_form(r)}" if echo else f"{r['idx']} => {fmt_form(r)}") for r in shot["lines"])


def format_neighbours(rows: List[Dict[str, Any]]) -> str:
    out = ["Labelled examples of similar lines from OTHER notes (different names; same meanings):"]
    out += [f"- {r['text']} => {fmt_form(r)}" for r in rows]
    return "\n".join(out) + "\n\n"


def build_messages(staff, holders, lines, shots=None, echo=True, exclude_ids=(), neighbours=None, n_fixed_shots=None):
    shots = load_shots() if shots is None else shots
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    used = 0
    for sid, sh in shots.items():
        if sid in exclude_ids: continue
        if n_fixed_shots is not None and used >= n_fixed_shots: break
        used += 1
        msgs.append({"role": "user", "content": format_user(sh["staff"], sh["holders"], [(r["idx"], r["text"]) for r in sh["lines"]])})
        msgs.append({"role": "assistant", "content": shot_assistant(sh, echo)})
    pre = format_neighbours(neighbours) if neighbours else ""
    msgs.append({"role": "user", "content": pre + format_user(staff, holders, lines)})
    return msgs


_RETRIEVER = _V2._RETRIEVER   # one shared retriever cache


def messages_for_item(item: ParsedItem, echo: bool = True, exclude_ids: Tuple[str, ...] = (), knn: int = 0, knn_backend: str = "auto"):
    lines = [(i + 1, t) for i, t in enumerate(item.all_lines)]
    if not knn:
        return build_messages(item.header.staff, item.header.station_holders, lines, echo=echo, exclude_ids=exclude_ids)
    from src.knn import Retriever
    R = _RETRIEVER.get(knn_backend) or _RETRIEVER.setdefault(knn_backend, Retriever(knn_backend))
    nb = R.neighbours([t for _, t in lines], k=knn, exclude_item=item.item_id)
    return build_messages(item.header.staff, item.header.station_holders, lines, echo=echo, exclude_ids=exclude_ids,
                          neighbours=nb, n_fixed_shots=3)


# ----------------------------- parsing -----------------------------
_FORM = re.compile(r"^\s*(ON|AT|ORDER|BETWEEN)\b(.*)$", re.I | re.S)
_SKIP = re.compile(r"SKIP\s*[:\-]?\s*(chat|past|wish|open|unmet)", re.I)
_KV = re.compile(r"(\w+)\s*=\s*(.*?)(?=\s+\w+\s*=|\s*$)", re.S)
_YES = {"yes", "y", "true", "1"}
_NO = {"no", "n", "false", "0"}


def _slots(rest: str) -> Dict[str, str]:
    return {k.lower(): v.strip().strip("'\"`").rstrip(".;") for k, v in _KV.findall(rest)}


def parse_one(idx: int, text: str, staff: List[str], line_text: str) -> Verdict:
    res = text.rsplit("=>", 1)[-1].strip() if "=>" in text else text.strip()
    m = _FORM.match(res)
    sk = _SKIP.search(res)
    if m and (not sk or m.start() <= sk.start()):
        fn, kv = m.group(1).upper(), _slots(m.group(2))
        try:
            if fn in ("ON", "AT"):
                neg = kv.get("neg", "no").lower()
                if neg in _YES or neg in _NO:
                    neg = neg in _YES
                    p = _person(kv.get("person", ""), staff)
                    if fn == "ON":
                        b = _block(kv.get("block", ""))
                        if p and b: return Verdict(idx, "constraint", "BLOCK_NEQ" if neg else "BLOCK_EQ", (p, BLOCK_TO_IDX[b]), raw=res)
                    else:
                        s = _station(kv.get("station", ""))
                        if p and s: return Verdict(idx, "constraint", "STATION_NEQ" if neg else "STATION_EQ", (p, s), raw=res)
            elif fn == "ORDER":
                (k1, x), (k2, y) = _entity(kv.get("first", ""), staff), _entity(kv.get("second", ""), staff)
                gap = kv.get("gap", "any").lower()
                if k1 and k2 and x != y and gap in ("any", "none"):
                    if gap == "none":
                        if k1 == "P" and k2 == "P": return Verdict(idx, "constraint", "IMMEDIATE_BEFORE", (x, y), raw=res)
                    elif k1 == "S" and k2 == "P": return Verdict(idx, "constraint", "ORDER_STATION_PERSON", (x, y), raw=res)
                    elif k1 == "P" and k2 == "P": return Verdict(idx, "constraint", "ORDER_LT", (x, y), raw=res)
            elif fn == "BETWEEN":
                mid = _person(kv.get("middle", ""), staff)
                ends = [e for e in re.split(r"\s*(?:,|/|\band\b|&)\s*", kv.get("ends", "")) if e.strip()]
                if mid and len(ends) == 2:
                    a, b = _person(ends[0], staff), _person(ends[1], staff)
                    if a and b and len({mid, a, b}) == 3: return Verdict(idx, "constraint", "BETWEEN", (mid, a, b), raw=res)
        except Exception:
            pass
        return Verdict(idx, "invalid", raw=res)
    if sk:
        return Verdict(idx, "skip", skip=sk.group(1).lower(), raw=res)
    return Verdict(idx, "invalid", raw=res)


def parse_verdicts(raw: str, staff: List[str], lines: List[Tuple[int, str]]) -> Dict[int, Verdict]:
    want = {i: t for i, t in lines}
    got: Dict[int, Verdict] = {}
    for row in (raw or "").splitlines():
        m = _LEAD.match(row)
        if not m: continue
        idx = int(m.group(1))
        if idx in want and idx not in got:
            got[idx] = parse_one(idx, m.group(2), staff, want[idx])
    for i in want: got.setdefault(i, Verdict(i, "missing"))
    return got


def decompile_v2(item: ParsedItem, raw_output: str, staff: Optional[List[str]] = None):
    staff = staff or item.header.staff
    lines = [(i + 1, t) for i, t in enumerate(item.all_lines)]
    verdicts = parse_verdicts(raw_output, staff, lines)
    return verdicts_to_constraints(verdicts, lines), verdicts
