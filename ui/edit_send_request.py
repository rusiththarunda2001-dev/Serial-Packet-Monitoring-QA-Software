"""Edit Send Sequence dialog UI."""

import tkinter as tk
from tkinter import ttk

from core.checksum import build_checksum_preview_text
from core.checksum_rules import CHECKSUM_OPTIONS, DEFAULT_CHECKSUM
from core.sequence_codec import SequenceEncodeError, encode_sequence
from ui.sequence_text_editor import SequenceTextEditor


class EditSendRequest(tk.Toplevel):
    def __init__(
        self,
        parent,
        row_index=0,
        index="1",
        name="check",
        sequence="",
        row_count=1,
        periodic=False,
        repeat_interval=0.0,
        checksum=None,
        display_mode="HEX",
    ):
        super().__init__(parent)
        self.home = parent
        self._row_index = row_index
        self._row_count = max(1, row_count)

        self.title("Edit Send Sequence")
        self.geometry("720x540")
        self.resizable(False, False)
        self.configure(bg="#d9d9d9")
        self.transient(parent)
        self.grab_set()

        self._index = index
        self._name = name
        self._sequence = sequence
        self._periodic = periodic
        self._repeat_interval = repeat_interval
        self._checksum = checksum or DEFAULT_CHECKSUM
        self._display_mode = display_mode if display_mode in ("ASCII", "HEX", "Decimal", "Binary") else "HEX"
        self._build_layout()

    def _build_layout(self):
        self._build_footer(self)

        main = tk.Frame(self, bg="#d9d9d9", padx=12, pady=10)
        main.pack(fill=tk.BOTH, expand=True)

        self._build_index_row(main)
        self._add_separator(main)
        self._build_sequence_definition(main)
        self._add_separator(main)
        self._build_additional_settings(main)

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

    def _build_additional_settings(self, parent):
        section = ttk.LabelFrame(parent, text="3 - Additional Settings", padding=8)
        section.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(section)
        notebook.pack(fill=tk.BOTH, expand=True)

        repeat_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)
        checksum_tab = tk.Frame(notebook, bg="#d9d9d9", padx=8, pady=8)
        notebook.add(repeat_tab, text="Repeat")
        notebook.add(checksum_tab, text="Checksum")

        self.periodic_var = tk.BooleanVar(value=self._periodic)
        ttk.Checkbutton(
            repeat_tab,
            text=(
                "Send periodically (if not sent as an automatic answer "
                "to a receive sequence)"
            ),
            variable=self.periodic_var,
        ).pack(anchor=tk.W)

        repeat_row = tk.Frame(repeat_tab, bg="#d9d9d9")
        repeat_row.pack(anchor=tk.W, padx=24, pady=(8, 0))

        tk.Label(repeat_row, text="Repeat sequence every", bg="#d9d9d9").pack(
            side=tk.LEFT
        )
        self.repeat_seconds_entry = ttk.Entry(repeat_row, width=5)
        self.repeat_seconds_entry.insert(0, self._format_repeat_interval(self._repeat_interval))
        self.repeat_seconds_entry.pack(side=tk.LEFT, padx=4)
        tk.Label(repeat_row, text="seconds", bg="#d9d9d9").pack(side=tk.LEFT)

        self.checksum_combo = ttk.Combobox(
            checksum_tab,
            values=CHECKSUM_OPTIONS,
            width=72,
            state="readonly",
        )
        if self._checksum in CHECKSUM_OPTIONS:
            self.checksum_combo.set(self._checksum)
        else:
            self.checksum_combo.set(DEFAULT_CHECKSUM)
        self.checksum_combo.pack(fill=tk.X, anchor=tk.W, pady=(0, 6))
        self.checksum_combo.bind("<<ComboboxSelected>>", self._update_checksum_preview)

        preview_area = tk.Frame(checksum_tab, bg="#e6e6e6", relief=tk.SUNKEN, bd=1, height=72)
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

        notebook.select(0)

    @staticmethod
    def _format_repeat_interval(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        if number == int(number):
            return str(int(number))
        return str(number)

    def _get_repeat_interval(self):
        value = self.repeat_seconds_entry.get().strip()
        if not value:
            return 0.0
        try:
            return max(0.0, float(value))
        except ValueError:
            return 0.0

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
        self.home.update_send_sequence(
            self._row_index,
            new_index,
            name,
            sequence,
            periodic=self.periodic_var.get(),
            repeat_interval=self._get_repeat_interval(),
            checksum=self.checksum_combo.get(),
            display_mode=self.sequence_editor.get_display_mode(),
        )
        self._row_index = new_index

    def _on_ok(self):
        self._save_sequence()
        self.destroy()

    def _on_apply(self):
        self._save_sequence()

    def _on_delete(self):
        self.home.delete_send_sequence(self._row_index)
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    EditSendRequest(root, row_index=0, index="1", name="Test", sequence="2D 2D 2D 2D")
    root.mainloop()
