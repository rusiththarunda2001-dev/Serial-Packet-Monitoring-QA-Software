"""Shared checksum rule labels for send/receive sequence editors."""

CHECKSUM_OPTIONS = [
    "# (off, no checksum)",
    "MOD256 # simple one byte sum on all but the last character",
    "XOR # simple XOR on all but the last character",
    "CRC-MODBUS L # MODBUS RTU checksum. Lower Byte first ('Little Endian')",
    (
        "(2, -5) LRC-ASCII A @ -4 # MODBUS ASCII checksum is LRC over readable "
        "HEX data, excluding start/end characters"
    ),
    "(2, -2) LRC # Binary LRC, e.g. for POS/payment protocols with STX/ETX telegrams",
    "(1, 3) CRC-16 @ 10 # CRC-16 checksum over the first 3 bytes.",
    (
        "(1, -4) CRC-XMODEM @ -3 # CRC-XMODEM sum placed before a "
        "end-of-line character, e.g. CR"
    ),
    "(2, -5) CRC:8,07,00,00,No,Yes # CRC with custom, non-standard spec.",
]

CHECKSUM_DETECT_OPTIONS = [
    "Detect Checksum OK",
    "Checksum Wrong",
    "Both OK/Wrong",
]

DEFAULT_CHECKSUM = CHECKSUM_OPTIONS[0]
DEFAULT_CHECKSUM_DETECT = CHECKSUM_DETECT_OPTIONS[0]
