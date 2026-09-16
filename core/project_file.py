"""Save and load Docklight project files as Excel Workbooks."""

from __future__ import annotations

import openpyxl
from copy import deepcopy
from pathlib import Path

from core.checksum_rules import DEFAULT_CHECKSUM, DEFAULT_CHECKSUM_DETECT
from core.receive_actions import (
    ReceiveActionConfig,
    parse_receive_action,
    receive_action_fields,
)
from core.settings_saver import DEFAULT_PROJECT_SETTINGS

PROJECT_FORMAT_VERSION = 1
PROJECT_FILE_EXTENSION = ".xlsx"
PROJECT_FILE_TYPES = [
    ("Docklight Project (Excel)", "*.xlsx"),
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
    
    script_commands = document.get("script_commands", [])


    if hasattr(home, "clear_script_editor") and hasattr(home, "_script_sheet"):
        home.clear_script_editor()
        if script_commands:
            # Reconstruct the sheet matrix using only the raw command strings
            sheet_data = [[str(cmd)] for cmd in script_commands]
            home._script_sheet.set_sheet_data(sheet_data)
            home._script_sheet.redraw()

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

    if hasattr(home, "comm_service"):
        home.comm_service.configure_session(home.project_settings.as_dict())
    if hasattr(home, "_update_flow_control_bar"):
        home._update_flow_control_bar()


def save_project_file(path, home) -> None:
    """Write the current project to disk as a multi-sheet Excel file."""
    # 1. Gather all data using your existing JSON-style builder
    document = build_project_document(home)
    
    # 2. Create a new Excel Workbook
    wb = openpyxl.Workbook()
    
    # ==========================================
    # SHEET 01: Project Settings & Meta Data
    # ==========================================
    ws_settings = wb.active
    ws_settings.title = "Sheet01_Settings"
    ws_settings.append(["Meta/Setting Key", "Value"])
    
    ws_settings.append(["format_version", str(document.get("format_version", ""))])
    ws_settings.append(["app", str(document.get("app", ""))])
    ws_settings.append(["display_mode", str(document.get("display_mode", ""))])
    
    settings = document.get("settings", {})
    for key, value in settings.items():
        if isinstance(value, (list, tuple)):
            value = ", ".join(map(str, value))
        ws_settings.append([key, str(value)])


    # ==========================================
    # SHEET 02: Send Sequences
    # ==========================================
    ws_send = wb.create_sheet(title="Sheet02_Send_Sequences")
    send_headers = [
        "name", "sequence", "periodic", "checksum", 
        "display_mode", "repeat_interval"
    ]
    ws_send.append(send_headers)
    
    for row_dict in document.get("send_sequences", []):
        ws_send.append([
            str(row_dict.get("name", "")),
            str(row_dict.get("sequence", "")),
            str(row_dict.get("periodic", False)),
            str(row_dict.get("checksum", "")),
            str(row_dict.get("display_mode", "")),
            str(row_dict.get("repeat_interval", 0.0))
        ])


    # ==========================================
    # SHEET 03: Receive Sequences
    # ==========================================
    ws_receive = wb.create_sheet(title="Sheet03_Receive_Sequences")
    receive_headers = [
        "active", "name", "sequence", "checksum", "checksum_detect", "display_mode",
        "action_type", "answer_send_index", "comment_text", "comment_line_break",
        "comment_timestamp", "snapshot_trigger", "stop_communication"
    ]
    ws_receive.append(receive_headers)
    
    for row_dict in document.get("receive_sequences", []):
        action = row_dict.get("action", {})
        ws_receive.append([
            str(row_dict.get("active", False)),
            str(row_dict.get("name", "")),
            str(row_dict.get("sequence", "")),
            str(row_dict.get("checksum", "")),
            str(row_dict.get("checksum_detect", "")),
            str(row_dict.get("display_mode", "")),
            str(action.get("action_type", "")),
            str(action.get("answer_send_index", "")),
            str(action.get("comment_text", "")),
            str(action.get("comment_line_break", True)),
            str(action.get("comment_timestamp", False)),
            str(action.get("snapshot_trigger", True)),
            str(action.get("stop_communication", False))
        ])


    # ==========================================
    # SHEET 04: Project Script
    # ==========================================
    ws_script = wb.create_sheet(title="Sheet04_Script")
    ws_script.append(["command number", "command"])
    
    if hasattr(home, "get_script_text"):
        script_text = home.get_script_text()
        command_number = 1
        for line in script_text.splitlines():
            line = line.strip()
            if line:
                # Add the sequential number and the entire line as a single string
                ws_script.append([command_number, line])
                command_number += 1


    # ==========================================
    # Save the Workbook to Disk
    # ==========================================
    target = Path(path)
    if target.suffix.lower() != PROJECT_FILE_EXTENSION:
        target = target.with_suffix(PROJECT_FILE_EXTENSION)
        
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
    except OSError as exc:
        raise ProjectFileError("Could not save project:\n{}".format(exc)) from exc


def load_project_file(path) -> dict:
    """Read an Excel project file and reconstruct the document dictionary."""
    source = Path(path)
    if not source.is_file():
        raise ProjectFileError("Project file not found:\n{}".format(source))

    try:
        wb = openpyxl.load_workbook(source, data_only=True)
    except Exception as exc:
        raise ProjectFileError("Could not read project file:\n{}".format(exc)) from exc

    # Base dictionary structure that apply_project_document expects
    document = {
        "format_version": PROJECT_FORMAT_VERSION,
        "app": "EC Docklight",
        "display_mode": "HEX",
        "settings": {},
        "send_sequences": [],
        "receive_sequences": [],
        "script_commands": []
    }

    # ==========================================
    # Read SHEET 01: Project Settings
    # ==========================================
    if "Sheet01_Settings" in wb.sheetnames:
        ws_settings = wb["Sheet01_Settings"]
        for row in ws_settings.iter_rows(min_row=2, values_only=True): 
            if not row or row[0] is None:
                continue
            
            key = str(row[0])
            val = str(row[1]) if row[1] is not None else ""

            if key == "format_version":
                try:
                    document["format_version"] = int(val)
                except ValueError:
                    document["format_version"] = PROJECT_FORMAT_VERSION
            elif key == "app":
                document["app"] = val
            elif key == "display_mode":
                document["display_mode"] = val
            else:
                if key == "channel_aliases":
                    aliases = [a.strip() for a in val.split(",")]
                    while len(aliases) < 2:
                        aliases.append("")
                    document["settings"][key] = aliases[:2]
                else:
                    document["settings"][key] = val

    # ==========================================
    # Read SHEET 02: Send Sequences
    # ==========================================
    if "Sheet02_Send_Sequences" in wb.sheetnames:
        ws_send = wb["Sheet02_Send_Sequences"]
        if ws_send.max_row > 1:
            headers = [str(c.value) if c.value else "" for c in ws_send[1]]
            
            for row in ws_send.iter_rows(min_row=2, values_only=True):
                if not any(row): continue
                
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        val = row[i]
                        if header == "periodic":
                            val = str(val).lower() in ("true", "1")
                        elif header == "repeat_interval":
                            try: val = float(val)
                            except (ValueError, TypeError): val = 0.0
                        elif val is None:
                            val = ""
                            
                        row_dict[header] = val
                document["send_sequences"].append(row_dict)

    # ==========================================
    # Read SHEET 03: Receive Sequences
    # ==========================================
    if "Sheet03_Receive_Sequences" in wb.sheetnames:
        ws_receive = wb["Sheet03_Receive_Sequences"]
        if ws_receive.max_row > 1:
            headers = [str(c.value) if c.value else "" for c in ws_receive[1]]
            
            action_keys = {
                "action_type", "answer_send_index", "comment_text", 
                "comment_line_break", "comment_timestamp", 
                "snapshot_trigger", "stop_communication"
            }

            for row in ws_receive.iter_rows(min_row=2, values_only=True):
                if not any(row): continue
                
                row_dict = {"action": {}}
                for i, header in enumerate(headers):
                    if i < len(row):
                        val = row[i] if row[i] is not None else ""
                        
                        if header in ("active", "comment_line_break", "comment_timestamp", "snapshot_trigger", "stop_communication"):
                            val = str(val).lower() in ("true", "1")
                        elif header == "answer_send_index":
                            try: val = int(val)
                            except (ValueError, TypeError): val = 0
                        
                        if header in action_keys:
                            row_dict["action"][header] = val
                        else:
                            row_dict[header] = val
                            
                document["receive_sequences"].append(row_dict)

    # ==========================================
    # Read SHEET 04: Project Script
    # ==========================================
    if "Sheet04_Script" in wb.sheetnames:
        ws_script = wb["Sheet04_Script"]
        # Start from row 2 to skip the header
        for row in ws_script.iter_rows(min_row=2, values_only=True):
            if not row or not any(row): 
                continue
            # row[0] is command_number, row[1] is the command string
            if len(row) > 1 and row[1]:
                document["script_commands"].append(str(row[1]))

    return document