"""Convert Docklight-style sequence strings to raw bytes."""

import re

PLACEHOLDER_PATTERN = re.compile(r"^<[^>]+>$")

PLACEHOLDER_BYTES = {
    "<ACK>": 0x06,
    "<BEL>": 0x07,
    "<BS>": 0x08,
    "<HT>": 0x09,
    "<LF>": 0x0A,
    "<VT>": 0x0B,
    "<FF>": 0x0C,
    "<CR>": 0x0D,
    "<SO>": 0x0E,
    "<SI>": 0x0F,
    "<DLE>": 0x10,
    "<DC1>": 0x11,
    "<DC2>": 0x12,
    "<DC3>": 0x13,
    "<DC4>": 0x14,
    "<NAK>": 0x15,
    "<SYN>": 0x16,
    "<ETB>": 0x17,
    "<CAN>": 0x18,
    "<EM>": 0x19,
    "<SUB>": 0x1A,
    "<ESC>": 0x1B,
    "<FS>": 0x1C,
    "<GS>": 0x1D,
    "<RS>": 0x1E,
    "<US>": 0x1F,
    "<SP>": 0x20,
    "<DEL>": 0x7F,
}


# A wildcard byte. In a send sequence it is a parameter filled in when sending
# (e.g. the device address on an RS485 bus); in a receive sequence it matches
# any one byte. Shown as "<?>" in ASCII mode so it differs from a real "?" (3F).
WILDCARD = "?"
WILDCARD_ASCII = "<?>"


class SequenceEncodeError(ValueError):
    """Raised when a sequence string cannot be converted to bytes."""


def count_wildcards(sequence: str) -> int:
    return sum(1 for token in (sequence or "").split() if token == WILDCARD)


def has_wildcards(sequence: str) -> bool:
    return count_wildcards(sequence) > 0


def parse_parameter_values(value) -> bytes:
    """Values for the ? bytes of a send sequence.

    A number (0-255) is one byte; text is HEX bytes separated by spaces or commas,
    e.g. "05" or "05 0A" ("0x05" and a single digit "5" are accepted too).
    """
    if isinstance(value, bool):
        raise SequenceEncodeError("a value must be a number or HEX text such as \"05\"")
    if isinstance(value, int):
        if 0 <= value <= 255:
            return bytes([value])
        raise SequenceEncodeError("{} is not a byte value (0 to 255)".format(value))
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str):
        raise SequenceEncodeError("a value must be a number or HEX text such as \"05\"")

    result = bytearray()
    for token in value.replace(",", " ").split():
        text = token[2:] if token.lower().startswith("0x") else token
        if not (1 <= len(text) <= 2) or any(ch not in "0123456789abcdefABCDEF" for ch in text):
            raise SequenceEncodeError(
                "{} is not a HEX byte (write two HEX digits, e.g. 05 or 0A)".format(token))
        result.append(int(text, 16))
    if not result:
        raise SequenceEncodeError("no value was given")
    return bytes(result)


def fill_wildcards(sequence: str, values: bytes) -> str:
    """Replace each ? in a send sequence, in order, with one of values."""
    needed = count_wildcards(sequence)
    values = bytes(values or b"")
    if len(values) != needed:
        raise SequenceEncodeError(
            "the sequence has {} parameter byte(s) (?) but {} value(s) were given".format(
                needed, len(values)))
    filled = iter(values)
    return " ".join("{:02X}".format(next(filled)) if token == WILDCARD else token
                    for token in sequence.split())


def compile_receive_pattern(sequence: str):
    """Pattern for matching received data: a list of byte values, with None for
    each ? (matches any byte)."""
    pattern = []
    for token in sequence.split():
        if token == WILDCARD:
            pattern.append(None)
        else:
            pattern.extend(encode_sequence(token))
    if not pattern:
        raise SequenceEncodeError("Sequence is empty.")
    return pattern


def encode_sequence(sequence: str) -> bytes:
    """Parse a space-separated HEX / placeholder sequence into bytes."""
    sequence = sequence.strip()
    if not sequence:
        raise SequenceEncodeError("Sequence is empty.")
    if has_wildcards(sequence):
        raise SequenceEncodeError(
            "the sequence has parameter bytes (?) that must be filled in when it is sent.")

    result = bytearray()
    for token in sequence.split():
        if PLACEHOLDER_PATTERN.match(token):
            upper = token.upper()
            if upper not in PLACEHOLDER_BYTES:
                raise SequenceEncodeError("Unknown placeholder: {}".format(token))
            result.append(PLACEHOLDER_BYTES[upper])
            continue

        if len(token) == 2 and all(ch in "0123456789ABCDEFabcdef" for ch in token):
            result.append(int(token, 16))
            continue

        if token.isdigit():
            value = int(token)
            if 0 <= value <= 255:
                result.append(value)
                continue

        raise SequenceEncodeError("Invalid sequence token: {}".format(token))

    return bytes(result)


def _token_to_byte(token: str):
    if PLACEHOLDER_PATTERN.match(token):
        return None
    if len(token) == 2 and all(ch in "0123456789ABCDEFabcdef" for ch in token):
        return int(token, 16)
    if token.isdigit():
        value = int(token)
        if 0 <= value <= 255:
            return value
    return None


def _byte_to_display(byte_val: int, mode: str) -> str:
    if mode == "HEX":
        return "{:02X}".format(byte_val)
    if mode == "Decimal":
        return str(byte_val)
    if mode == "Binary":
        return "{:08b}".format(byte_val)
    if 32 <= byte_val <= 126:
        return chr(byte_val)
    return "{:02X}".format(byte_val)


def format_sequence_display(sequence: str, mode: str = "HEX") -> str:
    """Format a stored sequence string for display in the chosen edit mode."""
    sequence = sequence.strip()
    if not sequence:
        return ""

    tokens = []
    for token in sequence.split():
        if token == WILDCARD:
            tokens.append(WILDCARD_ASCII if mode == "ASCII" else WILDCARD)
            continue
        if PLACEHOLDER_PATTERN.match(token):
            tokens.append(token)
            continue
        byte_val = _token_to_byte(token)
        if byte_val is None:
            tokens.append(token)
        else:
            tokens.append(_byte_to_display(byte_val, mode))
    return " ".join(tokens)
