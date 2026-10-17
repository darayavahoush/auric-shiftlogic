"""
Granite 4.2 8B Constraint Decompiler.

Transforms natural language shift notes into typed logical constraints.
Includes few-shot exemplars, strict schema enforcement, and robust JSON extraction.
"""
import os
import re
import json
from typing import List, Optional, Tuple, Dict, Any
from openai import OpenAI
from src.types import ParsedItem, BLOCKS
from src.solver import Constraint, BLOCK_TO_IDX

FEW_SHOT_SYSTEM = """You are an expert logic and entity-relation decompiler for workplace shift scheduling.
Given a list of staff, stations, blocks, and candidate lines from facility shift notes, extract all valid schedule and station constraints.

Staff: 5 people.
Blocks: 07:00, 09:00, 11:00, 13:00, 15:00.
Stations: intake, calibration, packing.

Available constraint kinds and argument formats:
- BLOCK_EQ: [person, block] -- e.g. ["Tomas", "11:00"] (includes "opens up at", "takes 11:00", "is scheduled for", "11:00 is Tomas's block", "whoever drew the 11:00 block, it was Tomas")
- BLOCK_NEQ: [person, block] -- e.g. ["Tomas", "11:00"] (includes "rules out the ... block entirely", "11:00 is the one block X is definitely not on", "the 11:00 block is not X's", "you will not find X on the 11:00 block", "lobbied for 11:00 without success", "turned down", "declined", "unavailable at 11:00")
- STATION_EQ: [person, station] -- e.g. ["Tomas", "intake"]
- STATION_NEQ: [person, station] -- e.g. ["Tomas", "intake"] (includes "covered by someone other than", "rule out", "not assigned to")
- ORDER_LT: [p1, p2] -- p1 works earlier in the day than p2 (e.g. "p1 precedes p2", "p1 done before p2 starts", "p1 earlier than p2")
- ORDER_GT: [p1, p2] -- p1 works later in the day than p2 (e.g. "p1 comes later than p2", "p1 after p2")
- IMMEDIATE_AFTER: [p1, p2] -- p1 works directly after p2 (e.g. "p1 relieves p2 directly", "p1 on block directly after p2")
- IMMEDIATE_BEFORE: [p1, p2] -- p1 works directly before p2 (e.g. "p1 then p2, back to back", "p1 hands straight over to p2")
- BETWEEN: [p_mid, p1, p2] -- p_mid works strictly between p1 and p2 (e.g. "Whichever way round p1 and p2 are, p_mid is between them", "p_mid's block falls between p1's and p2's", "p_mid sits between p1 and p2", "p_mid is on after one of p1 and p2 and before the other", "Put p_mid between p1 and p2")
- ORDER_STATION_PERSON: [station, person] -- station covered earlier in the day than person's block (e.g. "The station is covered earlier in the day than person's block", "Whoever has station is done before person starts")
- ORDER_PERSON_STATION: [person, station] -- person works later in the day than whoever has station (e.g. "person is on later than whoever has station")

CRITICAL RULES:
1. "X is on after one of Y and Z and before the other" MUST be parsed as BETWEEN: [X, Y, Z] (do NOT parse as ORDER_LT).
2. Distinguish direction: "p1 precedes p2" or "p1 is done before p2 starts" is ORDER_LT [p1, p2].
3. "p1 is on later than whoever has station" is ORDER_PERSON_STATION [p1, station].
4. "The station is covered earlier than p1" is ORDER_STATION_PERSON [station, p1].
5. Output ONLY a valid JSON list of objects with "line_idx", "kind", "args". No markdown text before or after.
"""

FEW_SHOT_EXAMPLE_PROMPT = """Staff: Samuel, Tomas, Meera, Rohan, Ayesha.
Lines:
1. As far as I know, Tomas lobbied for 11:00 without success.
4. Packing is covered by someone other than Ayesha.
6. Ayesha is not assigned to calibration.
10. Speaking from memory, Meera is on the block directly after Samuel.
12. Put Meera between Tomas and Rohan, though not necessarily next to either.
13. Meera has not been put on packing.
14. Going off the roster, Meera has not been put on intake.
17. Calibration is covered by someone other than Meera.
19. Speaking from memory, you will not find Rohan on the 07:00 block.
20. Going off the roster, Rohan is done before Ayesha starts."""

FEW_SHOT_EXAMPLE_RESPONSE = """[
  {"line_idx": 1, "kind": "BLOCK_NEQ", "args": ["Tomas", "11:00"]},
  {"line_idx": 4, "kind": "STATION_NEQ", "args": ["Ayesha", "packing"]},
  {"line_idx": 6, "kind": "STATION_NEQ", "args": ["Ayesha", "calibration"]},
  {"line_idx": 10, "kind": "IMMEDIATE_AFTER", "args": ["Meera", "Samuel"]},
  {"line_idx": 12, "kind": "BETWEEN", "args": ["Meera", "Tomas", "Rohan"]},
  {"line_idx": 13, "kind": "STATION_NEQ", "args": ["Meera", "packing"]},
  {"line_idx": 14, "kind": "STATION_NEQ", "args": ["Meera", "intake"]},
  {"line_idx": 17, "kind": "STATION_NEQ", "args": ["Meera", "calibration"]},
  {"line_idx": 19, "kind": "BLOCK_NEQ", "args": ["Rohan", "07:00"]},
  {"line_idx": 20, "kind": "ORDER_LT", "args": ["Rohan", "Ayesha"]}
]"""


def build_decompiler_prompt(item: ParsedItem) -> str:
    staff_str = ", ".join(item.header.staff)
    lines_str = "\n".join(f"{idx}. {text}" for idx, text in item.candidate_lines)
    return f"""Staff: {staff_str}.
Lines:
{lines_str}"""


def extract_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    """Robustly extracts JSON array from model output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Regex search for [ ... ]
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass

    return None


def call_granite(client: OpenAI, model: str, item_id: str, prompt: str, temperature: float = 1.0) -> str:
    """Invokes Granite 4.2 8B under the exact competition requirements."""
    messages = [
        {"role": "system", "content": FEW_SHOT_SYSTEM},
        {"role": "user", "content": FEW_SHOT_EXAMPLE_PROMPT},
        {"role": "assistant", "content": FEW_SHOT_EXAMPLE_RESPONSE},
        {"role": "user", "content": prompt}
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=0.95,
        extra_headers={"X-Item-Id": item_id},
        extra_body={"reasoning": {"enabled": False}}
    )
    return response.choices[0].message.content or ""


NEGATION_MARKERS = [
    'without success', 'turned down', 'declined', 'not on', 'will not find',
    'rules out', 'not assigned to', 'other than', 'definitely not', 'refused',
    'unsuccessful', 'was not given', 'not put on', 'has not been put on'
]


def canonicalize_between_line(line: str) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """Deterministically identifies the middle entity and endpoints for any betweenness phrasing."""
    m1 = re.search(r'whichever way round (\w+) and (\w+) are,\s*(\w+) is between them', line, re.IGNORECASE)
    if m1:
        return 'BETWEEN', (m1.group(3), m1.group(1), m1.group(2))

    m2 = re.search(r'put (\w+) between (\w+) and (\w+)', line, re.IGNORECASE)
    if m2:
        return 'BETWEEN', (m2.group(1), m2.group(2), m2.group(3))

    m3 = re.search(r'(\w+)(?:\'s block)? falls between (\w+)(?:\'s)? and (\w+)(?:\'s)?', line, re.IGNORECASE)
    if m3:
        return 'BETWEEN', (m3.group(1), m3.group(2), m3.group(3))

    m4 = re.search(r'(\w+) sits between (\w+) and (\w+)', line, re.IGNORECASE)
    if m4:
        return 'BETWEEN', (m4.group(1), m4.group(2), m4.group(3))

    m5 = re.search(r'(\w+) works at some point between (\w+) and (\w+)', line, re.IGNORECASE)
    if m5:
        return 'BETWEEN', (m5.group(1), m5.group(2), m5.group(3))

    m6 = re.search(r'(\w+) relieves (\w+) directly, with no block in between', line, re.IGNORECASE)
    if m6:
        return 'IMMEDIATE_AFTER', (m6.group(1), m6.group(2))

    m7 = re.search(r'there is no block between (\w+)(?:\'s)? and (\w+)(?:\'s)?, in that order', line, re.IGNORECASE)
    if m7:
        return 'IMMEDIATE_BEFORE', (m7.group(1), m7.group(2))

    return None


def extract_deterministic_negation(line: str, staff: List[str]) -> Optional[Tuple[str, Tuple[Any, ...]]]:
    """Recovers missed negative constraints (BLOCK_NEQ and STATION_NEQ) directly from candidate text."""
    low = line.lower()
    if not any(w in low for w in NEGATION_MARKERS):
        return None

    p_found = None
    for p in staff:
        if re.search(r'\b' + re.escape(p) + r'\b', line, re.IGNORECASE):
            p_found = p
            break
    if not p_found:
        return None

    # Check block
    for b in BLOCKS:
        if b in line:
            return 'BLOCK_NEQ', (p_found, BLOCK_TO_IDX[b])

    # Check station
    for st in ("intake", "calibration", "packing"):
        if st in low:
            return 'STATION_NEQ', (p_found, st)

    return None


def decompile_constraints(
    client: OpenAI,
    model: str,
    item: ParsedItem,
    temperature: float = 1.0
) -> List[Constraint]:
    """Calls Granite 8B and maps parsed JSON back to typed Constraint objects with canonicalization guards."""
    prompt = build_decompiler_prompt(item)
    raw_output = call_granite(client, model, item.item_id, prompt, temperature=temperature)
    parsed = extract_json_array(raw_output)

    # Map candidate line indices
    line_map = {idx: text for idx, text in item.candidate_lines}
    all_line_map = {i + 1: l for i, l in enumerate(item.all_lines)}

    def norm_station(val: Any) -> str:
        val_low = str(val).lower()
        for s in ("intake", "calibration", "packing"):
            if s in val_low:
                return s
        return val_low

    constraints: List[Constraint] = []
    extracted_lines = set()

    if parsed:
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind")
            args = entry.get("args")
            line_idx = entry.get("line_idx")

            if not kind or not args:
                continue

            source_line = line_map.get(line_idx)
            if not source_line:
                source_line = all_line_map.get(line_idx)
            if not source_line and isinstance(line_idx, int) and 0 <= line_idx - 1 < len(item.candidate_lines):
                source_line = item.candidate_lines[line_idx - 1][1]
            if not source_line:
                continue

            # Technique 1: Bi-directional Betweenness Canonicalization Guard
            canon = canonicalize_between_line(source_line)
            if canon:
                kind, canon_args = canon
                args = list(canon_args)

            # Technique 2: Negation Guard against positive misclassification
            s_low = source_line.lower()
            if kind == "BLOCK_EQ" and any(w in s_low for w in NEGATION_MARKERS):
                kind = "BLOCK_NEQ"
            elif kind == "STATION_EQ" and any(w in s_low for w in ('other than', 'not assigned to', 'not on', 'not put on', 'definitely not')):
                kind = "STATION_NEQ"

            # Normalize args
            norm_args = []
            if kind in ("BLOCK_EQ", "BLOCK_NEQ"):
                p = str(args[0]).strip()
                b = str(args[1]).strip()
                if b in BLOCK_TO_IDX:
                    norm_args = (p, BLOCK_TO_IDX[b])
                elif isinstance(args[1], int) and 0 <= args[1] < 5:
                    norm_args = (p, args[1])
                else:
                    continue
            elif kind in ("STATION_EQ", "STATION_NEQ"):
                p = str(args[0]).strip()
                st = norm_station(args[1])
                norm_args = (p, st)
            elif kind in ("ORDER_LT", "ORDER_GT", "IMMEDIATE_AFTER", "IMMEDIATE_BEFORE"):
                p1 = str(args[0]).strip()
                p2 = str(args[1]).strip()
                if any(s in p1.lower() for s in ("intake", "calibration", "packing")):
                    p1 = norm_station(p1)
                if any(s in p2.lower() for s in ("intake", "calibration", "packing")):
                    p2 = norm_station(p2)
                norm_args = (p1, p2)
            elif kind == "BETWEEN":
                p_mid = str(args[0]).strip()
                p1 = str(args[1]).strip()
                p2 = str(args[2]).strip()
                norm_args = (p_mid, p1, p2)
            elif kind == "ORDER_STATION_PERSON":
                st = norm_station(args[0])
                p = str(args[1]).strip()
                norm_args = (st, p)
            elif kind == "ORDER_PERSON_STATION":
                p = str(args[0]).strip()
                st = norm_station(args[1])
                norm_args = (p, st)
            else:
                continue

            c = Constraint(kind=kind, args=tuple(norm_args), source_line=source_line)
            constraints.append(c)
            extracted_lines.add(source_line)

    # Technique 2 (Post-pass): Deterministic Negation & Betweenness Sweep for missed lines
    for idx, cand_line in item.candidate_lines:
        if cand_line not in extracted_lines:
            # Check for betweenness / immediate adjacency
            canon = canonicalize_between_line(cand_line)
            if canon:
                c_kind, c_args = canon
                constraints.append(Constraint(kind=c_kind, args=c_args, source_line=cand_line))
                extracted_lines.add(cand_line)
                continue

            # Check for missed negation
            neg = extract_deterministic_negation(cand_line, item.header.staff)
            if neg:
                n_kind, n_args = neg
                constraints.append(Constraint(kind=n_kind, args=n_args, source_line=cand_line))
                extracted_lines.add(cand_line)

    # Deduplicate constraints
    unique_constraints: List[Constraint] = []
    seen = set()
    for c in constraints:
        key = (c.kind, c.args, c.source_line)
        if key not in seen:
            seen.add(key)
            unique_constraints.append(c)

    return unique_constraints
