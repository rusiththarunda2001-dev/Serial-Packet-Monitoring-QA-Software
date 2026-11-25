"""Checksum compute and verify for serial sequences.

A checksum setting is a specification text, like in Docklight, followed by an
optional comment after "#":

    MOD256 | MOD65536 | XOR | LRC (or -MOD256) | LRC-ASCII
    CRC-7 | CRC-8 | CRC-DOW | CRC-CCITT | CRC-XMODEM | CRC-16 | CRC-MODBUS | CRC-32
    CRC:width,polynomial,init,finalXOR,reflectIn,reflectOut   (your own CRC;
        values in HEX, reflect = Yes/No), e.g. CRC:16,8005,FFFF,0000,Yes,Yes

Add " L" to put a multi-byte result low byte first (e.g. "CRC-MODBUS L");
otherwise the high byte comes first.

The checksum is calculated over all bytes of the sequence and added at the end.
Only LRC-ASCII (MODBUS ASCII) is put before a final CR LF, and it ignores a
leading ":" (the frame is ":" + HEX text + LRC + CR LF).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.checksum_rules import DEFAULT_CHECKSUM


class ChecksumError(ValueError):
    """Raised when a checksum rule cannot be applied."""


@dataclass(frozen=True)
class CrcParams:
    width: int
    poly: int
    init: int
    xorout: int
    refin: bool
    refout: bool


# Standard parameters; each gives the listed value for the ASCII text "123456789".
PREDEFINED_CRCS = {
    "CRC-7": CrcParams(7, 0x09, 0x00, 0x00, False, False),              # 75
    "CRC-8": CrcParams(8, 0x07, 0x00, 0x00, False, False),              # F4
    "CRC-DOW": CrcParams(8, 0x31, 0x00, 0x00, True, True),              # A1
    "CRC-CCITT": CrcParams(16, 0x1021, 0xFFFF, 0x0000, False, False),   # 29B1
    "CRC-XMODEM": CrcParams(16, 0x1021, 0x0000, 0x0000, False, False),  # 31C3
    "CRC-16": CrcParams(16, 0x8005, 0x0000, 0x0000, True, True),        # BB3D
    "CRC-MODBUS": CrcParams(16, 0x8005, 0xFFFF, 0x0000, True, True),    # 4B37
    "CRC-32": CrcParams(32, 0x04C11DB7, 0xFFFFFFFF, 0xFFFFFFFF, True, True),  # CBF43926
}

SUM_RULES = {
    # name: size in bytes
    "MOD256": 1,
    "MOD65536": 2,
    "XOR": 1,
    "LRC": 1,
    "-MOD256": 1,
    "LRC-ASCII": 2,
}

CUSTOM_CRC_PATTERN = re.compile(r"^CRC:\s*(.+)$", re.IGNORECASE)
YES = ("yes", "y", "true", "1")
NO = ("no", "n", "false", "0")


@dataclass(frozen=True)
class ChecksumSpec:
    name: str                  # e.g. "CRC-MODBUS", "MOD256", "CRC:16,1021,..."
    size: int                  # bytes added to the sequence
    little_endian: bool = False
    crc: CrcParams | None = None

    @property
    def before_line_end(self):
        """LRC-ASCII goes before a final CR / LF instead of at the very end."""
        return self.name == "LRC-ASCII"


# ----------------------------------------------------------------------
# Reading the specification text
# ----------------------------------------------------------------------

def _spec_text(rule_text):
    text = (rule_text or DEFAULT_CHECKSUM).strip()
    return text.split("#", 1)[0].strip()


def _parse_custom_crc(body):
    parts = [part.strip() for part in body.split(",")]
    if len(parts) != 6:
        raise ChecksumError(
            "A custom CRC needs 6 values: CRC:width,polynomial,init,finalXOR,reflectIn,"
            "reflectOut, e.g. CRC:16,8005,FFFF,0000,Yes,Yes")
    try:
        width = int(parts[0])
    except ValueError:
        raise ChecksumError('The CRC width "{}" must be a number from 1 to 32.'.format(parts[0]))
    if not 1 <= width <= 32:
        raise ChecksumError("The CRC width must be from 1 to 32 bits (not {}).".format(width))
    values = []
    for label, text in zip(("polynomial", "init", "finalXOR"), parts[1:4]):
        try:
            value = int(text, 16)
        except ValueError:
            raise ChecksumError('The CRC {} "{}" must be a HEX value.'.format(label, text))
        if value >= 1 << width:
            raise ChecksumError(
                "The CRC {} {} is too large for a CRC of {} bits.".format(label, text, width))
        values.append(value)
    flags = []
    for label, text in zip(("reflectIn", "reflectOut"), parts[4:6]):
        if text.lower() in YES:
            flags.append(True)
        elif text.lower() in NO:
            flags.append(False)
        else:
            raise ChecksumError('The CRC {} value "{}" must be Yes or No.'.format(label, text))
    return CrcParams(width, values[0], values[1], values[2], flags[0], flags[1])


def parse_checksum_spec(rule_text):
    """The checksum described by rule_text, or None when it is off.

    Raises ChecksumError with a plain message when the text is not valid.
    """
    text = _spec_text(rule_text)
    if not text or text.lower() in ("off", "none"):
        return None

    little_endian = False
    match = re.match(r"^(.*?)\s+L$", text, re.IGNORECASE)
    if match:
        text, little_endian = match.group(1).strip(), True

    custom = CUSTOM_CRC_PATTERN.match(text)
    if custom:
        params = _parse_custom_crc(custom.group(1))
        name = "CRC:{}".format(custom.group(1).replace(" ", ""))
        return ChecksumSpec(name, (params.width + 7) // 8, little_endian, params)

    name = text.upper()
    if name in PREDEFINED_CRCS:
        params = PREDEFINED_CRCS[name]
        return ChecksumSpec(name, (params.width + 7) // 8, little_endian, params)
    if name in SUM_RULES:
        return ChecksumSpec(name, SUM_RULES[name], little_endian)
    raise ChecksumError(
        '"{}" is not a known checksum. Use one from the list, or a custom CRC like '
        "CRC:16,8005,FFFF,0000,Yes,Yes.".format(text))


def check_checksum_rule(rule_text):
    """None if the rule text is valid, otherwise the problem as a message."""
    try:
        parse_checksum_spec(rule_text)
    except ChecksumError as exc:
        return str(exc)
    return None


def parse_rule(rule_text: str) -> str:
    """'off', 'unsupported' (not valid) or the checksum name in lower case."""
    try:
        spec = parse_checksum_spec(rule_text)
    except ChecksumError:
        return "unsupported"
    return "off" if spec is None else spec.name.lower()


# ----------------------------------------------------------------------
# Calculating
# ----------------------------------------------------------------------

def _reflect(value, width):
    result = 0
    for bit in range(width):
        if value >> bit & 1:
            result |= 1 << (width - 1 - bit)
    return result


def crc_value(params: CrcParams, data: bytes) -> int:
    """Generic CRC (works for any width from 1 to 32 bits)."""
    width = params.width
    mask = (1 << width) - 1
    crc = params.init
    for byte in data:
        if params.refin:
            byte = _reflect(byte, 8)
        for bit in range(7, -1, -1):
            top = (crc >> (width - 1)) & 1
            crc = (crc << 1) & mask
            if top ^ ((byte >> bit) & 1):
                crc ^= params.poly
    if params.refout:
        crc = _reflect(crc, width)
    return (crc ^ params.xorout) & mask


def _lrc_ascii_bytes(payload: bytes) -> bytes:
    """The binary values written as HEX text in a MODBUS ASCII frame."""
    text = payload
    if text.startswith(b":"):
        text = text[1:]
    try:
        decoded = bytes.fromhex(text.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise ChecksumError(
            "LRC-ASCII needs the data as HEX text in ASCII characters, e.g. :010300000001")
    return decoded


def _split_line_end(data: bytes):
    """(data without a final CR/LF, the final CR/LF bytes)."""
    end = len(data)
    while end > 0 and data[end - 1] in (0x0D, 0x0A) and len(data) - end < 2:
        end -= 1
    return data[:end], data[end:]


def _checksum_bytes(spec: ChecksumSpec, payload: bytes) -> bytes:
    name = spec.name
    if spec.crc is not None:
        value = crc_value(spec.crc, payload)
    elif name == "MOD256":
        value = sum(payload) & 0xFF
    elif name == "MOD65536":
        value = sum(payload) & 0xFFFF
    elif name == "XOR":
        value = 0
        for byte in payload:
            value ^= byte
    elif name in ("LRC", "-MOD256"):
        value = (-sum(payload)) & 0xFF
    elif name == "LRC-ASCII":
        return "{:02X}".format((-sum(_lrc_ascii_bytes(payload))) & 0xFF).encode("ascii")
    else:
        raise ChecksumError("Unknown checksum rule.")
    return value.to_bytes(spec.size, "little" if spec.little_endian else "big")


def compute_checksum(payload: bytes, rule_text: str) -> bytes:
    """Return the checksum bytes for payload (empty when the checksum is off)."""
    spec = parse_checksum_spec(rule_text)
    if spec is None:
        return b""
    if spec.before_line_end:
        payload = _split_line_end(payload)[0]
    return _checksum_bytes(spec, payload)


def append_checksum(payload: bytes, rule_text: str) -> bytes:
    """Return payload with checksum added (send path)."""
    spec = parse_checksum_spec(rule_text)
    if spec is None:
        return payload
    if spec.before_line_end:
        body, line_end = _split_line_end(payload)
        return body + _checksum_bytes(spec, body) + line_end
    return payload + _checksum_bytes(spec, payload)


def verify_checksum(frame: bytes, rule_text: str) -> bool:
    """Return True when the checksum in frame is valid."""
    try:
        spec = parse_checksum_spec(rule_text)
    except ChecksumError:
        return False
    if spec is None:
        return True

    if spec.before_line_end:
        frame = _split_line_end(frame)[0]
    if len(frame) < spec.size + 1:
        return False
    body, received = frame[:-spec.size], frame[-spec.size:]
    try:
        return _checksum_bytes(spec, body) == received
    except ChecksumError:
        return False


def checksum_size(rule_id: str) -> int:
    """Number of checksum bytes for a rule text (kept for older callers)."""
    try:
        spec = parse_checksum_spec(rule_id)
    except ChecksumError:
        return 0
    return 0 if spec is None else spec.size


# ----------------------------------------------------------------------
# Preview in the editors
# ----------------------------------------------------------------------

def get_checksum_description(rule_text: str) -> str:
    try:
        spec = parse_checksum_spec(rule_text)
    except ChecksumError as exc:
        return "Description: {}".format(exc)
    if spec is None:
        return "Description: No checksum is appended to this sequence."
    if spec.name == "LRC-ASCII":
        return ('Description: MODBUS ASCII LRC over the HEX text after ":", added as two HEX '
                "characters before a final CR LF.")
    if spec.crc is not None:
        p = spec.crc
        detail = "{}-bit CRC, poly {:X}, init {:X}, final XOR {:X}, reflect in/out {}/{}".format(
            p.width, p.poly, p.init, p.xorout, "Yes" if p.refin else "No",
            "Yes" if p.refout else "No")
    else:
        detail = {
            "MOD256": "sum of all bytes, modulo 256",
            "MOD65536": "sum of all bytes, modulo 65536",
            "XOR": "XOR of all bytes",
            "LRC": "negative sum of all bytes (all bytes incl. the LRC add up to 0)",
            "-MOD256": "negative sum of all bytes (all bytes incl. the result add up to 0)",
        }[spec.name]
    order = ""
    if spec.size > 1:
        order = " Low byte first." if spec.little_endian else " High byte first."
    return 'Description: "{}" ({}) over all bytes, added at the end ({} byte(s)).{}'.format(
        spec.name, detail, spec.size, order)


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
    description = get_checksum_description(rule_text)
    try:
        spec = parse_checksum_spec(rule_text)
    except ChecksumError:
        return "Preview: (checksum not valid)", description
    if spec is None:
        return "", ""

    if payload is None:
        return "Preview: (invalid sequence)", description

    body = format_bytes_for_preview(payload, display_mode)
    if not body:
        return "Preview: {}", description

    try:
        checksum = compute_checksum(payload, rule_text)
    except ChecksumError as exc:
        return "Preview: {" + body + "} (" + str(exc) + ")", description

    return "Preview: {" + body + "} = (" + format_bytes_for_preview(checksum, display_mode) + ")", \
        description
