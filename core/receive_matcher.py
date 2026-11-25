"""Match incoming RX data against active receive sequences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.checksum import parse_rule, verify_checksum
from core.sequence_codec import SequenceEncodeError, compile_receive_pattern


def _find(data: bytes, pattern: list, start: int) -> int:
    """Index of the first match of pattern in data from start, or -1.
    None in the pattern matches any byte (the ? wildcard)."""
    if None not in pattern:
        return data.find(bytes(pattern), start)
    size = len(pattern)
    first_fixed = next(i for i, value in enumerate(pattern) if value is not None) \
        if any(value is not None for value in pattern) else None
    for index in range(start, len(data) - size + 1):
        if first_fixed is not None and data[index + first_fixed] != pattern[first_fixed]:
            continue
        if all(value is None or data[index + offset] == value
               for offset, value in enumerate(pattern)):
            return index
    return -1


@dataclass
class ReceiveMatch:
    name: str
    data: bytes
    checksum_ok: Optional[bool]
    row_index: int


def _is_active(flag: str) -> bool:
    return flag == "☑"


def _checksum_accepted(checksum_ok: bool, detect_mode: str) -> bool:
    if detect_mode == "Detect Checksum OK":
        return checksum_ok
    if detect_mode == "Checksum Wrong":
        return not checksum_ok
    return True


def find_matches(
    data: bytes,
    receive_rows: list,
    normalize_row,
) -> List[ReceiveMatch]:
    """Return receive-sequence hits for one RX frame, matching recursively."""
    matches: List[ReceiveMatch] = []
    if not data:
        return matches

    for row_index, row in enumerate(receive_rows):
        active, name, sequence, checksum_rule, detect_mode, *_ = normalize_row(row)
        if not _is_active(active):
            continue
        if not sequence.strip():
            continue

        try:
            pattern = compile_receive_pattern(sequence)
        except SequenceEncodeError:
            continue

        if not pattern:
            continue

        rule_id = parse_rule(checksum_rule)

        # -----------------------------------------------------------------
        # MODE 1: Checksum is OFF (Find EVERY occurrence inside the buffer)
        # -----------------------------------------------------------------
        if rule_id == "off":
            search_start = 0
            while True:
                # Look for the pattern string anywhere in the remaining buffer
                idx = _find(data, pattern, search_start)
                if idx == -1:
                    break  # No more matches in this buffer

                matches.append(
                    ReceiveMatch(
                        name=name,
                        data=data[idx:idx + len(pattern)],  # the bytes really received
                        checksum_ok=None,
                        row_index=row_index,
                    )
                )
                # Advance search index past this match to find subsequent ones
                search_start = idx + len(pattern)
            continue

        # -----------------------------------------------------------------
        # MODE 2: Checksum is ON (Scan through buffer parsing frame segments)
        # -----------------------------------------------------------------
        search_start = 0
        while search_start < len(data):
            # Look for where the frame header sequence starts
            idx = _find(data, pattern, search_start)
            if idx == -1:
                break

            # Slice the remaining data starting from this pattern detection header
            sub_data = data[idx:]
            if len(sub_data) < len(pattern) + 1:
                break  # Too short to contain a valid checksum payload
            
            # Validate checksum over this individual chunk segment
            checksum_ok = verify_checksum(sub_data, checksum_rule)
            if _checksum_accepted(checksum_ok, detect_mode):
                matches.append(
                    ReceiveMatch(
                        name=name,
                        data=sub_data,
                        checksum_ok=checksum_ok,
                        row_index=row_index,
                    )
                )
            
            # Advance past this frame header sequence to keep scanning for more packets
            search_start = idx + len(pattern)

    return matches