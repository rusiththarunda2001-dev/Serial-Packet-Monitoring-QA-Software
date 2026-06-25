"""Checksum compute and verify for serial sequences."""

from __future__ import annotations

from core.checksum_rules import DEFAULT_CHECKSUM


class ChecksumError(ValueError):
    """Raised when a checksum rule cannot be applied."""


CHECKSUM_DESCRIPTIONS = {
    "off": "No checksum is appended to this sequence.",
    "mod256": (
        '"MOD256" checksum from character pos "1st from left" to pos "2nd from right". '
        'Store result at pos "1st from right".'
    ),
    "xor": (
        '"XOR" checksum from character pos "1st from left" to pos "2nd from right". '
        'Store result at pos "1st from right".'
    ),
    "crc_modbus": (
        '"CRC-MODBUS" checksum from character pos "1st from left" to pos "2nd from right". '
        'Store result at pos "1st from right" (lower byte first).'
    ),
    "unsupported": "Checksum rule is not implemented yet.",
}


def parse_rule(rule_text: str) -> str:
    """Map combobox label to internal rule id."""
    text = (rule_text or DEFAULT_CHECKSUM).strip()
    if not text or text.startswith("#"):
        return "off"
    if text.startswith("MOD256"):
        return "mod256"
    if text.startswith("XOR"):
        return "xor"
    if "CRC-MODBUS" in text:
        return "crc_modbus"
    return "unsupported"


def get_checksum_description(rule_text: str) -> str:
    rule_id = parse_rule(rule_text)
    text = CHECKSUM_DESCRIPTIONS.get(rule_id, CHECKSUM_DESCRIPTIONS["unsupported"])
    return "Description: {}".format(text)


def format_bytes_for_preview(data: bytes, mode: str) -> str:
    if not data:
        return ""
    if mode == "HEX":
        return " ".join("{:02X}".format(byte) for byte in data)
    if mode == "Decimal":
        return " ".join(str(byte) for byte in data)
    if mode == "Binary":
        return " ".join("{:08b}".format(byte) for byte in data)
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def build_checksum_preview_text(
    payload: bytes | None,
    rule_text: str,
    display_mode: str = "Decimal",
) -> tuple[str, str]:
    rule_id = parse_rule(rule_text)
    description = get_checksum_description(rule_text)

    if rule_id == "off":
        return "", ""

    if payload is None:
        return "Preview: (invalid sequence)", description

    body = format_bytes_for_preview(payload, display_mode)
    if not body:
        return "Preview: {}", description

    if rule_id == "unsupported":
        return "Preview: {" + body + "} (not available)", description

    try:
        checksum = compute_checksum(payload, rule_text)
    except ChecksumError:
        return "Preview: {" + body + "} (error)", description

    checksum_display = format_bytes_for_preview(checksum, display_mode)
    result = "({})".format(checksum_display)

    return "Preview: {" + body + "} = " + result, description


def checksum_size(rule_id: str) -> int:
    if rule_id == "mod256" or rule_id == "xor":
        return 1
    if rule_id == "crc_modbus":
        return 2
    return 0


def _crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def compute_checksum(payload: bytes, rule_text: str) -> bytes:
    """Return checksum bytes to append after payload."""
    rule_id = parse_rule(rule_text)
    if rule_id == "off":
        return b""
    if rule_id == "unsupported":
        raise ChecksumError("Checksum rule is not implemented yet.")

    if rule_id == "mod256":
        return bytes([sum(payload) % 256])

    if rule_id == "xor":
        value = 0
        for byte in payload:
            value ^= byte
        return bytes([value])

    if rule_id == "crc_modbus":
        crc = _crc16_modbus(payload)
        return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    raise ChecksumError("Unknown checksum rule.")


def append_checksum(payload: bytes, rule_text: str) -> bytes:
    """Return payload with checksum appended (send path)."""
    checksum = compute_checksum(payload, rule_text)
    if not checksum:
        return payload
    return payload + checksum


def verify_checksum(frame: bytes, rule_text: str) -> bool:
    """Return True when trailing checksum in frame is valid."""
    rule_id = parse_rule(rule_text)
    if rule_id == "off":
        return True
    if rule_id == "unsupported":
        return False

    size = checksum_size(rule_id)
    if len(frame) < size + 1:
        return False

    body = frame[:-size]
    expected = compute_checksum(body, rule_text)
    return frame[-size:] == expected
