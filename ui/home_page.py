"""Docklight home page UI."""

from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk

from core.checksum import ChecksumError, append_checksum
from core.comm_display import (
    format_comm_segments,
    format_line_ending_segments,
    iter_comm_lines,
)
from core.comm_service import CommService, ErrorEvent, RxEvent, TxEvent
from core.checksum_rules import DEFAULT_CHECKSUM
from core.receive_actions import (
    ReceiveActionConfig,
    default_comment_text,
    parse_receive_action,
    receive_action_fields,
)
from core.receive_matcher import find_matches
from core.sequence_codec import (
    PLACEHOLDER_PATTERN,
    SequenceEncodeError,
    encode_sequence,
    format_sequence_display,
)
from project_settings import ProjectSettings
from route.routes import Routes
from ui.edit_receive_sequence import DEFAULT_CHECKSUM_DETECT


class HomePage(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EC Docklight V2.3")
        self.geometry("1100x650")
        self.minsize(900, 550)
        self.configure(bg="#d9d9d9")

        self._send_rows = []
        self._receive_rows = []
        self._send_buttons = {}
        self._repeat_after_ids = {}
        self._global_display_mode = "HEX"
        self._updating_display_mode = False
        self.project_settings = ProjectSettings()
        self._communication_open = False
        self._comm_texts = {}
        self.comm_service = CommService(self._on_comm_event)
        self.routes = Routes(self)

        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()
        self._build_layout()
        self.routes.bind()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after_idle(self._refresh_send_buttons)

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        for label in ("File", "Edit", "Run", "Tools", "Scripting", "Help"):
            menu = tk.Menu(menubar, tearoff=0)
            menu.add_command(label="{} item".format(label))
            menubar.add_cascade(label=label, menu=menu)

    def _build_toolbar(self):
        toolbar = tk.Frame(self, bg="#d4d0c8", relief=tk.RAISED, bd=1)
        toolbar.pack(fill=tk.X)

        play_btn = self._toolbar_icon_button(
            toolbar,
            self._draw_play_icon,
            self.routes.start_communication,
        )
        play_btn.pack(side=tk.LEFT, padx=(6, 0), pady=2)

        stop_btn = self._toolbar_icon_button(
            toolbar,
            self._draw_stop_icon,
            self.routes.stop_communication,
        )
        stop_btn.pack(side=tk.LEFT, padx=(2, 6), pady=2)

    def _toolbar_icon_button(self, parent, draw_icon, command):
        normal_bg = "#d4d0c8"
        hover_bg = "#b8b4ac"

        frame = tk.Frame(parent, bg=normal_bg, cursor="hand2")
        canvas = tk.Canvas(
            frame,
            width=24,
            height=24,
            bg=normal_bg,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack()
        draw_icon(canvas)

        def on_enter(_event):
            frame.configure(bg=hover_bg)
            canvas.configure(bg=hover_bg)

        def on_leave(_event):
            frame.configure(bg=normal_bg)
            canvas.configure(bg=normal_bg)

        def on_click(_event):
            command()

        for widget in (frame, canvas):
            widget.bind("<Button-1>", on_click)
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)

        return frame

    @staticmethod
    def _draw_play_icon(canvas):
        canvas.create_polygon(
            8, 6, 8, 18, 18, 12, fill="#0066cc", outline="#003d7a", width=1
        )

    @staticmethod
    def _draw_stop_icon(canvas):
        canvas.create_rectangle(
            8, 8, 16, 16, fill="#808080", outline="#505050", width=1
        )

    def _build_status_bar(self):
        status_frame = tk.Frame(self, bg="#d9d9d9")
        status_frame.pack(fill=tk.X, padx=8, pady=(2, 0))

        self.port_status = tk.StringVar(value="Communication port closed")
        tk.Label(
            status_frame,
            textvariable=self.port_status,
            bg="#d9d9d9",
            anchor=tk.W,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT)

    def _on_close(self):
        self.stop_repeat_senders()
        self.comm_service.disconnect()
        self.destroy()

    def _on_comm_event(self, event):
        self.after(0, lambda evt=event: self._handle_comm_event(evt))

    def _handle_comm_event(self, event):
        if isinstance(event, TxEvent):
            self._append_comm_data(event.data, "TX")
        elif isinstance(event, RxEvent):
            matches = find_matches(
                event.data, self._receive_rows, self._normalize_receive_row
            )
            self._append_comm_data(event.data, "RX")
            self._handle_receive_matches(matches)
        elif isinstance(event, ErrorEvent):
            self._append_comm_line("[ERR] {}".format(event.message), tag="error", direction="RX")
            self.routes.stop_communication()

    @staticmethod
    def _format_comm_timestamp():
        now = datetime.now()
        return "{} {}.{:03d}".format(
            "{}/{}/{}".format(now.month, now.day, now.year),
            now.strftime("%H:%M:%S"),
            now.microsecond // 1000,
        )

    @staticmethod
    def _configure_comm_tags(text_widget):
        text_widget.tag_configure("meta", foreground="#008000")
        text_widget.tag_configure("rx_data", foreground="#8B0000")
        text_widget.tag_configure("tx_data", foreground="#0000FF")
        text_widget.tag_configure("separator", foreground="#008000")
        text_widget.tag_configure("status", foreground="#008000")
        text_widget.tag_configure("error", foreground="#CC0000")

    def _insert_comm_header(self, text_widget, direction):
        timestamp = self._format_comm_timestamp()
        text_widget.insert(tk.END, timestamp + " ", "meta")
        text_widget.insert(tk.END, "[{}]".format(direction), "meta")
        text_widget.insert(tk.END, " - ", "meta")

    def _insert_comm_payload(self, text_widget, data, mode, data_tag):
        for text, segment_tag in format_comm_segments(data, mode):
            widget_tag = "meta" if segment_tag == "control" else data_tag
            text_widget.insert(tk.END, text, widget_tag)

    def _insert_comm_line_ending(self, text_widget, ending):
        for text, _segment_tag in format_line_ending_segments(ending):
            text_widget.insert(tk.END, text, "meta")

    def _append_comm_line(self, line, tag="status", direction="RX"):
        if not self._comm_texts:
            return

        for text_widget in self._comm_texts.values():
            self._insert_comm_header(text_widget, direction)
            text_widget.insert(tk.END, line, tag)
            text_widget.insert(tk.END, "\n")
            text_widget.see(tk.END)

    def _append_comm_data(self, data, direction, label=""):
        if not self._comm_texts:
            return

        lines = list(iter_comm_lines(data))
        if not lines and data:
            lines = [(data, b"")]

        data_tag = "rx_data" if direction == "RX" else "tx_data"

        for tab_name, text_widget in self._comm_texts.items():
            for index, (line_bytes, ending) in enumerate(lines):
                if index == 0:
                    self._insert_comm_header(text_widget, direction)

                self._insert_comm_payload(text_widget, line_bytes, tab_name, data_tag)
                self._insert_comm_line_ending(text_widget, ending)

                if label and index == 0:
                    text_widget.insert(tk.END, "  {}".format(label), "meta")

                text_widget.insert(tk.END, "\n")

            text_widget.see(tk.END)

    def _append_comm_comment(self, text, include_timestamp=False, extra_line_break=False):
        if not self._comm_texts or not text:
            return

        line = text
        if include_timestamp:
            line = "{}  {}".format(line, self._format_comm_timestamp())

        for text_widget in self._comm_texts.values():
            self._insert_comm_header(text_widget, "RX")
            text_widget.insert(tk.END, line, "meta")
            text_widget.insert(tk.END, "\n")
            if extra_line_break:
                text_widget.insert(tk.END, "\n")
            text_widget.see(tk.END)

    def _handle_receive_matches(self, matches):
        for match in matches:
            if match.checksum_ok is False:
                self._append_comm_line(
                    'Checksum wrong for receive sequence "{}".'.format(match.name)
                )
                continue

            row = self.get_receive_row(match.row_index)
            action = parse_receive_action(row, match.name)
            if self._run_receive_action(match, action):
                self._append_comm_line(
                    'Communication stopped by receive sequence "{}".'.format(
                        match.name
                    )
                )
                self.routes.stop_communication()
                break

    def _run_receive_action(self, match, action: ReceiveActionConfig) -> bool:
        if action.action_type == "Comment":
            comment = action.comment_text.strip() or default_comment_text(match.name)
            self._append_comm_comment(
                comment,
                include_timestamp=action.comment_timestamp,
                extra_line_break=action.comment_line_break,
            )
            return False

        if action.action_type == "Trigger" and action.snapshot_trigger:
            self._append_comm_line(
                'Snapshot triggered by receive sequence "{}".'.format(match.name)
            )
            return False

        if action.action_type == "Stop" and action.stop_communication:
            return True

        if action.action_type == "Answer":
            self._send_answer_sequence(action.answer_send_index, match.name)

        return False

    def _send_answer_sequence(self, send_index, trigger_name=""):
        if not self.comm_service.is_connected():
            return

        if not (0 <= send_index < len(self._send_rows)):
            self._append_comm_line(
                'Automatic answer for "{}" failed: invalid send sequence.'.format(
                    trigger_name
                )
            )
            return

        send_row = self.get_send_row(send_index)
        name = send_row[1]
        sequence = send_row[2]
        checksum_rule = send_row[4]

        for token in sequence.split():
            if PLACEHOLDER_PATTERN.match(token):
                self._append_comm_line(
                    'Automatic answer for "{}" failed: send sequence "{}" '
                    "contains wildcards.".format(trigger_name, name)
                )
                return

        try:
            payload = encode_sequence(sequence)
            payload = append_checksum(payload, checksum_rule)
        except (SequenceEncodeError, ChecksumError) as exc:
            self._append_comm_line(
                'Automatic answer for "{}" failed: {}'.format(trigger_name, exc)
            )
            return

        try:
            self.comm_service.send_bytes(payload, label=name)
        except Exception as exc:
            self._append_comm_line(
                'Automatic answer for "{}" failed: {}'.format(trigger_name, exc)
            )

    def apply_project_settings(self, settings):
        was_open = self.comm_service.is_connected()
        if was_open:
            self.routes.stop_communication()

        self.project_settings.update(settings)
        self.com_port.set(self.project_settings.get("channel"))

        if was_open:
            self.routes.start_communication()
        elif self._communication_open:
            self.port_status.set(
                "Communication port {} open".format(self.project_settings.get("channel"))
            )

    def _build_layout(self):
        top_bar = tk.Frame(self, bg="#d9d9d9")
        top_bar.pack(fill=tk.X, padx=8, pady=(4, 0))

        tk.Label(top_bar, text="", bg="#d9d9d9").pack(side=tk.LEFT, expand=True)

        com_frame = tk.Frame(top_bar, bg="#d9d9d9")
        com_frame.pack(side=tk.RIGHT)
        self.com_port = tk.StringVar(value=self.project_settings.get("channel"))
        ttk.Button(
            com_frame,
            textvariable=self.com_port,
            width=10,
            command=self.routes.open_project_settings,
        ).pack()

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left_pane = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(left_pane, weight=1)

        send_frame = self._build_send_sequences()
        receive_frame = self._build_receive_sequences()
        left_pane.add(send_frame, weight=1)
        left_pane.add(receive_frame, weight=1)

        comm_frame = self._build_communication_panel()
        paned.add(comm_frame, weight=2)

    def _build_send_sequences(self):
        frame = ttk.LabelFrame(self, text="", padding=4)

        header = tk.Frame(frame, bg="#d9d9d9")
        header.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            header,
            text="Send Sequences",
            bg="#d9d9d9",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(header, text="Add Sequence", command=self.routes.add_send_sequence).pack(
            side=tk.RIGHT
        )

        table_frame = tk.Frame(frame)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("send", "name", "sequence")
        self.send_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=8
        )
        self.send_tree.heading("send", text="Send")
        self.send_tree.heading("name", text="Name")
        self.send_tree.heading("sequence", text="Sequence")
        self.send_tree.column("send", width=50, anchor=tk.CENTER, stretch=False)
        self.send_tree.column("name", width=120, anchor=tk.W)
        self.send_tree.column("sequence", width=200, anchor=tk.W)

        self._send_rows = [
            ("", "TestData", "7 8 9 4 5", False, DEFAULT_CHECKSUM, "HEX"),
            ("", "Ping", "2D 2D 2D 2D", False, DEFAULT_CHECKSUM, "HEX"),
            ("", "Pong", "50 6F 6E 67", False, DEFAULT_CHECKSUM, "HEX"),
        ]
        for row in self._send_rows:
            self.send_tree.insert("", tk.END, values=self._send_row_display_values(row))

        def on_yscroll(*args):
            scrollbar.set(*args)
            self.after_idle(self._refresh_send_buttons)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=on_yscroll)
        self.send_tree.configure(yscrollcommand=on_yscroll)

        self.send_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.send_tree.bind("<Configure>", self._on_send_tree_layout, add="+")
        self.send_tree.bind("<ButtonRelease-1>", self._on_send_tree_click, add="+")

        return frame

    def _on_send_tree_layout(self, _event):
        self.after_idle(self._refresh_send_buttons)

    def _on_send_tree_click(self, event):
        if self.send_tree.identify_column(event.x) == "#1":
            return "break"

    def _refresh_send_buttons(self):
        for button in self._send_buttons.values():
            button.destroy()
        self._send_buttons.clear()

        for item in self.send_tree.get_children():
            bbox = self.send_tree.bbox(item, column="send")
            if not bbox:
                continue

            x, y, width, height = bbox
            button = ttk.Button(
                self.send_tree,
                text="→",
                width=2,
                command=lambda row_id=item: self._send_sequence(row_id),
            )
            button.place(x=x, y=y, width=max(width, 28), height=height)
            self._send_buttons[item] = button

    def _send_sequence(self, row_id):
        if not self.comm_service.is_connected():
            messagebox.showwarning(
                "Communication",
                "Start communication before sending a sequence.",
                parent=self,
            )
            return

        row_index = self.send_tree.index(row_id)
        send_row = self.get_send_row(row_index)
        if send_row[3] and send_row[6] > 0:
            self._start_repeat_for_row(row_index, send_immediately=True)
            return

        self._stop_repeat_for_row(row_index)
        self._send_sequence_by_index(row_index)

    def _send_sequence_by_index(self, row_index, from_repeat=False):
        if not self.comm_service.is_connected():
            return False
        if not (0 <= row_index < len(self._send_rows)):
            return False

        send_row = self.get_send_row(row_index)
        name = send_row[1]
        sequence = send_row[2]
        checksum_rule = send_row[4]

        try:
            payload = encode_sequence(sequence)
            payload = append_checksum(payload, checksum_rule)
        except (SequenceEncodeError, ChecksumError) as exc:
            if from_repeat:
                self._append_comm_line(
                    'Periodic send for "{}" failed: {}'.format(name, exc)
                )
            else:
                messagebox.showerror(
                    "Send Sequence",
                    "Could not encode sequence:\n{}".format(exc),
                    parent=self,
                )
            return False

        try:
            self.comm_service.send_bytes(payload, label=name)
        except Exception as exc:
            if from_repeat:
                self._append_comm_line(
                    'Periodic send for "{}" failed: {}'.format(name, exc)
                )
            else:
                messagebox.showerror(
                    "Send Sequence",
                    "Could not send sequence:\n{}".format(exc),
                    parent=self,
                )
            return False

        return True

    def _stop_repeat_for_row(self, row_index):
        after_id = self._repeat_after_ids.pop(row_index, None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass

    def _start_repeat_for_row(self, row_index, send_immediately=False):
        self._stop_repeat_for_row(row_index)

        if not self.comm_service.is_connected():
            return

        send_row = self.get_send_row(row_index)
        if not send_row[3] or send_row[6] <= 0:
            if send_immediately:
                self._send_sequence_by_index(row_index)
            return

        if send_immediately and not self._send_sequence_by_index(row_index):
            return

        interval_ms = max(100, int(send_row[6] * 1000))
        after_id = self.after(
            interval_ms,
            lambda: self._tick_repeat_send(row_index, interval_ms),
        )
        self._repeat_after_ids[row_index] = after_id

    def stop_repeat_senders(self):
        for after_id in self._repeat_after_ids.values():
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._repeat_after_ids.clear()

    def _tick_repeat_send(self, row_index, interval_ms):
        self._repeat_after_ids.pop(row_index, None)
        if not self.comm_service.is_connected():
            return

        if not (0 <= row_index < len(self._send_rows)):
            return

        send_row = self.get_send_row(row_index)
        if not send_row[3] or send_row[6] <= 0:
            return

        self._send_sequence_by_index(row_index, from_repeat=True)

        if not self.comm_service.is_connected():
            return

        after_id = self.after(
            interval_ms,
            lambda: self._tick_repeat_send(row_index, interval_ms),
        )
        self._repeat_after_ids[row_index] = after_id

    def get_display_mode(self):
        return self._global_display_mode

    def apply_global_display_mode(self, mode):
        if mode not in ("ASCII", "HEX", "Decimal", "Binary"):
            return
        if self._updating_display_mode:
            return

        self._updating_display_mode = True
        try:
            self._global_display_mode = mode

            for index, row in enumerate(self._send_rows):
                normalized = list(self._normalize_send_row(row))
                normalized[5] = mode
                self._send_rows[index] = tuple(normalized)

            for index, row in enumerate(self._receive_rows):
                normalized = list(self._normalize_receive_row(row))
                normalized[5] = mode
                self._receive_rows[index] = tuple(normalized)

            self._refresh_send_tree()
            self._refresh_receive_tree()

            if hasattr(self, "_comm_notebook"):
                modes = ("ASCII", "HEX", "Decimal", "Binary")
                selected = self._comm_notebook.index(self._comm_notebook.select())
                if modes[selected] != mode:
                    self._comm_notebook.select(modes.index(mode))

            dialog = getattr(self.routes, "_open_dialog", None)
            if (
                dialog is not None
                and dialog.winfo_exists()
                and hasattr(dialog, "update_display_mode_from_global")
            ):
                dialog.update_display_mode_from_global(mode)
        finally:
            self._updating_display_mode = False

    def _on_comm_tab_changed(self, _event):
        modes = ("ASCII", "HEX", "Decimal", "Binary")
        selected = self._comm_notebook.index(self._comm_notebook.select())
        self.apply_global_display_mode(modes[selected])

    def get_send_row(self, index):
        if not (0 <= index < len(self._send_rows)):
            return ("", "", "", False, DEFAULT_CHECKSUM, "HEX", 0.0)
        return self._normalize_send_row(self._send_rows[index])

    def _normalize_send_row(self, row):
        send = row[0] if len(row) > 0 else ""
        name = row[1] if len(row) > 1 else ""
        sequence = row[2] if len(row) > 2 else ""
        periodic = row[3] if len(row) > 3 else False
        checksum = row[4] if len(row) > 4 else DEFAULT_CHECKSUM
        display_mode = row[5] if len(row) > 5 else "HEX"
        repeat_interval = row[6] if len(row) > 6 else 0.0
        try:
            repeat_interval = float(repeat_interval)
        except (TypeError, ValueError):
            repeat_interval = 0.0
        repeat_interval = max(0.0, repeat_interval)
        return (
            send,
            name,
            sequence,
            periodic,
            checksum,
            display_mode,
            repeat_interval,
        )

    def _send_row_display_values(self, row):
        normalized = self._normalize_send_row(row)
        sequence_display = format_sequence_display(normalized[2], normalized[5])
        return (normalized[0], normalized[1], sequence_display)

    def _refresh_send_tree(self):
        for item in self.send_tree.get_children():
            self.send_tree.delete(item)
        for row in self._send_rows:
            self.send_tree.insert("", tk.END, values=self._send_row_display_values(row))
        self.after_idle(self._refresh_send_buttons)

    def update_send_sequence(
        self,
        old_index,
        new_index,
        name,
        sequence,
        periodic=False,
        checksum=None,
        display_mode="HEX",
        repeat_interval=0.0,
    ):
        try:
            repeat_interval = max(0.0, float(repeat_interval))
        except (TypeError, ValueError):
            repeat_interval = 0.0

        was_repeating = old_index in self._repeat_after_ids
        self._stop_repeat_for_row(old_index)

        row_data = (
            "",
            name,
            sequence,
            periodic,
            checksum or DEFAULT_CHECKSUM,
            display_mode,
            repeat_interval,
        )
        rows = self._send_rows
        if not (0 <= old_index < len(rows)):
            return

        rows.pop(old_index)
        new_index = max(0, min(new_index, len(rows)))
        rows.insert(new_index, row_data)
        self._refresh_send_tree()
        if (
            was_repeating
            and periodic
            and repeat_interval > 0
            and self.comm_service.is_connected()
        ):
            self._start_repeat_for_row(new_index, send_immediately=False)

    def delete_send_sequence(self, index):
        if 0 <= index < len(self._send_rows):
            self.stop_repeat_senders()
            self._send_rows.pop(index)
            self._refresh_send_tree()

    def get_receive_row(self, index):
        if not (0 <= index < len(self._receive_rows)):
            return ("☐", "", "", DEFAULT_CHECKSUM, DEFAULT_CHECKSUM_DETECT, "HEX")
        return self._normalize_receive_row(self._receive_rows[index])

    def _normalize_receive_row(self, row):
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

    def _receive_row_display_values(self, row):
        normalized = self._normalize_receive_row(row)
        sequence_display = format_sequence_display(normalized[2], normalized[5])
        return (normalized[0], normalized[1], sequence_display)

    def _refresh_receive_tree(self):
        for item in self.receive_tree.get_children():
            self.receive_tree.delete(item)
        for row in self._receive_rows:
            self.receive_tree.insert("", tk.END, values=self._receive_row_display_values(row))

    def update_receive_sequence(
        self,
        old_index,
        new_index,
        name,
        sequence,
        checksum=None,
        checksum_detect=None,
        display_mode="HEX",
        action=None,
    ):
        rows = self._receive_rows
        if not (0 <= old_index < len(rows)):
            return

        old_row = self._normalize_receive_row(rows[old_index])
        active = old_row[0]
        if checksum is None:
            checksum = old_row[3]
        if checksum_detect is None:
            checksum_detect = old_row[4]
        if action is None:
            action = parse_receive_action(old_row, name)
        row_data = (
            active,
            name,
            sequence,
            checksum,
            checksum_detect,
            display_mode,
            *receive_action_fields(action),
        )
        rows.pop(old_index)
        new_index = max(0, min(new_index, len(rows)))
        rows.insert(new_index, row_data)
        self._refresh_receive_tree()

    def delete_receive_sequence(self, index):
        if 0 <= index < len(self._receive_rows):
            self._receive_rows.pop(index)
            self._refresh_receive_tree()

    def _build_receive_sequences(self):
        frame = ttk.LabelFrame(self, text="", padding=4)

        header = tk.Frame(frame, bg="#d9d9d9")
        header.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            header,
            text="Receive Sequences",
            bg="#d9d9d9",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(header, text="Add Sequence", command=self.routes.add_receive_sequence).pack(
            side=tk.RIGHT
        )

        table_frame = tk.Frame(frame)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("active", "name", "sequence")
        self.receive_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=8
        )
        self.receive_tree.heading("active", text="Active")
        self.receive_tree.heading("name", text="Name")
        self.receive_tree.heading("sequence", text="Sequence")
        self.receive_tree.column("active", width=50, anchor=tk.CENTER)
        self.receive_tree.column("name", width=120, anchor=tk.W)
        self.receive_tree.column("sequence", width=200, anchor=tk.W)

        self._receive_rows = [
            (
                "☑",
                "ACK",
                "<ACK>",
                DEFAULT_CHECKSUM,
                DEFAULT_CHECKSUM_DETECT,
                "HEX",
                "Comment",
                0,
                default_comment_text("ACK"),
                True,
                True,
                True,
                False,
            ),
            (
                "☑",
                "Ping received",
                "2D 2D 2D 2D",
                DEFAULT_CHECKSUM,
                DEFAULT_CHECKSUM_DETECT,
                "HEX",
                "Stop",
                0,
                default_comment_text("Ping received"),
                True,
                True,
                True,
                True,
            ),
            (
                "☐",
                "Pong received",
                "50 6F 6E 67",
                DEFAULT_CHECKSUM,
                DEFAULT_CHECKSUM_DETECT,
                "HEX",
                "Answer",
                2,
                default_comment_text("Pong received"),
                True,
                True,
                True,
                False,
            ),
        ]
        for row in self._receive_rows:
            self.receive_tree.insert("", tk.END, values=self._receive_row_display_values(row))

        scrollbar = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.receive_tree.yview
        )
        self.receive_tree.configure(yscrollcommand=scrollbar.set)

        self.receive_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        return frame

    def _clear_communication_panel(self):
        for text_widget in self._comm_texts.values():
            text_widget.delete("1.0", tk.END)

    def _build_communication_panel(self):
        frame = ttk.LabelFrame(self, text="", padding=4)

        header = tk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 4))
        tk.Label(header, text="Communication", font=("Segoe UI", 9, "bold")).pack(
            side=tk.RIGHT
        )
        ttk.Button(
            header,
            text="Clear",
            width=8,
            command=self._clear_communication_panel,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        notebook = ttk.Notebook(frame)
        self._comm_notebook = notebook
        notebook.pack(fill=tk.BOTH, expand=True)

        for tab_name in ("ASCII", "HEX", "Decimal", "Binary"):
            tab = tk.Frame(notebook, bg="white")
            notebook.add(tab, text=tab_name)

            text = tk.Text(
                tab,
                bg="white",
                relief=tk.SUNKEN,
                borderwidth=1,
                wrap=tk.WORD,
                font=("Consolas", 9),
            )
            scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=text.yview)
            text.configure(yscrollcommand=scrollbar.set)
            self._configure_comm_tags(text)

            text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self._comm_texts[tab_name] = text

        notebook.bind("<<NotebookTabChanged>>", self._on_comm_tab_changed)
        notebook.select(1)
        return frame


if __name__ == "__main__":
    app = HomePage()
    app.mainloop()
