"""Send and receive sequences proposed by the assistant.

The assistant writes them as JSON in a fenced block that starts with
```docklight-sequences. They are checked here and only added to the project when
the user clicks "Add to project" and confirms. Nothing is invented here: items
that are not written correctly are skipped and listed as problems.

Example block content:
    {"send": [{"name": "Read status", "data": "01 03 00 00 00 01", "checksum": "CRC-MODBUS"}],
     "receive": [{"name": "Status reply", "data": "01 03 02", "checksum": "CRC-MODBUS",
                  "action": "comment"}]}
"""

import json
from dataclasses import dataclass, field

from core.checksum import ChecksumError, parse_checksum_spec
from core.checksum_rules import CHECKSUM_OPTIONS, DEFAULT_CHECKSUM, DEFAULT_CHECKSUM_DETECT
from core.receive_actions import (
    NO_ANSWER_SEND_INDEX,
    ReceiveActionConfig,
    default_comment_text,
    receive_action_fields,
)
from core.sequence_codec import SequenceEncodeError, encode_sequence

SEQUENCE_FENCE = "docklight-sequences"
MAX_NAME_LENGTH = 40
MAX_SEQUENCES = 100

ACTIONS = ("comment", "answer", "stop")
# MODBUS RTU sends its CRC low byte first, so "CRC-MODBUS" always means "CRC-MODBUS L".
CHECKSUM_ALIASES = {"crc_modbus": "CRC-MODBUS L", "modbus": "CRC-MODBUS L",
                    "crc-modbus": "CRC-MODBUS L"}


def _checksum_label(text):
    """The checksum setting for a proposed sequence, or None if it is not valid.
    A known checksum gets its label from the list; anything else is kept as typed."""
    text = str(text or "off").split("#")[0].strip()
    if text.lower() in ("", "off", "none"):
        return DEFAULT_CHECKSUM
    text = CHECKSUM_ALIASES.get(text.lower(), text)
    try:
        spec = parse_checksum_spec(text)
    except ChecksumError:
        return None
    for label in CHECKSUM_OPTIONS:
        try:
            if parse_checksum_spec(label) == spec:
                return label
        except ChecksumError:
            continue
    return text


def _checksum_short(label):
    return label.split("#")[0].strip() or "off"


@dataclass
class ProposedSequence:
    kind: str                 # "send" or "receive"
    name: str
    data: str                 # HEX bytes, e.g. "50 49 4E 47"
    checksum: str = DEFAULT_CHECKSUM
    action: str = "comment"   # receive only: comment / answer / stop
    answer: str = ""          # receive "answer": name of the send sequence
    comment: str = ""         # receive: comment shown when detected

    def summary(self):
        text = "{}: {}".format(self.name, self.data)
        if self.checksum != DEFAULT_CHECKSUM:
            text += "  + {}".format(_checksum_short(self.checksum))
        if self.kind == "receive":
            if self.action == "answer":
                text += '  → answer with "{}"'.format(self.answer)
            elif self.action == "stop":
                text += "  → stop communication"
            else:
                text += "  → comment"
        return text


@dataclass
class SequenceProposal:
    send: list = field(default_factory=list)
    receive: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    def is_empty(self):
        return not self.send and not self.receive


def _normalize_data(value):
    """HEX bytes as 'AA BB CC'. Control names such as <CR> become their HEX value,
    so the sequence can also be used as an automatic answer."""
    if not isinstance(value, str) or not value.strip():
        raise SequenceEncodeError("the data is empty")
    tokens = []
    for token in value.replace(",", " ").split():
        if token.lower().startswith("0x"):
            token = token[2:]
        if len(token) == 1 and token in "0123456789abcdefABCDEF":
            token = "0" + token
        if len(token) == 2 and token[0] != "<":
            try:
                int(token, 16)
            except ValueError:
                raise SequenceEncodeError("{} is not a HEX byte".format(token))
        tokens.append(token.upper())
    # Two-digit tokens are HEX, ? is a parameter / any-byte wildcard; anything
    # else must be a known control name.
    result = []
    for token in tokens:
        if token == "?":
            result.append(token)
            continue
        if len(token) != 2 and not (token.startswith("<") and token.endswith(">")):
            raise SequenceEncodeError("{} is not a HEX byte".format(token))
        result.extend("{:02X}".format(byte) for byte in encode_sequence(token))
    if all(token == "?" for token in result):
        raise SequenceEncodeError("it has only ? bytes")
    return " ".join(result)


def _text(item, key):
    value = item.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _parse_item(kind, item, number):
    """One sequence from the JSON. Returns (ProposedSequence or None, problem or None)."""
    label = "{} sequence {}".format(kind.capitalize(), number)
    if not isinstance(item, dict):
        return None, "{}: not written correctly.".format(label)

    name = _text(item, "name")[:MAX_NAME_LENGTH]
    if not name:
        return None, "{}: it has no name.".format(label)
    label = '{} sequence "{}"'.format(kind.capitalize(), name)

    try:
        data = _normalize_data(item.get("data"))
    except SequenceEncodeError as exc:
        return None, "{}: the data is not valid ({}).".format(label, exc)

    checksum = _checksum_label(item.get("checksum", "off"))
    if checksum is None:
        return None, '{}: the checksum "{}" is not supported.'.format(label, item.get("checksum"))

    sequence = ProposedSequence(kind=kind, name=name, data=data, checksum=checksum)
    if kind == "receive":
        action = (_text(item, "action") or "comment").lower()
        if action not in ACTIONS:
            return None, '{}: the action "{}" is not known.'.format(label, item.get("action"))
        sequence.action = action
        sequence.comment = _text(item, "comment") or default_comment_text(name)
        if action == "answer":
            sequence.answer = _text(item, "answer")
            if not sequence.answer:
                return None, "{}: it should answer, but no send sequence is named.".format(label)
    return sequence, None


def parse_sequence_block(text):
    """Read the JSON from a ```docklight-sequences block."""
    proposal = SequenceProposal()
    try:
        document = json.loads(text)
    except ValueError:
        proposal.problems.append("The list from the assistant is not written correctly, so "
                                 "nothing can be added. Ask the assistant again.")
        return proposal
    if not isinstance(document, dict):
        proposal.problems.append("The list from the assistant is not written correctly.")
        return proposal

    for kind, target in (("send", proposal.send), ("receive", proposal.receive)):
        items = document.get(kind) or []
        if not isinstance(items, list):
            proposal.problems.append('The "{}" list is not written correctly.'.format(kind))
            continue
        seen = set()
        for number, item in enumerate(items, start=1):
            if len(target) >= MAX_SEQUENCES:
                proposal.problems.append(
                    "Only the first {} {} sequences are used.".format(MAX_SEQUENCES, kind))
                break
            sequence, problem = _parse_item(kind, item, number)
            if problem:
                proposal.problems.append(problem)
                continue
            key = sequence.name.casefold()
            if key in seen:
                proposal.problems.append('{} sequence "{}" is listed twice; only the first is '
                                         "used.".format(kind.capitalize(), sequence.name))
                continue
            seen.add(key)
            target.append(sequence)
    return proposal


def _receive_action(sequence, send_rows):
    """The action settings for a new receive sequence, and a note if it changed."""
    if sequence.action == "stop":
        return ReceiveActionConfig(action_type="Stop", answer_send_index=NO_ANSWER_SEND_INDEX,
                                   comment_text=sequence.comment, stop_communication=True), None
    if sequence.action == "answer":
        wanted = sequence.answer.casefold()
        for index, row in enumerate(send_rows):
            if str(row[1]).strip().casefold() == wanted:
                if "?" in str(row[2]).split():
                    note = ('Receive sequence "{}": the send sequence "{}" has ? bytes, so it '
                            "cannot be an automatic answer; it only shows a comment.").format(
                                sequence.name, row[1])
                    return ReceiveActionConfig(action_type="Comment",
                                               answer_send_index=NO_ANSWER_SEND_INDEX,
                                               comment_text=sequence.comment), note
                return ReceiveActionConfig(action_type="Answer", answer_send_index=index,
                                           comment_text=sequence.comment), None
        note = ('Receive sequence "{}": there is no send sequence called "{}", so it only '
                "shows a comment.").format(sequence.name, sequence.answer)
        return ReceiveActionConfig(action_type="Comment", answer_send_index=NO_ANSWER_SEND_INDEX,
                                   comment_text=sequence.comment), note
    return ReceiveActionConfig(action_type="Comment", answer_send_index=NO_ANSWER_SEND_INDEX,
                               comment_text=sequence.comment), None


def apply_proposal(proposal, send_rows, receive_rows, display_mode="HEX"):
    """Add the proposed sequences to copies of the project's rows.

    Sequences whose name already exists are skipped. Returns
    (new_send_rows, new_receive_rows, added_send, added_receive, notes).
    """
    new_send = list(send_rows)
    new_receive = list(receive_rows)
    added_send, added_receive, notes = [], [], []

    send_names = {str(row[1]).strip().casefold() for row in new_send}
    for sequence in proposal.send:
        if sequence.name.casefold() in send_names:
            notes.append('Send sequence "{}" already exists, so it was not added.'.format(sequence.name))
            continue
        new_send.append(("", sequence.name, sequence.data, False, sequence.checksum,
                         display_mode, 0.0))
        send_names.add(sequence.name.casefold())
        added_send.append(sequence.name)

    receive_names = {str(row[1]).strip().casefold() for row in new_receive}
    for sequence in proposal.receive:
        if sequence.name.casefold() in receive_names:
            notes.append('Receive sequence "{}" already exists, so it was not added.'.format(sequence.name))
            continue
        action, note = _receive_action(sequence, new_send)
        if note:
            notes.append(note)
        new_receive.append(("☑", sequence.name, sequence.data, sequence.checksum,
                            DEFAULT_CHECKSUM_DETECT, display_mode, *receive_action_fields(action)))
        receive_names.add(sequence.name.casefold())
        added_receive.append(sequence.name)

    return new_send, new_receive, added_send, added_receive, notes
