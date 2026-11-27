"""Shared checksum rule labels for send/receive sequence editors.

The text before "#" is the checksum specification (see core/checksum.py); the
text after it is only a comment, so older project files (whose labels had other
comments) still load with the same checksum.
"""

CHECKSUM_OPTIONS = [
    "# (off, no checksum)",
    "MOD256 # one byte sum of all bytes",
    "XOR # one byte XOR of all bytes",
    "CRC-MODBUS L # MODBUS RTU checksum. Lower Byte first ('Little Endian')",
    "MOD65536 # two byte sum (high byte first)",
    "LRC # negative one byte sum (-MOD256): all bytes incl. the LRC add up to 0",
    "LRC-ASCII # MODBUS ASCII: LRC as two HEX characters, put before a final CR LF",
    "CRC-7 # MMC/SD cards (7 bit, poly 09)",
    "CRC-8 # 8 bit, poly 07",
    "CRC-DOW # Dallas/Maxim 1-Wire iButton (8 bit, poly 31)",
    "CRC-CCITT # 16 bit, poly 1021, init FFFF",
    "CRC-XMODEM # 16 bit, poly 1021, init 0000",
    "CRC-16 # IBM / ARC (16 bit, poly 8005)",
    "CRC-32 # PKZip, Ethernet (32 bit)",
    "CRC:16,1021,FFFF,0000,No,No # your own CRC: width,poly,init,finalXOR,reflectIn,reflectOut",
]

CHECKSUM_DETECT_OPTIONS = [
    "Detect Checksum OK",
    "Checksum Wrong",
    "Both OK/Wrong",
]

DEFAULT_CHECKSUM = CHECKSUM_OPTIONS[0]
DEFAULT_CHECKSUM_DETECT = CHECKSUM_DETECT_OPTIONS[0]
