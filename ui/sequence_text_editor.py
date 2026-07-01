"""Pipe-delimited tk.Text sequence editor (Docklight-style typing space)."""

import tkinter as tk
from tkinter import ttk

from core.sequence_codec import (
    PLACEHOLDER_PATTERN,
    SequenceEncodeError,
    encode_sequence,
)

TEXT_FONT = ("Consolas", 11)
CELL_SEP = "|"


class SequenceTextEditor(tk.Frame):
    """Single Text field with | separators between byte cells."""

    def __init__(
        self,
        parent,
        sequence="",
        display_mode="HEX",
        on_change=None,
        on_mode_change=None,
    ):
        super().__init__(parent, bg="#d9d9d9")
        self._on_change = on_change
        self._on_mode_change = on_mode_change
        self._updating_mode = False
        self._tokens = []
        self._display_mode = (
            display_mode
            if display_mode in ("ASCII", "HEX", "Decimal", "Binary")
            else "HEX"
        )
        self._prev_mode = self._display_mode

        self._build_header()
        self._build_text_area()
        self.load_sequence(sequence)

        self.seq_text.bind("<Key>", self._handle_keypress)
        self.seq_text.bind("<Return>", self._block_newline)
        self.seq_text.bind("<KP_Enter>", self._block_newline)
        self.seq_text.bind("<KeyRelease>", self._on_text_changed)
        self.seq_text.bind("<ButtonRelease-1>", self._on_text_changed)

    def _build_header(self):
        header = tk.Frame(self, bg="#d9d9d9")
        header.pack(fill=tk.X, pady=(0, 2))

        tk.Label(header, text="2 - Sequence", width=12, anchor=tk.W, bg="#d9d9d9").pack(
            side=tk.LEFT
        )
        tk.Label(header, text="Edit Mode", bg="#d9d9d9").pack(side=tk.LEFT, padx=(0, 8))

        self.edit_mode = tk.StringVar(value=self._display_mode)
        for mode in ("ASCII", "HEX", "Decimal", "Binary"):
            ttk.Radiobutton(
                header,
                text=mode,
                variable=self.edit_mode,
                value=mode,
                command=self._on_edit_mode_changed,
            ).pack(side=tk.LEFT, padx=2)

        self.pos_label = tk.Label(header, text="Pos. 0 / 0", bg="#d9d9d9")
        self.pos_label.pack(side=tk.RIGHT)

    def _build_text_area(self):
        area = tk.Frame(self, bg="white", relief=tk.SUNKEN, bd=1, height=100)
        area.pack(fill=tk.X, pady=4)
        area.pack_propagate(False)

        self.seq_text = tk.Text(
            area,
            height=4,
            font=TEXT_FONT,
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.NONE,
            undo=True,
            padx=8,
            pady=8,
        )
        h_scroll = ttk.Scrollbar(area, orient=tk.HORIZONTAL, command=self.seq_text.xview)
        self.seq_text.configure(xscrollcommand=h_scroll.set)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.seq_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def get_display_mode(self):
        return self.edit_mode.get()

    def set_display_mode(self, mode, skip_global_sync=False):
        if self.edit_mode.get() == mode:
            return
        self._updating_mode = True
        self.edit_mode.set(mode)
        self._updating_mode = False
        self._on_edit_mode_changed(skip_global_sync=skip_global_sync)

    def load_sequence(self, sequence):
        sequence = sequence.strip()
        self._tokens = sequence.split() if sequence else []
        self._prev_mode = self.get_display_mode()
        self._update_text_box(self._prev_mode)
        self._update_position_label()

    def get_sequence_string(self):
        self._sync_tokens_from_text()
        return " ".join(self._tokens)

    def _notify_change(self):
        if self._on_change:
            self._on_change()

    def _token_to_byte(self, token):
        if PLACEHOLDER_PATTERN.match(token):
            return None
        if len(token) == 2 and all(ch in "0123456789ABCDEFabcdef" for ch in token):
            return int(token, 16)
        if token.isdigit():
            value = int(token)
            if 0 <= value <= 255:
                return value
        return None

    def _display_part_to_token(self, part, mode):
        # A lone space is a valid ASCII cell (byte 0x20); strip() would erase it.
        if mode == "ASCII" and part == " ":
            return "{:02X}".format(32)
        part = part.strip()
        if not part:
            return None
        if PLACEHOLDER_PATTERN.match(part):
            return part.upper()
        try:
            if mode == "ASCII":
                if len(part) == 1:
                    return "{:02X}".format(ord(part))
                # Non-printable bytes are shown as 2-digit hex in ASCII mode.
                if len(part) == 2 and all(ch in "0123456789ABCDEFabcdef" for ch in part):
                    return "{:02X}".format(int(part, 16))
                return None
            if mode == "HEX":
                return "{:02X}".format(int(part, 16))
            if mode == "Decimal":
                value = int(part, 10)
                if 0 <= value <= 255:
                    return "{:02X}".format(value)
                return None
            if mode == "Binary":
                return "{:02X}".format(int(part, 2))
        except ValueError:
            return None
        return None

    def _part_to_display(self, token, mode):
        if PLACEHOLDER_PATTERN.match(token):
            return token
        byte_val = self._token_to_byte(token)
        if byte_val is None:
            return token
        if mode == "HEX":
            return "{:02X}".format(byte_val)
        if mode == "Decimal":
            return str(byte_val)
        if mode == "Binary":
            return "{:08b}".format(byte_val)
        if 32 <= byte_val <= 126:
            return chr(byte_val)
        return "{:02X}".format(byte_val)

    def _sync_tokens_from_text(self):
        content = self.seq_text.get("1.0", tk.END)
        if content.endswith("\n"):
            content = content[:-1]
        if not content:
            self._tokens = []
            return

        parts = [part.strip() if part != " " else part for part in content.split(CELL_SEP) if part != ""]
        tokens = []
        for part in parts:
            token = self._display_part_to_token(part, self._prev_mode)
            if token:
                tokens.append(token)
        self._tokens = tokens

    def _update_text_box(self, mode):
        self.seq_text.delete("1.0", tk.END)
        if not self._tokens:
            return

        cells = [self._part_to_display(token, mode) for token in self._tokens]
        display_str = CELL_SEP.join(cells) + CELL_SEP
        self.seq_text.insert("1.0", display_str)

    def _current_cell_text(self):
        line_text = self.seq_text.get("1.0", tk.INSERT)
        last_sep = line_text.rfind(CELL_SEP)
        if last_sep == -1:
            return line_text
        return line_text[last_sep + 1 :]

    def _update_position_label(self):
        content = self.seq_text.get("1.0", tk.INSERT)
        before_cursor = content.split(CELL_SEP)
        current = max(1, len(before_cursor))
        self._sync_tokens_from_text()
        filled = len(self._tokens)
        self.pos_label.config(text="Pos. {} / {}".format(current, filled))

    def _max_chars_for_mode(self, mode):
        if mode == "Binary":
            return 8
        if mode == "Decimal":
            return 3
        if mode == "HEX":
            return 2
        return 1

    def _is_cell_complete(self, cell_text, mode):
        if PLACEHOLDER_PATTERN.match(cell_text):
            return True
        if not cell_text:
            return False
        if mode == "Decimal":
            return cell_text.isdigit()
        return len(cell_text) >= self._max_chars_for_mode(mode)

    def _cursor_offset(self):
        return len(self.seq_text.get("1.0", tk.INSERT))

    def _on_right_arrow(self):
        cell_text = self._current_cell_text()
        mode = self.get_display_mode()
        offset = self._cursor_offset()
        text = self.seq_text.get("1.0", "1.0 lineend")
        rest = text[offset:]
        before = self.seq_text.get("1.0", tk.INSERT)
        cell_start = before.rfind(CELL_SEP) + 1
        pos_in_cell = len(before) - cell_start

        if not self._is_cell_complete(cell_text, mode):
            if pos_in_cell < len(cell_text):
                self.seq_text.mark_set(tk.INSERT, "1.0+{}c".format(offset + 1))
            self._update_position_label()
            return

        if rest.startswith(CELL_SEP):
            self.seq_text.mark_set(tk.INSERT, "1.0+{}c".format(offset + len(CELL_SEP)))
        else:
            pipe_pos = rest.find(CELL_SEP)
            if pipe_pos >= 0:
                self.seq_text.mark_set(
                    tk.INSERT,
                    "1.0+{}c".format(offset + pipe_pos + len(CELL_SEP)),
                )
            else:
                self.seq_text.insert(tk.INSERT, CELL_SEP)

        self._update_position_label()

    def _on_left_arrow(self):
        before = self.seq_text.get("1.0", tk.INSERT)
        last_pipe = before.rfind(CELL_SEP)

        if last_pipe == -1:
            self.seq_text.mark_set(tk.INSERT, "1.0")
        elif len(before) <= last_pipe + 1:
            if last_pipe == 0:
                self.seq_text.mark_set(tk.INSERT, "1.0")
            else:
                prev_pipe = before.rfind(CELL_SEP, 0, last_pipe)
                self.seq_text.mark_set(tk.INSERT, "1.0+{}c".format(prev_pipe + 1))
        else:
            self.seq_text.mark_set(tk.INSERT, "1.0+{}c".format(last_pipe + 1))

        self._update_position_label()

    def _on_text_changed(self, _event=None):
        self._update_position_label()
        self._notify_change()

    def _block_newline(self, _event=None):
        return "break"

    def _handle_keypress(self, event):
        if event.keysym in ("Return", "KP_Enter"):
            return "break"

        if event.keysym == "Right":
            self._on_right_arrow()
            return "break"
        if event.keysym == "Left":
            self._on_left_arrow()
            return "break"

        if event.keysym in ("BackSpace", "Delete", "Up", "Down", "Home", "End"):
            return

        if event.state & 0x4:
            return

        if not event.char or not event.char.isprintable():
            return

        mode = self.get_display_mode()
        cell_text = self._current_cell_text()

        if PLACEHOLDER_PATTERN.match(cell_text):
            return "break"

        if mode == "ASCII":
            self.seq_text.insert(tk.INSERT, event.char + CELL_SEP)
            return "break"

        if mode == "HEX":
            if event.char.upper() not in "0123456789ABCDEF":
                return "break"
            if len(cell_text) == 1:
                self.seq_text.insert(tk.INSERT, event.char.upper() + CELL_SEP)
            else:
                self.seq_text.insert(tk.INSERT, event.char.upper())
            return "break"

        if mode == "Binary":
            if event.char not in "01":
                return "break"
            if len(cell_text) == 7:
                self.seq_text.insert(tk.INSERT, event.char + CELL_SEP)
            else:
                self.seq_text.insert(tk.INSERT, event.char)
            return "break"

        if mode == "Decimal":
            if event.char == " ":
                return "break"
            if event.char not in "0123456789":
                return "break"

            new_text = cell_text + event.char
            new_val = int(new_text)
            if new_val > 255:
                start_idx = "{}-{}c".format(tk.INSERT, len(cell_text))
                self.seq_text.delete(start_idx, tk.INSERT)
                self.seq_text.insert(tk.INSERT, "255" + CELL_SEP)
            elif len(new_text) == 3:
                self.seq_text.insert(tk.INSERT, event.char + CELL_SEP)
            else:
                self.seq_text.insert(tk.INSERT, event.char)
            return "break"

        return None

    def _on_edit_mode_changed(self, skip_global_sync=False):
        if self._updating_mode:
            return

        self._sync_tokens_from_text()
        new_mode = self.get_display_mode()
        self._update_text_box(new_mode)
        self._prev_mode = new_mode
        self._update_position_label()
        self._notify_change()

        if not skip_global_sync and self._on_mode_change:
            self._on_mode_change(new_mode)

    def get_sequence_bytes(self):
        sequence = self.get_sequence_string()
        if not sequence.strip():
            return b""
        try:
            return encode_sequence(sequence)
        except SequenceEncodeError:
            return None
