"""
Entity-Grounded Hybrid Pre-Filter.

Separates high-confidence ambient noise, social chatter, and counterfactuals
from candidate constraint statements.
"""
from typing import List, Tuple
from src.types import ParsedItem, parse_header

# Universal non-constraint triggers (workplace chitchat, counterfactuals, past assignments, inconclusive notes)
NOISE_TRIGGERS = [
    'interview panel', 'fire-safety', 'supplier training', 'walkaround',
    'emergency contact', 'equipment survey', 'printer', 'cupboard',
    'jacket left', 'visitor log', 'recycling', 'catering is unchanged',
    'car park resurfacing', 'north gate', 'car-share', 'sign-in sheet',
    'parking problem', 'had the rota gone the other way', 'would have been smoother',
    'better fit', 'nobody could remember whether', 'left open in the handover',
    'came up, but nothing was minuted', 'back in the old arrangement',
    'in the spring', 'last month', 'on the previous cycle'
]


def is_obvious_noise(line: str, staff: List[str]) -> bool:
    low = line.lower()
    
    # 1. Rule out sentences mentioning NO entities at all (no staff, no station, no block)
    entities = list(staff) + ['intake', 'calibration', 'packing', '07:00', '09:00', '11:00', '13:00', '15:00']
    has_entity = any(e.lower() in low for e in entities)
    if not has_entity:
        return True

    # 2. Rule out known distractor topics
    if any(t in low for t in NOISE_TRIGGERS):
        return True

    return False


def prefilter_item(item_id: str, raw_text: str) -> ParsedItem:
    """Parses item text into header, candidate lines, and noise lines."""
    header = parse_header(raw_text)
    
    body_lines = [l.strip() for l in raw_text.split('\n')[1:] if l.strip()]
    
    candidate_lines: List[Tuple[int, str]] = []
    noise_lines: List[Tuple[int, str]] = []
    
    for idx, line in enumerate(body_lines, 1):
        if is_obvious_noise(line, header.staff):
            noise_lines.append((idx, line))
        else:
            candidate_lines.append((idx, line))
            
    return ParsedItem(
        item_id=item_id,
        raw_text=raw_text,
        header=header,
        all_lines=body_lines,
        candidate_lines=candidate_lines,
        noise_lines=noise_lines
    )
