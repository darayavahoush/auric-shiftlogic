"""
decompiler_v2: glossary + many-shot, verdict-on-every-line extraction for Granite 4.2 8B.

Design (all of it is *prompt and parsing*; the model still does the reading):
  * every numbered line gets exactly one verdict -> chatter/old news/wishes/open questions/unmet requests
    must be named ("SKIP:wish"), not silently skipped or silently promoted to a rule;
  * orderings are always written first-person-earlier (BEFORE / NEXT), so the model never has to pick
    between ORDER_LT and ORDER_GT or IMMEDIATE_AFTER and IMMEDIATE_BEFORE;
  * a synonym glossary (word families, not sentences) + ~10 fully labelled visible items as chat turns;
  * the parser VALIDATES (unknown names, bad blocks) but never rewrites a verdict from keywords.

Nothing here inspects the English of a line to decide what it means. The labelled shots are DATA
(src/shots.json, produced offline from the visible items); the rule-based oracle used to produce them is
dev-only and is not imported by ./run.
"""
import json, os, re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.solver import Constraint, BLOCK_TO_IDX
from src.types import ParsedItem

SHOTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots.json")
STATIONS = ("intake", "calibration", "packing")
SKIP_REASONS = ("chat", "past", "wish", "open", "unmet")

SYSTEM_PROMPT = """You read facility shift notes and label EVERY numbered line, one result per line.

SETUP. Five staff each work exactly one block: 07:00, 09:00, 11:00, 13:00, 15:00 (07:00 is earliest, 15:00 latest). Three stations (intake, calibration, packing) are each staffed by one of the listed station holders. Everything below is about TODAY'S roster.

OUTPUT FORMAT, one line per input line, in order, nothing else:
N | <the line copied exactly> => RESULT
RESULT is one constraint, or SKIP:<reason>.

CONSTRAINTS (names exactly as in the staff list; blocks as HH:MM; stations in lower case):
ON(person, HH:MM)        the person works that block
NOT_ON(person, HH:MM)    the person does not work that block
AT(person, station)      the person staffs that station
NOT_AT(person, station)  the person does not staff that station
BEFORE(x, y)             x works earlier in the day than y, any gap. x or y may be a station, meaning "whoever staffs it"
NEXT(x, y)               y works in the block immediately after x, nobody in between
BETWEEN(m, a, b)         m works strictly between a and b; it does not matter which of a, b is earlier

ALWAYS WRITE ORDERINGS WITH THE EARLIER ONE FIRST in BEFORE(first, second) and NEXT(first, second):
- "A is before B" / "A is earlier than B" / "A precedes B" -> BEFORE(A, B)
- "A is after B" / "A is later than B" / "A follows B" -> BEFORE(B, A) (because B is earlier!)
- "A is directly after B" / "A takes over from B" -> NEXT(B, A) (because B is immediately before A!)
- "A is directly before B" -> NEXT(A, B)
PLAIN "after" IS NEVER NEXT. "goes on after", "comes on once Y has finished", "does not start until Y is done", "follows", "starts after" with NO word like directly / immediately / straight / right / next / back to back mean ANY gap: BEFORE(earlier, later). Use NEXT only when the line says the two blocks touch (directly, immediately, straight over, right after, back to back, nobody in between).

WORD FAMILIES (examples of meaning, not an exhaustive list; new wording means the same thing):
- earlier: before, earlier than, ahead of, prior to, precedes, goes on before, is done/finished before X starts, falls somewhere earlier -> BEFORE(this one, that one)
- later: after, later than, follows, comes on after, takes over from, not on until after, starts once Y is done, by the time X starts Y has already been on -> BEFORE(Y, X)
- immediately next: directly/immediately/right after or before, straight over to, back to back, relieves directly, no block in between -> NEXT(first, second)
- between: between, in the middle of, wedged between, \"X and Y bracket M\" (M is the middle one), the middle one of, neither first nor last of, flanked by, after one of them and before the other, in either order, not necessarily adjacent -> BETWEEN
- has a block: takes, draws, opens up at, is scheduled, belongs to, is the one at, "the 11:00 block is X's" -> ON
- not a block: unavailable, rules out, will not find X on, definitely not on, can't do, is not on the block -> NOT_ON
- has a station: covers, is on, assigned to, posted to, stationed at, placed on, in charge of, running, manning, has it this week, "intake is covered by X", "the station is down to X", "intake is X's station" -> AT
- not a station: not on, not assigned to, not put on, rule X out for, covered by someone other than X, not X's station -> NOT_AT

HEDGES AND REPEATS ARE NOT DOUBT. "As far as I know", "I'm fairly sure", "My recollection is that", "Speaking from memory", "Going off the roster", "From what I recall", "If memory serves", "I believe" and the like leave the statement exactly as binding as without them. A line prefixed "It bears repeating:", "Noted twice in the handover:", "Worth restating:" is just the statement itself. Label the statement. A hedge NEVER turns a roster statement into SKIP:wish or SKIP:open: "Unless I have this wrong, Tobias has been posted to intake" is AT(Tobias, intake). SKIP:open needs the line itself to say the matter is undecided.

SKIP REASONS (these are never constraints, however much they mention names, blocks or stations):
SKIP:chat   workplace chatter with no bearing on who works which block or station: gates, keys, surveys, car-sharing, training, drills, walkarounds, recycling, catering, paperwork, who signed or attended something
SKIP:past   how things used to be: old arrangement, last month, previous cycle, in the spring, held for a while, historically, two cycles ago
SKIP:wish   what would have been better, a better fit, if X had / had it gone the other way / would have solved
SKIP:open   unsettled: nobody could remember, disagreement about whether, question left open, came up but nothing minuted, undecided, unconfirmed
SKIP:unmet  unfulfilled requests or preferences: somebody asked, wanted, requested, lobbied, or put in for a block or station and was refused, turned down, declined, did not get it, or it went to someone else. Such lines are NEVER constraints: ALWAYS label them SKIP:unmet.
If a line is a statement of today's roster, label it a constraint. If it is none of the above kinds, SKIP:chat."""


def format_user(staff: List[str], holders: List[str], lines: List[Tuple[int, str]]) -> str:
    body = "\n".join(f"{i}. {t}" for i, t in lines)
    return (f"Staff: {', '.join(staff)}.\nStation holders: {', '.join(holders)} "
            f"(the other staff hold no station).\nLines:\n{body}")


def _fmt_result(row: Dict[str, Any]) -> str:
    k, a = row.get("kind"), row.get("args")
    if not k:
        return f"SKIP:{(row.get('decoy') or 'chat').lower()}"
    if k == "BLOCK_EQ": return f"ON({a[0]}, {a[1]})"
    if k == "BLOCK_NEQ": return f"NOT_ON({a[0]}, {a[1]})"
    if k == "STATION_EQ": return f"AT({a[0]}, {a[1]})"
    if k == "STATION_NEQ": return f"NOT_AT({a[0]}, {a[1]})"
    if k == "ORDER_LT": return f"BEFORE({a[0]}, {a[1]})"
    if k == "ORDER_GT": return f"BEFORE({a[1]}, {a[0]})"
    if k == "IMMEDIATE_BEFORE": return f"NEXT({a[0]}, {a[1]})"
    if k == "IMMEDIATE_AFTER": return f"NEXT({a[1]}, {a[0]})"
    if k == "BETWEEN": return f"BETWEEN({a[0]}, {a[1]}, {a[2]})"
    if k == "ORDER_STATION_PERSON": return f"BEFORE({a[0]}, {a[1]})"
    if k == "ORDER_PERSON_STATION": return f"BEFORE({a[1]}, {a[0]})"
    raise ValueError(k)


def shot_assistant(shot: Dict[str, Any], echo: bool = True) -> str:
    out = []
    for r in shot["lines"]:
        res = _fmt_result(r)
        out.append(f"{r['idx']} | {r['text']} => {res}" if echo else f"{r['idx']} => {res}")
    return "\n".join(out)


def load_shots(path: str = SHOTS_PATH) -> Dict[str, Any]:
    return json.load(open(path)) if os.path.exists(path) else {}


def format_neighbours(rows: List[Dict[str, Any]]) -> str:
    out = ["Labelled examples of similar lines from OTHER notes (different names; same meanings):"]
    for r in rows:
        out.append(f"- {r['text']} => {_fmt_result(r)}")
    return "\n".join(out) + "\n\n"


def build_messages(staff: List[str], holders: List[str], lines: List[Tuple[int, str]],
                   shots: Optional[Dict[str, Any]] = None, echo: bool = True,
                   exclude_ids: Tuple[str, ...] = (), neighbours: Optional[List[Dict[str, Any]]] = None,
                   n_fixed_shots: Optional[int] = None) -> List[Dict[str, str]]:
    shots = load_shots() if shots is None else shots
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    used = 0
    for sid, sh in shots.items():
        if sid in exclude_ids:
            continue
        if n_fixed_shots is not None and used >= n_fixed_shots:
            break
        used += 1
        msgs.append({"role": "user", "content": format_user(sh["staff"], sh["holders"], [(r["idx"], r["text"]) for r in sh["lines"]])})
        msgs.append({"role": "assistant", "content": shot_assistant(sh, echo)})
    pre = format_neighbours(neighbours) if neighbours else ""
    msgs.append({"role": "user", "content": pre + format_user(staff, holders, lines)})
    return msgs


# ----------------------------- parsing -----------------------------
@dataclass
class Verdict:
    idx: int
    status: str                 # "constraint" | "skip" | "invalid" | "missing"
    kind: Optional[str] = None  # repo kind
    args: Optional[tuple] = None
    skip: Optional[str] = None
    raw: str = ""


_CALL = re.compile(r"\b(NOT_ON|NOT_AT|ON|AT|BEFORE|NEXT|BETWEEN)\s*\(([^()]*)\)", re.I)
_SKIP = re.compile(r"SKIP\s*[:\-]?\s*(chat|past|wish|open|unmet)", re.I)
_LEAD = re.compile(r"^\s*(?:line\s*)?(\d+)\s*[|.:)\]-]?\s*(.*)$", re.I)


def _person(tok: str, staff: List[str]) -> Optional[str]:
    t = tok.strip().strip("'\"` ").rstrip(".,;")
    for s in staff:
        if s.lower() == t.lower():
            return s
    hits = [s for s in staff if s.lower().startswith(t.lower())] if len(t) >= 3 else []
    if len(hits) == 1:
        return hits[0]
    if len(t) >= 3:
        def _dist1(a: str, b: str) -> bool:
            if abs(len(a) - len(b)) > 1:
                return False
            if len(a) == len(b):
                return sum(c1 != c2 for c1, c2 in zip(a, b)) == 1
            shorter, longer = (a, b) if len(a) < len(b) else (b, a)
            for i in range(len(longer)):
                if longer[:i] + longer[i+1:] == shorter:
                    return True
            return False
        fuzz = [s for s in staff if _dist1(s.lower(), t.lower())]
        if len(fuzz) == 1:
            return fuzz[0]
    return None


def _station(tok: str) -> Optional[str]:
    t = tok.strip().strip("'\"` ").lower().rstrip(".,;")
    for s in STATIONS:
        if s in t:
            return s
    return None


def _block(tok: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})(?::(\d\d))?", tok)
    if not m:
        return None
    b = f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
    return b if b in BLOCK_TO_IDX else None


def _entity(tok: str, staff: List[str]):
    """person name or station name"""
    p = _person(tok, staff)
    if p:
        return "P", p
    s = _station(tok)
    return ("S", s) if s else (None, None)


def parse_one(idx: int, text: str, staff: List[str], line_text: str) -> Verdict:
    res = text.rsplit("=>", 1)[-1].strip() if "=>" in text else text.strip()
    m = _SKIP.search(res)
    c = _CALL.search(res)
    if c and (not m or c.start() < m.start()):
        fn = c.group(1).upper()
        parts = [p.strip() for p in c.group(2).split(",")]
        try:
            if fn in ("ON", "NOT_ON") and len(parts) == 2:
                p, b = _person(parts[0], staff), _block(parts[1])
                if p and b:
                    return Verdict(idx, "constraint", "BLOCK_EQ" if fn == "ON" else "BLOCK_NEQ", (p, BLOCK_TO_IDX[b]), raw=res)
            elif fn in ("AT", "NOT_AT") and len(parts) == 2:
                p, s = _person(parts[0], staff), _station(parts[1])
                if p and s:
                    return Verdict(idx, "constraint", "STATION_EQ" if fn == "AT" else "STATION_NEQ", (p, s), raw=res)
            elif fn == "BEFORE" and len(parts) == 2:
                (k1, x), (k2, y) = _entity(parts[0], staff), _entity(parts[1], staff)
                if k1 and k2 and x != y:
                    if k1 == "S" and k2 == "P":
                        return Verdict(idx, "constraint", "ORDER_STATION_PERSON", (x, y), raw=res)
                    if k1 == "S" and k2 == "S":
                        pass  # two stations: not expressible, treat invalid
                    else:
                        return Verdict(idx, "constraint", "ORDER_LT", (x, y), raw=res)
            elif fn == "NEXT" and len(parts) == 2:
                (k1, x), (k2, y) = _entity(parts[0], staff), _entity(parts[1], staff)
                if k1 and k2 and x != y:
                    return Verdict(idx, "constraint", "IMMEDIATE_BEFORE", (x, y), raw=res)
            elif fn == "BETWEEN" and len(parts) == 3:
                ps = [_entity(p, staff) for p in parts]
                if all(k for k, _ in ps) and len({v for _, v in ps}) == 3:
                    return Verdict(idx, "constraint", "BETWEEN", tuple(v for _, v in ps), raw=res)
        except Exception:
            pass
        return Verdict(idx, "invalid", raw=res)
    if m:
        return Verdict(idx, "skip", skip=m.group(1).lower(), raw=res)
    return Verdict(idx, "invalid", raw=res)


def parse_verdicts(raw: str, staff: List[str], lines: List[Tuple[int, str]]) -> Dict[int, Verdict]:
    want = {i: t for i, t in lines}
    got: Dict[int, Verdict] = {}
    for row in (raw or "").splitlines():
        m = _LEAD.match(row)
        if not m:
            continue
        idx = int(m.group(1))
        if idx in want:
            v = parse_one(idx, m.group(2), staff, want[idx])
            if v.status in ("constraint", "skip") or idx not in got:
                got[idx] = v
    for i in want:
        got.setdefault(i, Verdict(i, "missing"))
    return got


def verdicts_to_constraints(verdicts: Dict[int, Verdict], lines: List[Tuple[int, str]]) -> List[Constraint]:
    text = dict(lines)
    out, seen = [], set()
    for i in sorted(verdicts):
        v = verdicts[i]
        if v.status == "constraint":
            c = Constraint(kind=v.kind, args=tuple(v.args), source_line=text[i])
            if (c.kind, c.args, c.source_line) not in seen:
                seen.add((c.kind, c.args, c.source_line)); out.append(c)
    return out


# ----------------------------- model call + drop-in -----------------------------
def call_granite_v2(client, model: str, item_id: str, messages: List[Dict[str, str]],
                    temperature: float = 1.0, timeout: float = 300.0) -> str:
    """ONE HTTP request. The client must be built with max_retries=0 so the SDK cannot re-send behind your back."""
    r = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, top_p=0.95, timeout=timeout,
        extra_headers={"X-Item-Id": str(item_id)}, extra_body={"reasoning": {"enabled": False}})
    return r.choices[0].message.content or ""


def decompile_v2(item: ParsedItem, raw_output: str, staff: Optional[List[str]] = None):
    """item.all_lines are the numbered body lines (1-based). Returns (constraints, verdicts)."""
    staff = staff or item.header.staff
    lines = [(i + 1, t) for i, t in enumerate(item.all_lines)]
    verdicts = parse_verdicts(raw_output, staff, lines)
    return verdicts_to_constraints(verdicts, lines), verdicts


_RETRIEVER = {}


def messages_for_item(item: ParsedItem, echo: bool = True, exclude_ids: Tuple[str, ...] = (),
                      knn: int = 0, knn_backend: str = "auto"):
    """knn=0: the fixed 10 shots. knn=K: 3 fixed shots (format) + the K nearest labelled pool lines per line
    (never from the item itself), chosen by embedding similarity. Granite still labels every line."""
    lines = [(i + 1, t) for i, t in enumerate(item.all_lines)]
    if not knn:
        return build_messages(item.header.staff, item.header.station_holders, lines, echo=echo, exclude_ids=exclude_ids)
    from src.knn import Retriever
    R = _RETRIEVER.get(knn_backend) or _RETRIEVER.setdefault(knn_backend, Retriever(knn_backend))
    nb = R.neighbours([t for _, t in lines], k=knn, exclude_item=item.item_id)
    return build_messages(item.header.staff, item.header.station_holders, lines, echo=echo, exclude_ids=exclude_ids,
                          neighbours=nb, n_fixed_shots=3)


def call_granite_v2_lp(client, model: str, item_id: str, messages, temperature: float = 1.0, timeout: float = 300.0):
    """Same ONE request, but asks for token logprobs (if the endpoint supports them).
    Returns (text, [(token, logprob), ...] or None)."""
    r = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, top_p=0.95, timeout=timeout, logprobs=True,
        extra_headers={"X-Item-Id": str(item_id)}, extra_body={"reasoning": {"enabled": False}})
    ch = r.choices[0]
    lp = getattr(ch, "logprobs", None)
    toks = None
    if lp and getattr(lp, "content", None):
        toks = [(t.token, t.logprob) for t in lp.content]
    return ch.message.content or "", toks


def result_confidence(raw: str, toks):
    """{line_idx: mean logprob over the tokens of that line's RESULT (after '=>')}. None if no logprobs."""
    if not toks:
        return None
    spans, pos = [], 0
    for t, lp in toks:
        spans.append((pos, pos + len(t), lp)); pos += len(t)
    if "".join(t for t, _ in toks) != raw:
        return None
    out, off = {}, 0
    for row in raw.splitlines(keepends=True):
        m = _LEAD.match(row)
        if m and "=>" in row:
            a = off + row.rfind("=>") + 2
            b = off + len(row.rstrip("\n"))
            vals = [lp for (s0, s1, lp) in spans if s1 > a and s0 < b]
            if vals:
                out.setdefault(int(m.group(1)), sum(vals) / len(vals))
        off += len(row)
    return out
