"""What the assistant is told: the rules, the user manual and a project snapshot."""

from pathlib import Path

from core.bot_sequences import SEQUENCE_FENCE
from core.script_engine import COMMAND_EXAMPLES

KNOWLEDGE_FILE = Path(__file__).resolve().with_name("bot_knowledge.md")
MAX_COMM_LINES = 150
MAX_COMM_CHARS = 8000
SCRIPT_FENCE = "docklight"

RULES = """You are the assistant built into EC Docklight, a serial port testing tool.
The people asking you are often not programmers.

How to answer:
- Use simple, short sentences and the names used in the app (buttons, menus, lists).
- Only describe features that are in the manual below. Never invent buttons,
  menus, settings or script commands. If the app cannot do something, say so.
- When you explain received data or an error, use the project information and the
  communication lines below if they are given.

When you write a script:
- Use ONLY the script commands listed in the manual. One command per line.
- Do not use variables, if/else, loops, Python or any other programming. The only
  exception: to check how often a reply came, you may write ONE line like
  if GetReceiveCounter("Pong") < 3: Comment("FAIL: Pong received only " + str(GetReceiveCounter("Pong")) + " times")
- Put the whole script in one fenced block that starts with ```{fence} and ends
  with ```. Nothing else goes inside that block (no explanations, no numbering).
- Use only send and receive sequence names that exist in the project below. If a
  sequence that is needed does not exist, say so and tell the user to create it
  in the Send Sequences or Receive Sequences list. Do not create data for it.
- If communication may not be started yet, begin with StartCommunication().
- After the block, explain in one or two short sentences what the script does.

Attached files:
- The user can attach files (PDF manuals or protocol descriptions, logs, scripts,
  Excel files) to a question. Their content comes before the question, marked
  'Attached file "<name>"'. Use them to answer, and say which file you used.
- If a file was only partly sent or is no longer sent, say so when it matters.

When the user asks you to create send or receive sequences (for example from the
protocol in an attached file):
- Put them in one fenced block that starts with ```{seq_fence} and ends with ```.
  Inside is only JSON in exactly this form:
  {{"send": [{{"name": "Read status", "data": "01 03 00 00 00 01", "checksum": "CRC-MODBUS"}}],
   "receive": [{{"name": "Status reply", "data": "01 03 02", "checksum": "off",
                "action": "comment", "comment": "Status received"}}]}}
- "data" is two-digit HEX bytes separated by spaces: EVERY byte exactly as it goes
  over the wire, including start and end bytes such as STX (02), ETX (03), CR (0D)
  and LF (0A). The app does not add any framing.
- The only exception is the checksum: when "checksum" is not "off", leave the
  checksum bytes out; the app adds them when sending and checks them when receiving.
- For a receive sequence, write the bytes at the start of the reply that are
  always the same, up to the first byte that changes (measured values, counters).
  The app finds this pattern anywhere in the received data.
- For a value that changes, such as the device address on an RS485/Modbus bus,
  write "?" for that byte: in a send sequence it is filled in when sending
  (script: SendSequence("Read", 0, 1, "05")); in a receive sequence it matches
  any byte, e.g. "? 03 04" for a reply from any address.
- "checksum" is "off" or one of the checksums listed in the manual, e.g. "MOD256",
  "XOR", "LRC", "CRC-16", "CRC-CCITT", "CRC-32", "CRC-MODBUS" (always sent low byte
  first), or a custom CRC "CRC:width,poly,init,finalXOR,reflectIn,reflectOut".
  Add " L" for low byte first. Only use a checksum the document names.
- "action" (receive only) is "comment" (default), "stop", or "answer" together
  with "answer": "<name of a send sequence>".
- Only use byte values that are given in the file or by the user. Never guess
  values. If something is unclear, leave that sequence out and say why.
- Use short, unique names that are not already in the project.
- The user adds them with the "Add to project" button. After the block, say in one
  or two sentences what you created.
""".format(fence=SCRIPT_FENCE, seq_fence=SEQUENCE_FENCE)


def _command_list():
    return "\n".join("- " + example for example in COMMAND_EXAMPLES.values())


def load_manual():
    try:
        text = KNOWLEDGE_FILE.read_text(encoding="utf-8")
    except OSError:
        text = "## Scripts\nCommands (examples):\n{command_list}\n"
    return text.replace("{command_list}", _command_list())


def _format_settings(settings):
    if not settings:
        return "(not available)"
    labels = (
        ("comm_mode", "Communication mode"),
        ("channel", "COM port (channel 1)"),
        ("channel2", "Second COM port (Monitoring only)"),
        ("baud_rate", "Baud rate"),
        ("data_bits", "Data bits"),
        ("parity", "Parity"),
        ("stop_bits", "Stop bits"),
        ("flow_control", "Flow control"),
        ("contents_filter", "Contents filter"),
    )
    return "\n".join("- {}: {}".format(label, settings.get(key, ""))
                     for key, label in labels if key in settings)


def _format_rows(rows, with_active):
    if not rows:
        return "(none)"
    lines = []
    for row in rows:
        line = '- "{}": {}'.format(row.get("name", ""), row.get("data", "") or "(empty)")
        if row.get("checksum") and not str(row["checksum"]).startswith("#"):
            line += "  [checksum: {}]".format(str(row["checksum"]).split("#")[0].strip())
        if with_active:
            line += "  (active)" if row.get("active") else "  (switched off)"
            if row.get("action"):
                line += "  action: {}".format(row["action"])
        lines.append(line)
    return "\n".join(lines)


def trim_comm_lines(text):
    """The last MAX_COMM_LINES lines, at most MAX_COMM_CHARS characters."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    lines = lines[-MAX_COMM_LINES:]
    result = "\n".join(lines)
    if len(result) > MAX_COMM_CHARS:
        result = result[-MAX_COMM_CHARS:]
        result = result.split("\n", 1)[-1]  # drop the cut first line
    return result


def format_snapshot(snapshot):
    """The project information sent with each question, as plain text."""
    snapshot = snapshot or {}
    parts = [
        "## The user's project right now",
        "Communication started: {}".format("yes" if snapshot.get("connected") else "no"),
        "",
        "### Settings",
        _format_settings(snapshot.get("settings")),
        "",
        "### Send sequences",
        _format_rows(snapshot.get("send"), with_active=False),
        "",
        "### Receive sequences",
        _format_rows(snapshot.get("receive"), with_active=True),
        "",
        "### Current script (row by row)",
    ]
    script = snapshot.get("script") or ""
    if script.strip():
        parts.extend("{}: {}".format(number, line)
                     for number, line in enumerate(script.split("\n"), start=1))
    else:
        parts.append("(empty)")
    parts.append("")
    if "comm_lines" in snapshot:
        parts.append("### Last lines of the communication window (ASCII tab)")
        parts.append(snapshot["comm_lines"] or "(empty)")
    else:
        parts.append("(The user has chosen not to share communication data.)")
    return "\n".join(parts)


def build_system_text(snapshot):
    return "\n\n".join([RULES, "# Manual\n" + load_manual(), format_snapshot(snapshot)])
