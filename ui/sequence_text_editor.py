"""Pipe-delimited tk.Text sequence editor (Docklight-style typing space).

Every byte is one cell, cells are separated by "|". All edits (typing, Delete,
Backspace, a selection, paste, cut) work on whole cells, so a byte can never be
merged with its neighbour or cut in half.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from core.sequence_codec import (
    PLACEHOLDER_BYTES,
    PLACEHOLDER_PATTERN,
    WILDCARD,
    WILDCARD_ASCII,
    SequenceEncodeError,
    encode_sequence,
)

WILDCARD_HINT = (
    "F7 (or ? in HEX/Decimal/Binary) inserts a ? byte: in a send sequence it is filled "
    "in when sending (e.g. the device address), in a receive sequence it matches any byte."
)

TEXT_FONT = ("Consolas", 11)
CELL_SEP = "|"
HEX_DIGITS = "0123456789ABCDEFabcdef"
DIGITS_FOR_MODE = {"HEX": "0123456789ABCDEF", "Decimal": "0123456789", "Binary": "01"}
PASTE_EXAMPLES = {
    "HEX": '"01 03 00 0A" or "0103000A"',
    "Decimal": '"1 3 0 10"',
    "Binary": '"00000001 00000011"',
}
# Ctrl+key combinations that are safe to leave to Tk (copy, paste, cut, undo, redo,
# select all). Others, such as Ctrl+T (swap characters) or Ctrl+D/Ctrl+K (delete),
# would edit the text around the cells and are blocked.
SAFE_CTRL_KEYS = {"c", "v", "x", "z", "y", "a", "insert", "slash"}


def _is_hex(text):
    return bool(text) and all(ch in HEX_DIGITS for ch in text)


def check_sequence_fields(name, editor, rows, row_index, kind):
    """Problem with a sequence dialog's name and bytes, or None if it can be saved.

    rows are the sequence rows of the same list (send or receive); row_index is the
    row being edited, which may keep its own name.
    """
    if not name:
        return "Enter a name for the {} sequence.".format(kind)
    wanted = name.casefold()
    for index, row in enumerate(rows):
        if index != row_index and str(row[1]).strip().casefold() == wanted:
            return ('There is already a {} sequence called "{}" (number {}). Scripts find '
                    "sequences by name, so every name must be different.").format(
                        kind, row[1], index + 1)
    invalid = editor.get_invalid_cells()
    if invalid:
        return "These values are not valid {} bytes: {}".format(
            editor.get_display_mode(), ", ".join(invalid[:8]))
    if not editor.get_sequence_string().strip():
        return "The sequence is empty. Enter at least one byte."
    return None


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
        self._invalid_cells = []
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
        self.seq_text.bind("<<Paste>>", self._on_paste)
        self.seq_text.bind("<<Cut>>", self._on_cut)
        self.seq_text.bind("<<PasteSelection>>", lambda _event: "break")
        self.seq_text.bind("<<Clear>>", lambda _event: "break")

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
        tk.Label(self, text=WILDCARD_HINT, bg="#d9d9d9", fg="#555555", font=("Segoe UI", 8),
                 anchor=tk.W, justify=tk.LEFT, wraplength=660).pack(fill=tk.X)

    # ------------------------------------------------------------------ public

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

    def get_invalid_cells(self):
        """Cells that are not a valid byte in the current edit mode (e.g. "1G")."""
        self._sync_tokens_from_text()
        return list(self._invalid_cells)

    def get_sequence_bytes(self):
        sequence = self.get_sequence_string()
        if not sequence.strip():
            return b""
        try:
            return encode_sequence(sequence)
        except SequenceEncodeError:
            return None

    # ------------------------------------------------------- cells <-> tokens

    def _notify_change(self):
        if self._on_change:
            self._on_change()

    def _token_to_byte(self, token):
        if PLACEHOLDER_PATTERN.match(token):
            return None
        if len(token) == 2 and _is_hex(token):
            return int(token, 16)
        if token.isdigit():
            value = int(token)
            if 0 <= value <= 255:
                return value
        return None

    def _part_to_tokens(self, part, mode):
        """Tokens for one cell (or one pasted word), or None if it is not valid.

        A HEX cell of 4, 6, ... digits ("0103") is split into bytes, and a Binary
        cell of 16, 24, ... bits likewise, so nothing is merged into one big value.
        """
        if mode == "ASCII" and part == " ":
            return ["20"]
        part = part.strip()
        if not part:
            return []
        if part == WILDCARD_ASCII or (part == WILDCARD and mode != "ASCII"):
            return [WILDCARD]
        if PLACEHOLDER_PATTERN.match(part):
            upper = part.upper()
            return [upper] if upper in PLACEHOLDER_BYTES else None

        if mode == "ASCII":
            if len(part) == 1:
                return ["{:02X}".format(ord(part))] if ord(part) <= 255 else None
            # Non-printable bytes (and "|") are shown as 2-digit hex in ASCII mode.
            if len(part) == 2 and _is_hex(part):
                return [part.upper()]
            return None
        if mode == "HEX":
            if not _is_hex(part):
                return None
            if len(part) == 1:
                return ["0" + part.upper()]
            if len(part) % 2:
                return None
            return [part[i:i + 2].upper() for i in range(0, len(part), 2)]
        if mode == "Decimal":
            if all(ch in "0123456789" for ch in part) and int(part) <= 255:
                return ["{:02X}".format(int(part))]
            return None
        if mode == "Binary":
            if not all(ch in "01" for ch in part):
                return None
            if len(part) <= 8:
                return ["{:02X}".format(int(part, 2))]
            if len(part) % 8:
                return None
            return ["{:02X}".format(int(part[i:i + 8], 2)) for i in range(0, len(part), 8)]
        return None

    def _part_to_display(self, token, mode):
        if token == WILDCARD:
            return WILDCARD_ASCII if mode == "ASCII" else WILDCARD
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
        # "|" is the cell separator, so that byte is shown as 7C like non-printables.
        if 32 <= byte_val <= 126 and chr(byte_val) != CELL_SEP:
            return chr(byte_val)
        return "{:02X}".format(byte_val)

    def _sync_tokens_from_text(self):
        tokens = []
        invalid = []
        for part in self._text().split(CELL_SEP):
            if part == "":
                continue
            result = self._part_to_tokens(part, self._prev_mode)
            if result is None:
                invalid.append(part.strip() or part)
            else:
                tokens.extend(result)
        self._tokens = tokens
        self._invalid_cells = invalid

    def _update_text_box(self, mode):
        self.seq_text.delete("1.0", tk.END)
        if not self._tokens:
            return

        cells = [self._part_to_display(token, mode) for token in self._tokens]
        display_str = CELL_SEP.join(cells) + CELL_SEP
        self.seq_text.insert("1.0", display_str)

    # ---------------------------------------------------------- text helpers

    def _text(self):
        return self.seq_text.get("1.0", "end-1c")

    @staticmethod
    def _index(offset):
        return "1.0+{}c".format(offset)

    def _cursor_offset(self):
        return len(self.seq_text.get("1.0", tk.INSERT))

    def _set_cursor(self, offset):
        self.seq_text.mark_set(tk.INSERT, self._index(offset))

    @staticmethod
    def _cell_span(text, offset):
        """(start, end) of the cell around offset; end is before its "|"."""
        start = text.rfind(CELL_SEP, 0, offset) + 1
        end = text.find(CELL_SEP, offset)
        if end == -1:
            end = len(text)
        return start, end

    def _current_cell_text(self):
        text = self._text()
        offset = self._cursor_offset()
        start, _end = self._cell_span(text, offset)
        return text[start:offset]

    def _update_position_label(self):
        content = self.seq_text.get("1.0", tk.INSERT)
        current = max(1, len(content.split(CELL_SEP)))
        self._sync_tokens_from_text()
        self.pos_label.config(text="Pos. {} / {}".format(current, len(self._tokens)))

    def _max_chars_for_mode(self, mode):
        if mode == "Binary":
            return 8
        if mode == "Decimal":
            return 3
        if mode == "HEX":
            return 2
        return 1

    def _is_cell_complete(self, cell_text, mode):
        if cell_text == WILDCARD_ASCII or (cell_text == WILDCARD and mode != "ASCII"):
            return True
        if PLACEHOLDER_PATTERN.match(cell_text):
            return True
        if not cell_text:
            return False
        if mode == "ASCII":
            return True
        if mode == "Decimal":
            # Complete at 3 digits, or when another digit would go over 255.
            if not cell_text.isdigit():
                return True
            return len(cell_text) >= 3 or int(cell_text) * 10 > 255
        return len(cell_text) >= self._max_chars_for_mode(mode)

    # ------------------------------------------------------- cell operations

    def _delete_selection(self):
        """Delete every cell touched by the selection. True if something was selected."""
        try:
            first = len(self.seq_text.get("1.0", "sel.first"))
            last = len(self.seq_text.get("1.0", "sel.last"))
        except tk.TclError:
            return False
        self.seq_text.tag_remove("sel", "1.0", tk.END)
        if first >= last:
            return False
        text = self._text()
        if text[first] == CELL_SEP:
            first += 1
        if first >= last:
            self._set_cursor(first)
            return True
        start, _ = self._cell_span(text, first)
        _, end = self._cell_span(text, last - 1)
        if end < len(text):
            end += 1  # its "|"
        self.seq_text.delete(self._index(start), self._index(end))
        self._set_cursor(start)
        return True

    def _open_cell_at(self, offset):
        """Make an empty cell at offset (before the cell starting there)."""
        self.seq_text.insert(self._index(offset), CELL_SEP)
        self._set_cursor(offset)

    def _finish_cell(self):
        """Close the cell at the cursor and move to the start of the next one."""
        text = self._text()
        offset = self._cursor_offset()
        if offset < len(text) and text[offset] == CELL_SEP:
            self._set_cursor(offset + 1)
        else:
            self.seq_text.insert(self._index(offset), CELL_SEP)
            self._set_cursor(offset + 1)

    def _prepare_new_cell(self):
        """Put the cursor at a cell boundary, ready to insert whole cells ("xx|")."""
        self._delete_selection()
        text = self._text()
        offset = self._cursor_offset()
        start, end = self._cell_span(text, offset)
        if start < offset < end:
            self._set_cursor(start)          # inside a cell: insert before it
        elif offset == end and end > start:
            self._finish_cell()              # right after a cell's text

    def _prepare_typing(self, mode):
        """Get ready to type a digit; returns the text already in the cell."""
        self._delete_selection()
        text = self._text()
        offset = self._cursor_offset()
        start, end = self._cell_span(text, offset)
        if offset < end:
            # Bytes after the cursor in this cell: start a new cell before it
            # instead of typing into (and changing) the existing byte.
            self._open_cell_at(start)
            return ""
        cell = text[start:offset]
        if cell and self._is_cell_complete(cell, mode):
            self._finish_cell()
            offset = self._cursor_offset()
            if offset < len(self._text()):
                self._open_cell_at(offset)
            return ""
        return cell

    # ------------------------------------------------------------ key events

    def _on_right_arrow(self):
        offset = self._cursor_offset()
        text = self._text()
        rest = text[offset:]

        # At the end of the text: close the typed cell (e.g. "7" in Decimal mode).
        if not rest:
            if text and not text.endswith(CELL_SEP):
                self.seq_text.insert(tk.INSERT, CELL_SEP)
                self._update_position_label()
                self._notify_change()
            return

        pipe_pos = rest.find(CELL_SEP)
        if pipe_pos >= 0:
            self._set_cursor(offset + pipe_pos + len(CELL_SEP))
        else:
            self.seq_text.mark_set(tk.INSERT, "1.0 lineend")
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
                self._set_cursor(prev_pipe + 1)
        else:
            self._set_cursor(last_pipe + 1)

        self._update_position_label()

    def _on_backspace(self):
        if self._delete_selection():
            self._update_position_label()
            self._notify_change()
            return

        before = self.seq_text.get("1.0", tk.INSERT)
        offset = len(before)
        if offset == 0:
            return

        if before.endswith(CELL_SEP):
            # Right after a cell: delete that whole cell.
            pipe_pos = offset - len(CELL_SEP)
            prev_pipe = before.rfind(CELL_SEP, 0, pipe_pos)
            cell_start = prev_pipe + 1
            self.seq_text.delete(self._index(cell_start), self._index(offset))
            self._set_cursor(cell_start)
            self._update_position_label()
            self._notify_change()
            return

        last_pipe = before.rfind(CELL_SEP)
        cell_start = last_pipe + 1
        if offset <= cell_start:
            self._update_position_label()
            return

        mode = self.get_display_mode()
        cell_text = before[cell_start:]
        next_char = self.seq_text.get(self._index(offset), self._index(offset + 1))

        if mode != "ASCII" and next_char == CELL_SEP and len(cell_text) == 1:
            # Last digit of a cell: remove the cell with its "|".
            self.seq_text.delete(self._index(cell_start), self._index(offset + 1))
            self._set_cursor(cell_start)
        elif (
            mode != "ASCII"
            and not PLACEHOLDER_PATTERN.match(cell_text)
            and cell_text != WILDCARD
            and len(cell_text) > 1
        ):
            self.seq_text.delete(self._index(offset - 1), tk.INSERT)
        else:
            self.seq_text.delete(self._index(cell_start), tk.INSERT)

        self._update_position_label()
        self._notify_change()

    def _on_delete(self):
        """Delete key: remove the byte (cell) to the right of the cursor."""
        if not self._delete_selection():
            text = self._text()
            offset = self._cursor_offset()
            if offset < len(text) and text[offset] == CELL_SEP:
                offset += 1
            if offset >= len(text):
                return
            start, end = self._cell_span(text, offset)
            if end < len(text):
                end += 1  # its "|"
            self.seq_text.delete(self._index(start), self._index(end))
            self._set_cursor(start)
        self._update_position_label()
        self._notify_change()

    def _on_text_changed(self, _event=None):
        # In ASCII mode, snap the cursor to the left of a character.
        if self.get_display_mode() == "ASCII":
            left_char = self.seq_text.get("insert - 1c")
            if left_char and left_char != CELL_SEP and left_char != "\n":
                current_pos = self.seq_text.index(tk.INSERT)
                self.seq_text.mark_set(tk.INSERT, "{} - 1c".format(current_pos))

        self._update_position_label()
        self._notify_change()

    def _block_newline(self, _event=None):
        return "break"

    def _handle_keypress(self, event):
        if event.keysym in ("Return", "KP_Enter", "Tab"):
            return "break"

        if event.keysym == "Right":
            self._on_right_arrow()
            return "break"
        if event.keysym == "Left":
            self._on_left_arrow()
            return "break"
        if event.keysym == "BackSpace":
            self._on_backspace()
            return "break"
        if event.keysym == "Delete":
            self._on_delete()
            return "break"

        mode = self.get_display_mode()
        if event.keysym == "F7" or (event.char == WILDCARD and mode != "ASCII"):
            self._insert_wildcard(mode)
            return "break"

        if event.keysym in ("Up", "Down", "Home", "End"):
            return None

        if event.state & 0x4:
            # Ctrl+C/V/X/Z... are handled by Tk (paste and cut through the
            # <<Paste>>/<<Cut>> handlers below); other Ctrl keys would edit text.
            return None if event.keysym.lower() in SAFE_CTRL_KEYS else "break"

        if not event.char or not event.char.isprintable():
            return None

        if mode == "ASCII":
            self._type_ascii(event.char)
        else:
            self._type_digit(event.char, mode)
        self._update_position_label()
        self._notify_change()
        return "break"

    def _type_ascii(self, char):
        if ord(char) > 255:
            self.bell()
            return
        self._prepare_new_cell()
        shown = self._part_to_display("{:02X}".format(ord(char)), "ASCII")
        self.seq_text.insert(tk.INSERT, shown + CELL_SEP)

    def _type_digit(self, char, mode):
        if char in (" ", ","):
            # Space or comma finishes the cell being typed (e.g. "7" in Decimal).
            text = self._text()
            offset = self._cursor_offset()
            start, end = self._cell_span(text, offset)
            if offset == end and end > start:
                self._finish_cell()
            return

        char = char.upper()
        if char not in DIGITS_FOR_MODE[mode]:
            self.bell()
            return

        cell = self._prepare_typing(mode)
        new_text = cell + char
        if mode == "Decimal" and int(new_text) > 255:
            self.bell()  # a byte is 0-255; the cell keeps what was typed
            return
        self.seq_text.insert(tk.INSERT, char)
        if self._is_cell_complete(new_text, mode):
            self._finish_cell()

    def _insert_wildcard(self, mode):
        """Insert a ? byte as a cell of its own at the cursor."""
        self._prepare_new_cell()
        shown = WILDCARD_ASCII if mode == "ASCII" else WILDCARD
        self.seq_text.insert(tk.INSERT, shown + CELL_SEP)
        self._update_position_label()
        self._notify_change()

    # ------------------------------------------------------------ clipboard

    def _pasted_cells(self, text, mode):
        """Display cells for pasted text. Raises ValueError if a value is not valid."""
        if mode == "ASCII":
            cells = []
            for char in text:
                if ord(char) > 255:
                    raise ValueError('"{}" is not a one-byte character.'.format(char))
                cells.append(self._part_to_display("{:02X}".format(ord(char)), "ASCII"))
            return cells

        cleaned = text
        for separator in (CELL_SEP, ",", ";", "\t", "\r", "\n"):
            cleaned = cleaned.replace(separator, " ")
        cells = []
        for word in cleaned.split():
            value = word
            if mode == "HEX" and value.lower().startswith("0x"):
                value = value[2:]
            if mode == "Binary" and value.lower().startswith("0b"):
                value = value[2:]
            tokens = self._part_to_tokens(value, mode)
            if not tokens:
                raise ValueError('"{}" is not a valid {} value.'.format(word, mode))
            cells.extend(self._part_to_display(token, mode) for token in tokens)
        return cells

    def _on_paste(self, _event=None):
        try:
            clipboard = self.seq_text.clipboard_get()
        except tk.TclError:
            return "break"
        mode = self.get_display_mode()
        try:
            cells = self._pasted_cells(clipboard, mode)
        except ValueError as error:
            example = PASTE_EXAMPLES.get(mode)
            hint = "\n\nIn {} mode paste values such as {}.".format(mode, example) if example else ""
            messagebox.showwarning("Paste", "Nothing was pasted. {}{}".format(error, hint),
                                   parent=self.winfo_toplevel())
            return "break"
        if cells:
            self._prepare_new_cell()
            self.seq_text.insert(tk.INSERT, CELL_SEP.join(cells) + CELL_SEP)
            self._update_position_label()
            self._notify_change()
        return "break"

    def _on_cut(self, _event=None):
        try:
            selected = self.seq_text.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self.seq_text.clipboard_clear()
        self.seq_text.clipboard_append(selected)
        self._delete_selection()
        self._update_position_label()
        self._notify_change()
        return "break"

    # ----------------------------------------------------------- edit mode

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
