"""Save and load Docklight project files."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from core.checksum_rules import DEFAULT_CHECKSUM, DEFAULT_CHECKSUM_DETECT
from core.receive_actions import (
    ReceiveActionConfig,
    parse_receive_action,
    receive_action_fields,
)
from project_settings import DEFAULT_PROJECT_SETTINGS

PROJECT_FORMAT_VERSION = 1
PROJECT_FILE_EXTENSION = ".dck"
PROJECT_FILE_TYPES = [
    ("Docklight Project", "*.dck"),
    ("All files", "*.*"),
]


class ProjectFileError(Exception):
    """Raised when a project file cannot be read or written."""


def _active_to_bool(active) -> bool:
    return active in ("☑", True, "true", "True", 1)


def _bool_to_active(value) -> str:
    return "☑" if value else "☐"


def _serialize_send_row(row) -> dict:
    return {
        "name": row[1],
        "sequence": row[2],
        "periodic": bool(row[3]),
        "checksum": row[4],
        "display_mode": row[5],
        "repeat_interval": float(row[6]),
    }


def _serialize_receive_row(row) -> dict:
    normalized = _normalize_receive_row(row)
    action = parse_receive_action(normalized, normalized[1])
    return {
        "active": _active_to_bool(normalized[0]),
        "name": normalized[1],
        "sequence": normalized[2],
        "checksum": normalized[3],
        "checksum_detect": normalized[4],
        "display_mode": normalized[5],
        "action": {
            "action_type": action.action_type,
            "answer_send_index": action.answer_send_index,
            "comment_text": action.comment_text,
            "comment_line_break": action.comment_line_break,
            "comment_timestamp": action.comment_timestamp,
            "snapshot_trigger": action.snapshot_trigger,
            "stop_communication": action.stop_communication,
        },
    }


def _normalize_receive_row(row):
    active = row[0]
    name = row[1] if len(row) > 1 else ""
    sequence = row[2] if len(row) > 2 else ""
    checksum = row[3] if len(row) > 3 else DEFAULT_CHECKSUM
    checksum_detect = row[4] if len(row) > 4 else DEFAULT_CHECKSUM_DETECT
    display_mode = row[5] if len(row) > 5 else "HEX"
    action = parse_receive_action(row, name)
    return (
        active,
        name,
        sequence,
        checksum,
        checksum_detect,
        display_mode,
        *receive_action_fields(action),
    )


def _deserialize_send_row(data: dict) -> tuple:
    return (
        "",
        str(data.get("name", "")),
        str(data.get("sequence", "")),
        bool(data.get("periodic", False)),
        data.get("checksum", DEFAULT_CHECKSUM),
        data.get("display_mode", "HEX"),
        float(data.get("repeat_interval", 0.0) or 0.0),
    )


def _deserialize_receive_row(data: dict) -> tuple:
    action_data = data.get("action") or {}
    action = ReceiveActionConfig(
        action_type=action_data.get("action_type", "Answer"),
        answer_send_index=int(action_data.get("answer_send_index", 0)),
        comment_text=str(action_data.get("comment_text", "")),
        comment_line_break=bool(action_data.get("comment_line_break", True)),
        comment_timestamp=bool(action_data.get("comment_timestamp", False)),
        snapshot_trigger=bool(action_data.get("snapshot_trigger", True)),
        stop_communication=bool(action_data.get("stop_communication", False)),
    )
    return (
        _bool_to_active(data.get("active", False)),
        str(data.get("name", "")),
        str(data.get("sequence", "")),
        data.get("checksum", DEFAULT_CHECKSUM),
        data.get("checksum_detect", DEFAULT_CHECKSUM_DETECT),
        data.get("display_mode", "HEX"),
        *receive_action_fields(action),
    )


def build_project_document(home) -> dict:
    """Serialize the current application state into a project document."""
    settings = deepcopy(home.project_settings.as_dict())
    aliases = settings.get("channel_aliases", ("", ""))
    if isinstance(aliases, tuple):
        settings["channel_aliases"] = list(aliases)

    return {
        "format_version": PROJECT_FORMAT_VERSION,
        "app": "EC Docklight",
        "display_mode": home.get_display_mode(),
        "settings": settings,
        "send_sequences": [
            _serialize_send_row(home._normalize_send_row(row))
            for row in home._send_rows
        ],
        "receive_sequences": [
            _serialize_receive_row(row)
            for row in home._receive_rows
        ],
    }


def apply_project_document(home, document: dict) -> None:
    """Load a project document into the running application."""
    if not isinstance(document, dict):
        raise ProjectFileError("Project file is not a valid JSON object.")

    version = document.get("format_version")
    if version != PROJECT_FORMAT_VERSION:
        raise ProjectFileError(
            "Unsupported project format version: {}".format(version)
        )

    settings = deepcopy(DEFAULT_PROJECT_SETTINGS)
    raw_settings = document.get("settings") or {}
    if not isinstance(raw_settings, dict):
        raise ProjectFileError("Project settings must be an object.")
    settings.update(raw_settings)

    aliases = settings.get("channel_aliases", ["", ""])
    if isinstance(aliases, list):
        settings["channel_aliases"] = tuple(aliases)
    elif not isinstance(aliases, tuple):
        settings["channel_aliases"] = ("", "")

    send_rows = document.get("send_sequences") or []
    receive_rows = document.get("receive_sequences") or []
    if not isinstance(send_rows, list) or not isinstance(receive_rows, list):
        raise ProjectFileError("Sequence lists must be arrays.")

    home.stop_repeat_senders()
    home.project_settings.update(settings)
    home.com_port.set(home.project_settings.get("channel"))

    home._send_rows = [_deserialize_send_row(row) for row in send_rows]
    home._receive_rows = [_deserialize_receive_row(row) for row in receive_rows]

    display_mode = document.get("display_mode", "HEX")
    if display_mode not in ("ASCII", "HEX", "Decimal", "Binary"):
        display_mode = "HEX"

    home._global_display_mode = display_mode
    home._refresh_send_tree()
    home._refresh_receive_tree()

    if hasattr(home, "_comm_notebook"):
        modes = ("ASCII", "HEX", "Decimal", "Binary")
        if display_mode in modes:
            home._comm_notebook.select(modes.index(display_mode))


def save_project_file(path, home) -> None:
    """Write the current project to disk."""
    document = build_project_document(home)
    target = Path(path)
    if target.suffix.lower() != PROJECT_FILE_EXTENSION:
        target = target.with_suffix(PROJECT_FILE_EXTENSION)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(document, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ProjectFileError("Could not save project:\n{}".format(exc)) from exc


def load_project_file(path) -> dict:
    """Read a project file from disk."""
    source = Path(path)
    if not source.is_file():
        raise ProjectFileError("Project file not found:\n{}".format(source))

    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectFileError("Could not read project file:\n{}".format(exc)) from exc

    return document
