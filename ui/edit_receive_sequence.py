"""Edit Receive Sequence dialog UI."""

import tkinter as tk
from tkinter import ttk

from core.checksum import build_checksum_preview_text
from core.checksum_rules import (
    CHECKSUM_DETECT_OPTIONS,
    CHECKSUM_OPTIONS,
    DEFAULT_CHECKSUM,
    DEFAULT_CHECKSUM_DETECT,
)
from core.receive_actions import (
    ACTION_TYPES,
    NO_ANSWER_OPTION,
    NO_ANSWER_SEND_INDEX,
    ReceiveActionConfig,
    default_comment_text,
)
from core.sequence_codec import SequenceEncodeError, encode_sequence
from ui.sequence_text_editor import SequenceTextEditor
ACTION_TAB_INDEX = {name: index for index, name in enumerate(ACTION_TYPES)}


class EditReceiveSequence(tk.Toplevel):
    def __init__(
        self,
        parent,
        row_index=0,
        index="1",
        name="",
        sequence="50 6F 6E 67",
        row_count=1,
        checksum=None,
        checksum_detect=None,
        display_mode="HEX",
        action=None,
    ):
        super().__init__(parent)
        self.home = parent
        self._row_index = row_index
        self._row_count = max(1, row_count)

        self.title("Edit Receive Sequence")
        self.geometry("720x540")
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
        self._action = action or ReceiveActionConfig()
        self._current_action_type = self._action.action_type
        self._build_layout()
        self._load_action_settings()

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
        options = [NO_ANSWER_OPTION]
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
        section = ttk.LabelFrame(parent, text="Sequence Definition", padding=8)
        section.pack(fill=tk.X)
        name_row = tk.Frame(section)
        name_row.pack(fill=tk.X, pady=2)
        tk.Label(name_row, text="1 - Name", width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.name_entry = ttk.Entry(name_row)
        self.name_entry.insert(0, self._name)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.sequence_editor = SequenceTextEditor(
            section,
            sequence=self._sequence,
            display_mode=self._display_mode,
            on_change=self._update_checksum_preview,
            on_mode_change=self._on_sequence_mode_changed,
        )
        self.sequence_editor.pack(fill=tk.X, pady=(8, 0))

    def _on_sequence_mode_changed(self, mode):
        if hasattr(self.home, "apply_global_display_mode"):
            self.home.apply_global_display_mode(mode)

    def update_display_mode_from_global(self, mode):
        self.sequence_editor.set_display_mode(mode, skip_global_sync=True)

    def _get_sequence_bytes(self):
        try:
            sequence = self.sequence_editor.get_sequence_string()
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
            self.sequence_editor.get_display_mode(),
        )
        self.checksum_preview_label.config(text=preview_text)
        self.checksum_description_label.config(text=description_text)

    def _build_action_section(self, parent):
        section = ttk.LabelFrame(parent, text="3 - Action", padding=8)
        section.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(section)
        self._action_notebook = notebook
        notebook.pack(fill=tk.BOTH, expand=True)

        answer_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)
        comment_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)
        trigger_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)
        stop_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)
        checksum_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)

        notebook.add(answer_tab, text="Answer")
        notebook.add(comment_tab, text="Comment")
        notebook.add(trigger_tab, text="Trigger")
        notebook.add(stop_tab, text="Stop")
        notebook.add(checksum_tab, text="Checksum")

        self._build_answer_tab(answer_tab)
        self._build_comment_tab(comment_tab)
        self._build_trigger_tab(trigger_tab)
        self._build_stop_tab(stop_tab)
        self._build_checksum_tab(checksum_tab)

        self._current_action_type = self._action.action_type
        notebook.bind("<<NotebookTabChanged>>", self._on_action_tab_changed)
        notebook.select(ACTION_TAB_INDEX.get(self._action.action_type, 0))

    def _on_action_tab_changed(self, _event=None):
        tab_name = self._action_notebook.tab(
            self._action_notebook.index(self._action_notebook.select()),
            "text",
        )
        if tab_name in ACTION_TYPES:
            self._current_action_type = tab_name

    def _parse_answer_send_index(self):
        value = self.answer_combo.get().strip()
        if not value or value == NO_ANSWER_OPTION:
            return NO_ANSWER_SEND_INDEX
        prefix = value.split(":", 1)[0].strip()
        try:
            return max(0, int(prefix) - 1)
        except ValueError:
            return NO_ANSWER_SEND_INDEX

    def _get_action_config(self):
        return ReceiveActionConfig(
            action_type=self._current_action_type,
            answer_send_index=self._parse_answer_send_index(),
            comment_text=self.comment_entry.get(),
            comment_line_break=self.comment_line_break_var.get(),
            comment_timestamp=self.comment_timestamp_var.get(),
            snapshot_trigger=self.snapshot_trigger_var.get(),
            stop_communication=self.stop_communication_var.get(),
        )

    def _load_action_settings(self):
        action = self._action
        self._current_action_type = action.action_type
        self._action_notebook.select(ACTION_TAB_INDEX.get(action.action_type, 0))

        send_options = self._get_send_sequence_options()
        if send_options:
            if action.answer_send_index < 0:
                self.answer_combo.set(NO_ANSWER_OPTION)
            else:
                option_index = action.answer_send_index + 1
                if option_index < len(send_options):
                    self.answer_combo.set(send_options[option_index])
                elif len(send_options) > 1:
                    self.answer_combo.set(send_options[1])
                else:
                    self.answer_combo.set(NO_ANSWER_OPTION)

        self.comment_entry.delete(0, tk.END)
        self.comment_entry.insert(
            0,
            action.comment_text or default_comment_text(self._name),
        )
        self.comment_line_break_var.set(action.comment_line_break)
        self.comment_timestamp_var.set(action.comment_timestamp)
        self.snapshot_trigger_var.set(action.snapshot_trigger)
        self.stop_communication_var.set(action.stop_communication)

    def _build_answer_tab(self, parent):
        tk.Label(
            parent,
            text="Send out the following sequence:",
            bg="#d9d9d9",
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 6))

        send_options = self._get_send_sequence_options()
        self.answer_combo = ttk.Combobox(
            parent,
            values=send_options,
            width=40,
            state="readonly",
        )
        self.answer_combo.set(send_options[0])
        self.answer_combo.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            parent,
            text=(
                "Only send sequences without any wildcards are valid as an "
                "automatic answer."
            ),
            bg="#d9d9d9",
            anchor=tk.W,
            wraplength=640,
            justify=tk.LEFT,
        ).pack(fill=tk.X)

    def _default_comment_text(self):
        return default_comment_text(self.name_entry.get().strip() or self._name)

    def _build_comment_tab(self, parent):
        tk.Label(
            parent,
            text="Insert the following comment into the communication window:",
            bg="#d9d9d9",
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

        self.comment_timestamp_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent,
            text="Additional time stamp after the comment",
            variable=self.comment_timestamp_var,
        ).pack(anchor=tk.W)

    def _build_trigger_tab(self, parent):
        tk.Label(
            parent,
            text="Docklight Snapshot Mode",
            bg="#d9d9d9",
            font=("Segoe UI", 9, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 8))

        trigger_row = tk.Frame(parent, bg="#d9d9d9")
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
            bg="#d9d9d9",
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
        dropdown_row = tk.Frame(parent, bg="#d9d9d9")
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
        ttk.Button(btn_group, text="OK", command=self._on_ok).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_group, text="Cancel", command=self.destroy).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(btn_group, text="Apply", command=self._on_apply).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_group, text="Help").pack(side=tk.LEFT, padx=2)

    def _save_sequence(self):
        name = self.name_entry.get().strip()
        sequence = self.sequence_editor.get_sequence_string()
        new_index = self._get_index() - 1
        self.home.update_receive_sequence(
            self._row_index,
            new_index,
            name,
            sequence,
            checksum=self.checksum_combo.get(),
            checksum_detect=self.detect_combo.get(),
            display_mode=self.sequence_editor.get_display_mode(),
            action=self._get_action_config(),
        )
        self._action = self._get_action_config()
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
    EditReceiveSequence(root, row_index=0, index="1", name="", sequence="")
    root.mainloop()
