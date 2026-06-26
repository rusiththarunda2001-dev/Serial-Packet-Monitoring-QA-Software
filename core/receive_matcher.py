"""Match incoming RX data against active receive sequences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.checksum import parse_rule, verify_checksum
from core.sequence_codec import SequenceEncodeError, encode_sequence


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
    """Return receive-sequence hits for one RX frame."""
    matches: List[ReceiveMatch] = []

    for row_index, row in enumerate(receive_rows):
        active, name, sequence, checksum_rule, detect_mode, *_ = normalize_row(row)
        if not _is_active(active):
            continue
        if not sequence.strip():
            continue

        try:
            pattern = encode_sequence(sequence)
        except SequenceEncodeError:
            continue

        rule_id = parse_rule(checksum_rule)
        if rule_id == "off":
            if data == pattern or pattern in data:
                matches.append(
                    ReceiveMatch(
                        name=name,
                        data=data,
                        checksum_ok=None,
                        row_index=row_index,
                    )
                )
            continue

        if not (data.startswith(pattern) and len(data) >= len(pattern) + 1):
            continue

        checksum_ok = verify_checksum(data, checksum_rule)
        if _checksum_accepted(checksum_ok, detect_mode):
            matches.append(
                ReceiveMatch(
                    name=name,
                    data=data,
                    checksum_ok=checksum_ok,
                    row_index=row_index,
                )
            )

    return matches
