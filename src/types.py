"""
Data types and schemas for the Candidate Package puzzle solver.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any

BLOCKS = ["07:00", "09:00", "11:00", "13:00", "15:00"]
STATIONS = ["intake", "calibration", "packing"]

@dataclass
class ItemHeader:
    bay: str
    staff: List[str]
    blocks: List[str]
    stations: List[str]
    station_holders: List[str]

@dataclass
class ParsedItem:
    item_id: str
    raw_text: str
    header: ItemHeader
    all_lines: List[str]
    candidate_lines: List[Tuple[int, str]] # (1-based line index, line text)
    noise_lines: List[Tuple[int, str]]

def parse_header(text: str) -> ItemHeader:
    """Parses the first line of the shift notes."""
    header_line = text.strip().split("\n")[0]
    
    # Extract bay
    bay = "Bay 4"
    if "Bay " in header_line:
        bay_part = header_line.split("Bay ")[1].split(".")[0]
        bay = f"Bay {bay_part}"

    # Extract staff
    # e.g.: '5 staff on the rota: Samuel, Tomas, Meera, Rohan, Ayesha.'
    staff = []
    if "staff on the rota:" in header_line:
        part = header_line.split("staff on the rota:")[1].split(".")[0].strip()
        staff = [s.strip() for s in part.split(",") if s.strip()]

    # Extract station holders
    # e.g.: 'The people on a station are Samuel, Meera, Ayesha; the rest are on no station.'
    station_holders = []
    if "The people on a station are" in header_line:
        part = header_line.split("The people on a station are")[1].split(";")[0].strip()
        station_holders = [s.strip() for s in part.split(",") if s.strip()]

    return ItemHeader(
        bay=bay,
        staff=staff,
        blocks=BLOCKS,
        stations=STATIONS,
        station_holders=station_holders
    )
