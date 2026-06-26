"""Format raw communication bytes for the communication panel."""


def iter_comm_lines(data):
    """Yield (line_bytes, ending) for each logical line in a payload."""
    if not data:
        return

    start = 0
    index = 0
    while index < len(data):
        if data[index] == 0x0D and index + 1 < len(data) and data[index + 1] == 0x0A:
            yield data[start:index], b"\r\n"
            index += 2
            start = index
            continue

        if data[index] in (0x0D, 0x0A):
            yield data[start:index], bytes([data[index]])
            index += 1
            start = index
            continue

        index += 1

    if start < len(data):
        yield data[start:], b""


def ending_control_tokens(ending):
    if ending == b"\r\n":
        return ["<CR>", "<LF>"]
    if ending == b"\r":
        return ["<CR>"]
    if ending == b"\n":
        return ["<LF>"]
    return []


def format_comm_segments(data, mode):
    """Return (text, tag) segments for one payload line in the given display mode."""
    segments = []

    def append_ascii_char(char):
        if segments and segments[-1][1] == "data":
            segments[-1] = (segments[-1][0] + char, "data")
        else:
            segments.append((char, "data"))

    def append_spaced_token(token):
        if segments and segments[-1][1] == "data":
            segments[-1] = (segments[-1][0] + " " + token, "data")
        else:
            segments.append((token, "data"))

    for byte_val in data:
        if mode == "HEX":
            append_spaced_token("{:02X}".format(byte_val))
        elif mode == "Decimal":
            append_spaced_token(str(byte_val))
        elif mode == "Binary":
            append_spaced_token("{:08b}".format(byte_val))
        elif 32 <= byte_val <= 126:
            append_ascii_char(chr(byte_val))
        else:
            segments.append((".", "data"))

    return segments


def format_line_ending_segments(ending):
    return [(token, "control") for token in ending_control_tokens(ending)]
