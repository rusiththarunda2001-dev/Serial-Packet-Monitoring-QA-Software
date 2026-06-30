"""Receive sequence action configuration and helpers."""

from __future__ import annotations

from dataclasses import dataclass

ACTION_TYPES = ("Answer", "Comment", "Trigger", "Stop")
NO_ANSWER_SEND_INDEX = -1
NO_ANSWER_OPTION = "No answer"


@dataclass
class ReceiveActionConfig:
    action_type: str = "Answer"
    answer_send_index: int = 0
    comment_text: str = ""
    comment_line_break: bool = True
    comment_timestamp: bool = False
    snapshot_trigger: bool = True
    stop_communication: bool = False


def default_comment_text(sequence_name: str) -> str:
    name = sequence_name.strip()
    if not name:
        return ""
    first_word = name.split()[0]
    return '"{}" received'.format(first_word)


def parse_receive_action(row, sequence_name: str = "") -> ReceiveActionConfig:
    """Read action settings from a receive row tuple."""
    name = sequence_name or (row[1] if len(row) > 1 else "")
    action_type = row[6] if len(row) > 6 else "Answer"
    if action_type not in ACTION_TYPES:
        action_type = "Answer"

    answer_send_index = row[7] if len(row) > 7 else 0
    try:
        answer_send_index = int(answer_send_index)
    except (TypeError, ValueError):
        answer_send_index = 0
    if answer_send_index < 0:
        answer_send_index = NO_ANSWER_SEND_INDEX
    else:
        answer_send_index = max(0, answer_send_index)

    comment_text = row[8] if len(row) > 8 else default_comment_text(name)
    comment_line_break = row[9] if len(row) > 9 else True
    comment_timestamp = row[10] if len(row) > 10 else False
    snapshot_trigger = row[11] if len(row) > 11 else True
    stop_communication = row[12] if len(row) > 12 else False

    return ReceiveActionConfig(
        action_type=action_type,
        answer_send_index=answer_send_index,
        comment_text=comment_text,
        comment_line_break=bool(comment_line_break),
        comment_timestamp=bool(comment_timestamp),
        snapshot_trigger=bool(snapshot_trigger),
        stop_communication=bool(stop_communication),
    )


def format_answer_display(action: ReceiveActionConfig, send_rows, normalize_send_row) -> str:
    """Format the Answer column for a receive sequence row."""
    if action.action_type != "Answer":
        return ""

    index = action.answer_send_index
    if index < 0:
        return NO_ANSWER_OPTION

    if not (0 <= index < len(send_rows)):
        return ""

    send_row = normalize_send_row(send_rows[index])
    return send_row[1].strip() or "Sequence {}".format(index + 1)


def receive_action_fields(action: ReceiveActionConfig) -> tuple:
    """Serialize action settings for storage in a receive row."""
    return (
        action.action_type,
        action.answer_send_index,
        action.comment_text,
        action.comment_line_break,
        action.comment_timestamp,
        action.snapshot_trigger,
        action.stop_communication,
    )
