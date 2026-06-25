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


class SequenceEncodeError(ValueError):
    """Raised when a sequence string cannot be converted to bytes."""


def encode_sequence(sequence: str) -> bytes:
    """Parse a space-separated HEX / placeholder sequence into bytes."""
    sequence = sequence.strip()
    if not sequence:
        raise SequenceEncodeError("Sequence is empty.")

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
        if PLACEHOLDER_PATTERN.match(token):
            tokens.append(token)
            continue
        byte_val = _token_to_byte(token)
        if byte_val is None:
            tokens.append(token)
        else:
            tokens.append(_byte_to_display(byte_val, mode))
    return " ".join(tokens)
