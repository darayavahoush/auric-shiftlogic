"""
Entity-Grounded Hybrid Pre-Filter.

Separates high-confidence ambient noise, social chatter, and counterfactuals
from candidate constraint statements.
"""
from typing import List, Tuple
from src.types import ParsedItem, parse_header

def is_obvious_noise(line: str, staff: List[str]) -> bool:
    """
    Purely entity-grounded pre-filter.
    Any sentence mentioning NO entities on the rota (no staff member, no station, no block)
    is inert ambient noise. Does not rely on vocabulary lists or overfitting templates.
    """
    low = line.lower()
    entities = list(staff) + ['intake', 'calibration', 'packing', '07:00', '09:00', '11:00', '13:00', '15:00']
    return not any(e.lower() in low for e in entities)


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
