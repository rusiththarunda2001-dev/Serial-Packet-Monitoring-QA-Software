"""Edit Receive Sequence dialog UI."""

import re
import tkinter as tk
from tkinter import ttk

from core.checksum import build_checksum_preview_text
from core.checksum_rules import (
    CHECKSUM_DETECT_OPTIONS,
    CHECKSUM_OPTIONS,
    DEFAULT_CHECKSUM,
    DEFAULT_CHECKSUM_DETECT,
)
from core.sequence_codec import SequenceEncodeError, encode_sequence

PLACEHOLDER_PATTERN = re.compile(r"^<[^>]+>$")


class EditReceiveSequence(tk.Toplevel):
    def __init__(
        self,
        parent,
        row_index=0,
        index="1",
        name="Pong received",
        sequence="50 6F 6E 67",
        row_count=1,
        checksum=None,
        checksum_detect=None,
        display_mode="HEX",
    ):
        super().__init__(parent)
        self.home = parent
        self._row_index = row_index
        self._row_count = max(1, row_count)
        self._cell_values = []
        self._byte_cells = []
        self._updating_mode = False

        self.title("Edit Receive Sequence")
        self.geometry("720x560")
        self.resizable(False, False)
        self.configure(bg="#d9d9d9")
        self.transient(parent)
        self.grab_set()

        self._index = index
        self._name = name
        self._sequence = sequence
        self._checksum = checksum or DEFAULT_CHECKSUM
        self._checksum_detect = checksum_detect or DEFAULT_CHECKSUM_DETECT
        self._display_mode = display_mode if display_mode in ("ASCII", "HEX", "Decimal", "Binary") else "HEX"
        self._build_layout()
        self._previous_mode = self._display_mode
        self._load_sequence_cells()
        self._render_sequence_cells()

    def _build_layout(self):
        self._build_footer(self)

        main = tk.Frame(self, bg="#d9d9d9", padx=12, pady=10)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_index_row(main)
        self._add_separator(main)
        self._build_sequence_definition(main)
        self._add_separator(main)
        self._build_action_section(main)

    def _add_separator(self, parent):
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

    def _build_index_row(self, parent):
        row = tk.Frame(parent, bg="#d9d9d9")
        row.pack(fill=tk.X)

        tk.Label(row, text="Index", bg="#d9d9d9").pack(side=tk.LEFT)
        self.index_entry = ttk.Entry(row, width=4)
        self.index_entry.insert(0, self._index)
        self.index_entry.pack(side=tk.LEFT, padx=(8, 4))
        self.index_entry.bind("<FocusOut>", self._on_index_focus_out)
        self.index_entry.bind("<Return>", self._on_index_focus_out)

        ttk.Button(row, text="<", width=3, command=self._decrement_index).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(row, text=">", width=3, command=self._increment_index).pack(
            side=tk.LEFT, padx=2
        )



    def _get_send_sequence_options(self):
        options = []
        for index, row in enumerate(self.home._send_rows):
            name = row[1].strip() or "Sequence {}".format(index + 1)
            options.append("{}: {}".format(index + 1, name))
        return options

    def _clamp_index(self, value):
        try:
            index = int(value)
        except ValueError:
            index = self._row_index + 1
        return max(1, min(index, self._row_count))

    def _set_index(self, value):
        index = self._clamp_index(value)
        self.index_entry.delete(0, tk.END)
        self.index_entry.insert(0, str(index))

    def _get_index(self):
        return self._clamp_index(self.index_entry.get())

    def _decrement_index(self):
        self._set_index(self._get_index() - 1)

    def _increment_index(self):
        self._set_index(self._get_index() + 1)

    def _on_index_focus_out(self, _event=None):
        self._set_index(self.index_entry.get())

    def _build_sequence_definition(self, parent):
        section = tk.Frame(parent, bg="#d9d9d9")
        section.pack(fill=tk.X)

        tk.Label(
            section,
            text="Sequence Definition",
            bg="#d9d9d9",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        name_row = tk.Frame(section, bg="#d9d9d9")
        name_row.pack(fill=tk.X, pady=2)
        tk.Label(name_row, text="1 - Name", bg="#d9d9d9", width=12, anchor=tk.W).pack(
            side=tk.LEFT
        )
        self.name_entry = ttk.Entry(name_row)
        self.name_entry.insert(0, self._name)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        seq_header = tk.Frame(section, bg="#d9d9d9")
        seq_header.pack(fill=tk.X, pady=(8, 2))
        tk.Label(seq_header, text="2 - Sequence", bg="#d9d9d9", width=12, anchor=tk.W).pack(
            side=tk.LEFT
        )
        tk.Label(seq_header, text="Edit Mode", bg="#d9d9d9").pack(side=tk.LEFT, padx=(0, 8))

        self.edit_mode = tk.StringVar(value=self._display_mode)
        for mode in ("ASCII", "HEX", "Decimal", "Binary"):
            ttk.Radiobutton(
                seq_header,
                text=mode,
                variable=self.edit_mode,
                value=mode,
                command=self._on_edit_mode_changed,
            ).pack(side=tk.LEFT, padx=2)

        self.pos_label = tk.Label(seq_header, text="Pos. 0 / 0", bg="#d9d9d9")
        self.pos_label.pack(side=tk.RIGHT)

        self.seq_area = tk.Frame(section, bg="white", relief=tk.SUNKEN, bd=1, height=80)
        self.seq_area.pack(fill=tk.X, pady=4)
        self.seq_area.pack_propagate(False)

        self.cells_frame = tk.Frame(self.seq_area, bg="white")
        self.cells_frame.pack(anchor=tk.W, padx=8, pady=8)

    def _load_sequence_cells(self):
        tokens = self._sequence.split() if self._sequence.strip() else []
        self._cell_values = [
            self._token_to_display(token, self._display_mode) for token in tokens
        ]
        if not self._cell_values:
            self._cell_values = [""]

    def _token_to_byte(self, token):
        if PLACEHOLDER_PATTERN.match(token):
            return None
        if len(token) == 2 and all(ch in "0123456789ABCDEFabcdef" for ch in token):
            return int(token, 16)
        return None

    def _token_to_display(self, token, mode):
        if PLACEHOLDER_PATTERN.match(token):
            return token
        byte_val = self._token_to_byte(token)
        if byte_val is None:
            return token
        return self._byte_to_display(byte_val, mode)

    def _byte_to_display(self, byte_val, mode):
        if mode == "HEX":
            return f"{byte_val:02X}"
        if mode == "Decimal":
            return str(byte_val)
        if mode == "Binary":
            return f"{byte_val:08b}"
        if 32 <= byte_val <= 126:
            return chr(byte_val)
        return f"{byte_val:02X}"

    def _display_to_byte(self, value, mode):
        value = value.strip()
        if not value or PLACEHOLDER_PATTERN.match(value):
            return None
        try:
            if mode == "HEX":
                return int(value, 16)
            if mode == "Decimal":
                number = int(value, 10)
                if 0 <= number <= 255:
                    return number
                return None
            if mode == "Binary":
                if not all(ch in "01" for ch in value):
                    return None
                return int(value, 2)
            if len(value) == 1:
                return ord(value)
        except ValueError:
            return None
        return None

    def _cell_width(self, mode):
        if mode == "Binary":
            return 10
        if mode == "Decimal":
            return 4
        return 4

    def _validate_cell_input(self, mode, proposed):
        if proposed == "":
            return True
        if PLACEHOLDER_PATTERN.match(proposed):
            return True
        if mode == "HEX":
            return bool(re.fullmatch(r"[0-9A-Fa-f]{0,2}", proposed))
        if mode == "Decimal":
            if not proposed.isdigit() or len(proposed) > 3:
                return False
            return int(proposed) <= 255
        if mode == "Binary":
            return bool(re.fullmatch(r"[01]{0,8}", proposed))
        return len(proposed) <= 1

    def _normalize_cell_values(self):
        while len(self._cell_values) > 1 and not self._cell_values[-1].strip():
            if not self._cell_values[-2].strip():
                self._cell_values.pop()
            else:
                break
        if not self._cell_values:
            self._cell_values = [""]

    def _get_cell_count(self):
        self._normalize_cell_values()
        if not any(value.strip() for value in self._cell_values):
            return 1
        if self._cell_values[-1].strip():
            return len(self._cell_values) + 1
        return len(self._cell_values)

    def _render_sequence_cells(self, focus_index=None):
        for cell in self._byte_cells:
            cell.destroy()
        self._byte_cells.clear()

        self._normalize_cell_values()
        mode = self.edit_mode.get()
        cell_count = self._get_cell_count()

        vcmd = (self.register(self._validate_keypress), "%P")
        for index in range(cell_count):
            while len(self._cell_values) <= index:
                self._cell_values.append("")
            value = self._cell_values[index]
            cell = tk.Entry(
                self.cells_frame,
                width=self._cell_width(mode),
                justify=tk.CENTER,
                relief=tk.SOLID,
                bd=1,
                highlightthickness=1,
                highlightbackground="#4a90d9",
                highlightcolor="#4a90d9",
                insertwidth=1,
                validate="key",
                validatecommand=vcmd,
            )
            if value:
                cell.insert(0, value)
            cell.pack(side=tk.LEFT, padx=2)
            cell.bind("<FocusIn>", lambda _e, idx=index: self._update_position_label(idx))
            cell.bind("<KeyRelease>", lambda _e, idx=index: self._on_cell_changed(idx))
            cell.bind("<Return>", lambda _e, idx=index: self._on_cell_enter(idx))
            self._byte_cells.append(cell)

        if focus_index is not None and 0 <= focus_index < len(self._byte_cells):
            self._byte_cells[focus_index].focus_set()
            self._update_position_label(focus_index)
        else:
            self._update_position_label(0)

    def _validate_keypress(self, proposed):
        return self._validate_cell_input(self.edit_mode.get(), proposed)

    def _on_cell_changed(self, index):
        if index >= len(self._byte_cells):
            return
        self._cell_values[index] = self._byte_cells[index].get()
        self._update_position_label(index)
        self._update_checksum_preview()

    def _on_cell_enter(self, index):
        self._sync_cells_from_entries()
        if not self._byte_cells[index].get().strip():
            return "break"

        if index < len(self._byte_cells) - 1:
            self._byte_cells[index + 1].focus_set()
            self._update_position_label(index + 1)
        else:
            self._cell_values.append("")
            self._render_sequence_cells(focus_index=index + 1)

        return "break"

    def _update_position_label(self, index):
        filled = sum(1 for value in self._cell_values if value.strip())
        current = index + 1 if index >= 0 else 0
        self.pos_label.config(text=f"Pos. {current} / {filled}")

    def _sync_cells_from_entries(self):
        for index, cell in enumerate(self._byte_cells):
            if index < len(self._cell_values):
                self._cell_values[index] = cell.get()

    def _on_edit_mode_changed(self):
        if self._updating_mode:
            return

        self._sync_cells_from_entries()
        old_mode = getattr(self, "_previous_mode", "HEX")
        new_mode = self.edit_mode.get()
        converted = []

        for value in self._cell_values:
            if not value.strip():
                converted.append("")
                continue
            if PLACEHOLDER_PATTERN.match(value):
                converted.append(value)
                continue
            byte_val = self._display_to_byte(value, old_mode)
            if byte_val is None:
                converted.append(value)
            else:
                converted.append(self._byte_to_display(byte_val, new_mode))

        self._cell_values = converted or [""]
        self._previous_mode = new_mode
        self._render_sequence_cells()
        self._update_checksum_preview()

    def _get_sequence_bytes(self):
        try:
            sequence = self._get_sequence_string()
            if not sequence.strip():
                return b""
            return encode_sequence(sequence)
        except SequenceEncodeError:
            return None

    def _update_checksum_preview(self, _event=None):
        if not hasattr(self, "checksum_preview_label"):
            return

        preview_text, description_text = build_checksum_preview_text(
            self._get_sequence_bytes(),
            self.checksum_combo.get(),
            self.edit_mode.get(),
        )
        self.checksum_preview_label.config(text=preview_text)
        self.checksum_description_label.config(text=description_text)

    def _get_sequence_string(self):
        self._sync_cells_from_entries()
        mode = self.edit_mode.get()
        tokens = []

        for value in self._cell_values:
            value = value.strip()
            if not value:
                continue
            if PLACEHOLDER_PATTERN.match(value):
                tokens.append(value)
                continue
            byte_val = self._display_to_byte(value, mode)
            if byte_val is None:
                tokens.append(value)
            else:
                tokens.append(f"{byte_val:02X}")

        return " ".join(tokens)

    def _build_action_section(self, parent):
        section = tk.Frame(parent, bg="#d9d9d9")
        section.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(section, bg="#d9d9d9")
        header.pack(fill=tk.X, pady=(0, 4))
        tk.Label(header, text="3 - Action", bg="#d9d9d9", width=12, anchor=tk.W).pack(
            side=tk.LEFT
        )

        self._action_tab = "Answer"
        self._action_tab_buttons = {}
        tab_bar = tk.Frame(header, bg="#d9d9d9")
        tab_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        for tab_name in ("Answer", "Comment", "Trigger", "Stop", "Checksum"):
            button = tk.Button(
                tab_bar,
                text=tab_name,
                relief=tk.RAISED,
                padx=8,
                pady=2,
                bg="#ececec",
                command=lambda name=tab_name: self._show_action_tab(name),
            )
            button.pack(side=tk.LEFT, padx=1)
            self._action_tab_buttons[tab_name] = button

        self.action_body = tk.Frame(section, bg="#c8c8c8", relief=tk.SUNKEN, bd=1)
        self.action_body.pack(fill=tk.BOTH, expand=True)

        self._action_tab_frames = {
            "Answer": tk.Frame(self.action_body, bg="#c8c8c8", padx=8, pady=8),
            "Comment": tk.Frame(self.action_body, bg="#c8c8c8", padx=8, pady=8),
            "Trigger": tk.Frame(self.action_body, bg="#c8c8c8", padx=8, pady=8),
            "Stop": tk.Frame(self.action_body, bg="#c8c8c8", padx=8, pady=8),
            "Checksum": tk.Frame(self.action_body, bg="#c8c8c8", padx=8, pady=8),
        }

        self._build_answer_tab(self._action_tab_frames["Answer"])
        self._build_comment_tab(self._action_tab_frames["Comment"])
        self._build_trigger_tab(self._action_tab_frames["Trigger"])
        self._build_stop_tab(self._action_tab_frames["Stop"])
        self._build_checksum_tab(self._action_tab_frames["Checksum"])
        self._show_action_tab("Answer")

    def _show_action_tab(self, tab_name):
        self._action_tab = tab_name
        for name, frame in self._action_tab_frames.items():
            frame.pack_forget()

        self._action_tab_frames[tab_name].pack(fill=tk.BOTH, expand=True)

        for name, button in self._action_tab_buttons.items():
            button.config(relief=tk.SUNKEN if name == tab_name else tk.RAISED)

    def _build_answer_tab(self, parent):
        tk.Label(
            parent,
            text="Send out the following sequence:",
            bg="#c8c8c8",
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 6))

        send_options = self._get_send_sequence_options()
        self.answer_combo = ttk.Combobox(
            parent,
            values=send_options,
            width=40,
            state="readonly" if send_options else "disabled",
        )
        if send_options:
            self.answer_combo.set(send_options[0])
        self.answer_combo.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            parent,
            text=(
                "Only send sequences without any wildcards are valid as an "
                "automatic answer."
            ),
            bg="#c8c8c8",
            anchor=tk.W,
            wraplength=640,
            justify=tk.LEFT,
        ).pack(fill=tk.X)

    def _default_comment_text(self):
        name = self._name.strip()
        if not name:
            return ""
        first_word = name.split()[0]
        return '"{}" received'.format(first_word)

    def _build_comment_tab(self, parent):
        tk.Label(
            parent,
            text="Insert the following comment into the communication window:",
            bg="#c8c8c8",
            anchor=tk.W,
            wraplength=640,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 6))

        self.comment_entry = ttk.Entry(parent)
        self.comment_entry.insert(0, self._default_comment_text())
        self.comment_entry.pack(fill=tk.X, pady=(0, 10))

        self.comment_line_break_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent,
            text=(
                "Additional line break after the comment / begin new line after comment"
            ),
            variable=self.comment_line_break_var,
        ).pack(anchor=tk.W, pady=(0, 4))

        self.comment_timestamp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent,
            text="Additional time stamp after the comment",
            variable=self.comment_timestamp_var,
        ).pack(anchor=tk.W)

    def _build_trigger_tab(self, parent):
        tk.Label(
            parent,
            text="Docklight Snapshot Mode",
            bg="#c8c8c8",
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 8))

        trigger_row = tk.Frame(parent, bg="#c8c8c8")
        trigger_row.pack(fill=tk.X, anchor=tk.W)

        self.snapshot_trigger_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(trigger_row, variable=self.snapshot_trigger_var).pack(
            side=tk.LEFT, anchor=tk.N, padx=(0, 6)
        )
        tk.Label(
            trigger_row,
            text=(
                "Use this sequence as a trigger for the snapshot: If the sequence "
                "appears in the communication data received, Docklight will create "
                "a snapshot of this data in the communication window."
            ),
            bg="#c8c8c8",
            justify=tk.LEFT,
            wraplength=600,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_stop_tab(self, parent):
        self.stop_communication_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent,
            text=(
                "Stop communication, if this sequence appears in the serial data "
                "received."
            ),
            variable=self.stop_communication_var,
        ).pack(anchor=tk.W)

    def _build_checksum_tab(self, parent):
        dropdown_row = tk.Frame(parent, bg="#c8c8c8")
        dropdown_row.pack(fill=tk.X, pady=(0, 6))

        self.checksum_combo = ttk.Combobox(
            dropdown_row,
            values=CHECKSUM_OPTIONS,
            width=55,
            state="readonly",
        )
        if self._checksum in CHECKSUM_OPTIONS:
            self.checksum_combo.set(self._checksum)
        else:
            self.checksum_combo.set(DEFAULT_CHECKSUM)
        self.checksum_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.checksum_combo.bind("<<ComboboxSelected>>", self._update_checksum_preview)

        self.detect_combo = ttk.Combobox(
            dropdown_row,
            values=CHECKSUM_DETECT_OPTIONS,
            width=22,
            state="readonly",
        )
        if self._checksum_detect in CHECKSUM_DETECT_OPTIONS:
            self.detect_combo.set(self._checksum_detect)
        else:
            self.detect_combo.set(DEFAULT_CHECKSUM_DETECT)
        self.detect_combo.pack(side=tk.RIGHT)

        preview_area = tk.Frame(parent, bg="#e6e6e6", relief=tk.SUNKEN, bd=1, height=72)
        preview_area.pack(fill=tk.X)
        preview_area.pack_propagate(False)

        self.checksum_preview_label = tk.Label(
            preview_area,
            bg="#e6e6e6",
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self.checksum_preview_label.pack(fill=tk.X, padx=6, pady=(6, 2))

        self.checksum_description_label = tk.Label(
            preview_area,
            bg="#e6e6e6",
            anchor=tk.W,
            wraplength=640,
            justify=tk.LEFT,
        )
        self.checksum_description_label.pack(fill=tk.X, padx=6, pady=(0, 6))

        self._update_checksum_preview()

    def _build_footer(self, parent):
        footer = tk.Frame(parent, bg="#d9d9d9", padx=12)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 10))

        ttk.Button(footer, text="Delete Sequence", command=self._on_delete).pack(
            side=tk.LEFT
        )

        btn_group = tk.Frame(footer, bg="#d9d9d9")
        btn_group.pack(side=tk.RIGHT)
        ttk.Button(btn_group, text="OK", command=self._on_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_group, text="Cancel", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(btn_group, text="Apply", command=self._on_apply).pack(side=tk.LEFT, padx=4)

    def _save_sequence(self):
        name = self.name_entry.get().strip()
        sequence = self._get_sequence_string()
        new_index = self._get_index() - 1
        self.home.update_receive_sequence(
            self._row_index,
            new_index,
            name,
            sequence,
            checksum=self.checksum_combo.get(),
            checksum_detect=self.detect_combo.get(),
            display_mode=self.edit_mode.get(),
        )
        self._row_index = new_index

    def _on_ok(self):
        self._save_sequence()
        self.destroy()

    def _on_apply(self):
        self._save_sequence()

    def _on_delete(self):
        self.home.delete_receive_sequence(self._row_index)
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    EditReceiveSequence(root, row_index=0, index="1", name="ACK", sequence="<ACK>")
    root.mainloop()
