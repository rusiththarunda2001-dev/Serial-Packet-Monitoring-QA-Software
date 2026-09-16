"""Docklight home page UI."""

from datetime import datetime
from pathlib import Path
import tksheet

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
    format_answer_display,
    parse_receive_action,
    receive_action_fields,
)
from core.project_file import (
    ProjectFileError,
    apply_project_document,
    load_project_file,
    save_project_file,
)
from core.receive_matcher import find_matches
from core.sequence_codec import (
    PLACEHOLDER_PATTERN,
    SequenceEncodeError,
    encode_sequence,
    format_sequence_display,
)
from core.settings_saver import ProjectSettings
from route.routes import Routes
from ui.edit_receive_sequence import DEFAULT_CHECKSUM_DETECT


_FLOW_CONTROL_BAR_LABELS = {
    "manual": "Manual RTS/DTR Control",
    "hardware": "RTS/CTS Handshaking",
    "software": "XON/XOFF Handshaking",
}


class HomePage(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EC Docklight V2.3")
        self.geometry("1100x750")
        self.minsize(900, 650)
        self.configure(bg="#d9d9d9")

        self._send_rows = []
        self._receive_rows = []
        self._send_buttons = {}
        self._repeat_after_ids = {}
        self._global_display_mode = "HEX"
        self._updating_display_mode = False
        self._project_path = None
        self._project_dirty = False
        self.project_settings = ProjectSettings()
        self._communication_open = False
        self._keyboard_console_enabled = False
        self._keyboard_console_canvas = None
        self._toolbar_images = []
        self._comm_texts = {}
        self._handshake_poll_id = None
        self._handshake_indicators = {}
        self.comm_service = CommService(self._on_comm_event)
        self.routes = Routes(self)

        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()
        self._build_layout()
        self.routes.bind()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after_idle(self._refresh_send_buttons)
        self.after_idle(self._sync_flow_control_session)
        self._update_window_title()

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Project...", command=self.routes.new_project)
        file_menu.add_command(label="Open Project...", command=self.routes.open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Save Project", command=self.routes.save_project)
        file_menu.add_command(
            label="Save Project As...", command=self.routes.save_project_as
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        self._file_menu = file_menu

        for label in ("Edit", "Run", "Tools", "Help"):
            menu = tk.Menu(menubar, tearoff=0)
            menu.add_command(label="{} item".format(label))
            menubar.add_cascade(label=label, menu=menu)

    def get_project_path(self):
        return self._project_path

    def is_project_dirty(self):
        return self._project_dirty

    def mark_project_dirty(self):
        if self._project_dirty:
            return
        self._project_dirty = True
        self._update_window_title()

    def mark_project_clean(self, path=None):
        if path is not None:
            self._project_path = path
        self._project_dirty = False
        self._update_window_title()

    def _update_window_title(self):
        base_title = "EC Docklight V2.3"
        if self._project_path:
            name = Path(self._project_path).name
        else:
            name = "Untitled"
        dirty_marker = "*" if self._project_dirty else ""
        self.title("{} - {}{}".format(base_title, name, dirty_marker))

    def reset_project_state(self):
        self.set_keyboard_console_enabled(False)
        self.stop_repeat_senders()
        self.project_settings = ProjectSettings()
        self._send_rows = []
        self._receive_rows = []
        self._global_display_mode = "HEX"
        self.com_port.set(self.project_settings.get("channel"))
        self.comm_service.configure_session(self.project_settings.as_dict())
        self._update_flow_control_bar()
        self._refresh_send_tree()
        self._refresh_receive_tree()
        if hasattr(self, "_comm_notebook"):
            self._comm_notebook.select(1)
        self._clear_communication_panel()

    def load_project_from_path(self, path):
        document = load_project_file(path)
        apply_project_document(self, document)
        self.mark_project_clean(path=path)

    def save_project_to_path(self, path):
        save_project_file(path, self)
        self.mark_project_clean(path=path)

    def confirm_discard_unsaved_changes(self):
        if not self._project_dirty:
            return True

        answer = messagebox.askyesnocancel(
            "Unsaved Changes",
            "Save changes to the current project before continuing?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self.routes.save_project()
        return True

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
            stop_btn.pack(side=tk.LEFT, padx=(2, 0), pady=2)

            edit_btn = self._toolbar_image_button(
                toolbar, "edit_script.png", self.routes.edit_script
            )
            edit_btn.pack(side=tk.LEFT, padx=(6, 0), pady=2)

            keyboard_btn, keyboard_canvas = self._toolbar_icon_button(
                toolbar,
                self._draw_keyboard_icon,
                self.routes.toggle_keyboard_console,
                return_canvas=True,
            )
            keyboard_btn.pack(side=tk.LEFT, padx=(2, 6), pady=2)
            self._keyboard_console_canvas = keyboard_canvas

    # --- NEW SCRIPTING BUTTONS ---
            tk.Frame(toolbar, width=8, bg="#d4d0c8").pack(side=tk.LEFT)

            self._btn_script_play = self._toolbar_image_button(
                toolbar, 
                "play.png", 
                self._on_script_play, 
                disabled_image_name="play_disabled.png"
            )
            self._btn_script_play.pack(side=tk.LEFT, padx=(2, 0), pady=2)

            self._btn_script_pause = self._toolbar_image_button(
                toolbar, 
                "pause.png", 
                self._on_script_pause, 
                disabled_image_name="pause_disabled.png"
            )
            self._btn_script_pause.pack(side=tk.LEFT, padx=(2, 0), pady=2)

            self._btn_script_stop = self._toolbar_image_button(
                toolbar, 
                "stop.png", 
                self._on_script_stop, 
                disabled_image_name="stop_disabled.png"
            )
            self._btn_script_stop.pack(side=tk.LEFT, padx=(2, 0), pady=2)

            # Initialize the button states
            self._btn_script_play.set_state(True)
            self._btn_script_pause.set_state(False)
            self._btn_script_stop.set_state(False)

    def _load_toolbar_image(self, filename):
            path = Path(__file__).resolve().parent / "assets" / "toolbar" / filename
            image = tk.PhotoImage(file=str(path))
            self._toolbar_images.append(image)
            return image

    def _toolbar_icon_button(self, parent, draw_icon, command, return_canvas=False):
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

        if return_canvas:
            return frame, canvas
        return frame



    def _toolbar_image_button(self, parent, image_name, command, disabled_image_name=None):
            normal_bg = "#d4d0c8"
            hover_bg = "#b8b4ac"
            click_bg = "#a0a0a0"
            
            # Load the normal image, and the disabled image if one was provided
            image_active = self._load_toolbar_image(image_name)
            if disabled_image_name:
                image_disabled = self._load_toolbar_image(disabled_image_name)
            else:
                image_disabled = image_active  # Fallback if no disabled image is provided

            # Track our custom state manually
            state = {"enabled": True}

            def safe_command():
                if state["enabled"]:
                    command()

            btn = tk.Button(
                parent,
                image=image_active,
                command=safe_command,
                relief=tk.FLAT,
                bg=normal_bg,
                activebackground=click_bg,
                bd=1,
                cursor="hand2"
            )

            def on_click(_event):
                if not state["enabled"]:
                    return "break"

            def on_enter(_event):
                if state["enabled"]:
                    btn.configure(bg=hover_bg)

            def on_leave(_event):
                if state["enabled"]:
                    btn.configure(bg=normal_bg)

            def set_state(enabled):
                state["enabled"] = enabled
                if enabled:
                    # Swap to the colorful/active image
                    btn.config(image=image_active, bg=normal_bg, cursor="hand2")
                else:
                    # Swap to the grayed-out image
                    btn.config(image=image_disabled, bg=normal_bg, cursor="arrow")

            # Bind events
            btn.bind("<Button-1>", on_click)
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)

            btn.set_state = set_state
            return btn
    def _on_script_play(self):
            # If the script was previously paused, resume it
            if getattr(self, "_script_paused", False):
                self._script_paused = False
                
                # Update button states for resuming
                self._btn_script_play.set_state(False)
                self._btn_script_pause.set_state(True)
                self._btn_script_stop.set_state(True)
            else:
                # Try starting a fresh script run. Only update states if it actually fires!
                if self.routes.run_script():
                    self._btn_script_play.set_state(False)   # Deactivate Play
                    self._btn_script_pause.set_state(True)   # Activate Pause
                    self._btn_script_stop.set_state(True)    # Activate Stop
                else:
                    # If run_script returned False (e.g., empty editor), ensure 
                    # Play stays active and the others stay deactivated.
                    self._btn_script_play.set_state(True)
                    self._btn_script_pause.set_state(False)
                    self._btn_script_stop.set_state(False)

    def _on_script_pause(self):
            # Set pause flag high to halt execution loop in background thread
            self._script_paused = True
            
            # Explicitly set the exact states for this button action
            self._btn_script_play.set_state(True)    # Activate Play (to allow resume)
            self._btn_script_pause.set_state(False)  # Deactivate Pause
            self._btn_script_stop.set_state(True)    # Keep Stop active    

    def _on_script_stop(self):
            # Set stop flag high to completely break out of background thread execution
            self._script_stopped = True
            self._script_paused = False
            
            # Close the hardware communication line immediately
            self.routes.stop_communication()
            
            # Explicitly reset the buttons back to the default/idle layout right here
            self._btn_script_play.set_state(True)    # Activate Play
            self._btn_script_pause.set_state(False)  # Deactivate Pause
            self._btn_script_stop.set_state(False)   # Deactivate Stop    



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
    

    @staticmethod
    def _draw_keyboard_icon(canvas, active=False):
        canvas.delete("all")
        body_fill = "#9a9a9a" if active else "#c0c0c0"
        canvas.create_rectangle(4, 10, 20, 18, fill=body_fill, outline="#000000", width=1)
        for x in (7, 10, 13, 16):
            canvas.create_rectangle(x, 12, x + 2, 14, fill="#ffffff", outline="")
            canvas.create_rectangle(x, 15, x + 2, 17, fill="#ffffff", outline="")
        canvas.create_line(4, 10, 4, 7, 7, 5, 10, 4, 13, 6, fill="#000000", width=1)

    def set_keyboard_console_enabled(self, enabled):
        enabled = bool(enabled)
        if self._keyboard_console_enabled == enabled:
            return

        self._keyboard_console_enabled = enabled
        self._update_keyboard_console_bindings()
        self._update_keyboard_console_button()
        if enabled:
            self.port_status.set(
                "Communication port {} open - Keyboard Console On".format(
                    self.project_settings.get("channel")
                )
            )
        elif self.comm_service.is_connected():
            self.port_status.set(
                "Communication port {} open".format(
                    self.project_settings.get("channel")
                )
            )

    def _update_keyboard_console_button(self):
        if self._keyboard_console_canvas is None:
            return
        self._draw_keyboard_icon(
            self._keyboard_console_canvas,
            active=self._keyboard_console_enabled,
        )

    def _update_keyboard_console_bindings(self):
        if not self._comm_texts:
            return

        for text_widget in self._comm_texts.values():
            text_widget.unbind("<Key>")
            text_widget.unbind("<Button-1>")
            if self._keyboard_console_enabled:
                text_widget.config(state=tk.NORMAL, cursor="xterm")
                text_widget.bind("<Key>", self._on_keyboard_console_key)
                text_widget.bind("<Button-1>", self._on_keyboard_console_click, add="+")
            else:
                text_widget.config(state=tk.DISABLED, cursor="arrow")

    def _on_keyboard_console_click(self, event):
        widget = event.widget
        widget.focus_set()
        widget.mark_set(tk.INSERT, tk.END)
        return "break"

    def _keyboard_event_to_bytes(self, event):
        if event.state & 0x4:
            keysym = event.keysym.lower()
            if keysym == "v":
                try:
                    text = self.clipboard_get()
                except tk.TclError:
                    return b""
                return text[:1024].encode("latin-1", errors="replace")
            if len(event.keysym) == 1:
                code = ord(event.keysym.upper()) - 64
                if 1 <= code <= 26:
                    return bytes([code])
            return b""

        if event.keysym in ("Return", "KP_Enter"):
            return b"\r\n"
        if event.keysym == "Escape":
            return b"\x1b"
        if event.keysym == "Tab":
            return b"\t"
        if event.keysym == "BackSpace":
            return b"\x08"
        if event.char and event.char not in ("\r",):
            return event.char.encode("latin-1", errors="replace")
        return None

    def _on_keyboard_console_key(self, event):
        if not self._keyboard_console_enabled or not self.comm_service.is_connected():
            return "break"

        payload = self._keyboard_event_to_bytes(event)
        if payload is None:
            return "break"
        if not payload:
            return "break"

        try:
            if not self.comm_service.send_bytes(payload, label="Keyboard"):
                return "break"
        except Exception as exc:
            messagebox.showerror(
                "Keyboard Console",
                "Could not send keyboard input:\n{}".format(exc),
                parent=self,
            )
        return "break"

    def _with_comm_text_enabled(self, callback):
        widgets = list(self._comm_texts.values())
        for text_widget in widgets:
            text_widget.config(state=tk.NORMAL)
        try:
            callback()
        finally:
            if not self._keyboard_console_enabled:
                for text_widget in widgets:
                    text_widget.config(state=tk.DISABLED)

    def _build_status_bar(self):
        status_frame = tk.Frame(self, bg="#d9d9d9")
        status_frame.pack(fill=tk.X, padx=8, pady=(2, 0))
        self._status_frame = status_frame

        self.port_status = tk.StringVar(value="Communication port closed")
        tk.Label(
            status_frame,
            textvariable=self.port_status,
            bg="#d9d9d9",
            anchor=tk.W,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT)

        self._flow_control_frame = tk.Frame(status_frame, bg="#d9d9d9")
        self._flow_control_frame.pack(side=tk.RIGHT)

        self._flow_control_title = tk.Label(
            self._flow_control_frame,
            text="Manual RTS/DTR Control",
            bg="#d9d9d9",
            font=("Segoe UI", 8),
        )
        self._flow_control_title.pack(side=tk.TOP, anchor=tk.E, pady=(0, 2))

        indicators_row = tk.Frame(self._flow_control_frame, bg="#d9d9d9")
        indicators_row.pack(side=tk.TOP)
        self._handshake_indicators_row = indicators_row

        for signal, toggleable in (
            ("RTS", True),
            ("DTR", True),
            ("CTS", False),
            ("DSR", False),
            ("DCD", False),
            ("RI", False),
        ):
            cell = tk.Frame(indicators_row, bg="#d9d9d9", padx=6)
            cell.pack(side=tk.LEFT)

            tk.Label(
                cell,
                text=signal,
                bg="#d9d9d9",
                font=("Segoe UI", 8),
            ).pack()

            canvas = tk.Canvas(
                cell,
                width=16,
                height=16,
                bg="#d9d9d9",
                highlightthickness=0,
                bd=0,
            )
            canvas.pack(pady=(2, 0))

            key = signal.lower()
            self._handshake_indicators[key] = {
                "canvas": canvas,
                "toggleable": toggleable,
            }

            if toggleable:
                canvas.configure(cursor="hand2")
                canvas.bind(
                    "<Double-Button-1>",
                    lambda _e, sig=key: self._toggle_handshake_output(sig),
                )

        self._flow_control_frame.pack_forget()

    def _sync_flow_control_session(self):
        self.comm_service.configure_session(self.project_settings.as_dict())
        self._update_flow_control_bar()

    def _flow_control_bar_mode(self):
        mode = self.project_settings.get("flow_control", "off")
        if mode in _FLOW_CONTROL_BAR_LABELS:
            return mode
        return None

    def _update_flow_control_bar(self):
        mode = self._flow_control_bar_mode()
        if mode:
            self._flow_control_title.config(text=_FLOW_CONTROL_BAR_LABELS[mode])
            self._configure_handshake_interaction(mode)
            if mode == "manual":
                self._handshake_indicators_row.pack(side=tk.TOP)
                self._refresh_handshake_indicators()
                self._schedule_handshake_poll()
            else:
                self._handshake_indicators_row.pack_forget()
                self._cancel_handshake_poll()
            self._flow_control_frame.pack(side=tk.RIGHT)
        else:
            self._flow_control_frame.pack_forget()
            self._cancel_handshake_poll()

    def _configure_handshake_interaction(self, flow_mode):
        for key, widgets in self._handshake_indicators.items():
            toggleable = flow_mode == "manual" and key in ("rts", "dtr")
            widgets["toggleable"] = toggleable
            widgets["canvas"].configure(cursor="hand2" if toggleable else "")

    def _schedule_handshake_poll(self):
        self._cancel_handshake_poll()
        if not self._flow_control_bar_mode():
            return
        self._handshake_poll_id = self.after(200, self._poll_handshake_lines)

    def _cancel_handshake_poll(self):
        if self._handshake_poll_id is not None:
            try:
                self.after_cancel(self._handshake_poll_id)
            except tk.TclError:
                pass
            self._handshake_poll_id = None

    def _poll_handshake_lines(self):
        self._handshake_poll_id = None
        if not self._flow_control_bar_mode():
            return
        self._refresh_handshake_indicators()
        self._schedule_handshake_poll()

    def _refresh_handshake_indicators(self):
        state = self.comm_service.get_handshake_state()
        for key, widgets in self._handshake_indicators.items():
            self._draw_handshake_indicator(widgets["canvas"], state.get(key, False))

    @staticmethod
    def _draw_handshake_indicator(canvas, active):
        canvas.delete("all")
        if active:
            canvas.create_oval(2, 2, 14, 14, fill="#1a5fb4", outline="#1a5fb4")
        else:
            canvas.create_oval(2, 2, 14, 14, fill="#d9d9d9", outline="#666666")

    def _toggle_handshake_output(self, signal):
        if self.project_settings.get("flow_control") != "manual":
            return

        widgets = self._handshake_indicators.get(signal)
        if not widgets or not widgets.get("toggleable"):
            return

        state = self.comm_service.get_handshake_state()
        if signal == "rts":
            self.comm_service.set_manual_handshake(rts=not state["rts"])
        elif signal == "dtr":
            self.comm_service.set_manual_handshake(dtr=not state["dtr"])
        self._refresh_handshake_indicators()

    def _on_close(self):
        if not self.confirm_discard_unsaved_changes():
            return
        self._cancel_handshake_poll()
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

            if matches:
                buffer_cursor = 0
                is_first_chunk = True

                for match in matches:
                    # Find where this specific packet starts in the raw buffer
                    idx = event.data.find(match.data, buffer_cursor)
                    if idx != -1:
                        # 1. Print any unmatched bytes (like spacing) before the packet
                        unmatched = event.data[buffer_cursor:idx]
                        if unmatched:
                            self._append_comm_data(
                                unmatched, "RX", show_header=is_first_chunk
                            )
                            is_first_chunk = False

                        # 2. Check for checksum failures
                        if match.checksum_ok is False:
                            self._append_comm_line(
                                'Checksum wrong for receive sequence "{}".'.format(match.name)
                                
                            )
                            self._append_comm_data(match.data, "RX", show_header=is_first_chunk)
                            is_first_chunk = False
                            buffer_cursor = idx + len(match.data)
                            continue

                        # 3. Extract the comment for a successful match
                        row = self.get_receive_row(match.row_index)
                        action = parse_receive_action(row, match.name)
                        comment = action.comment_text.strip() or default_comment_text(match.name)

                        if action.comment_timestamp:
                            comment = "{}  {}".format(comment, self._format_comm_timestamp())

                        # 4. Print the matched packet with its attached comment
                        inline_suffix = " {}".format(comment) if comment else ""
                        self._append_comm_data(
                            match.data,
                            "RX",
                            inline_suffix=inline_suffix,
                            extra_line_break=False,
                            show_header=is_first_chunk
                        )
                        
                        # Advance the cursor past this packet
                        is_first_chunk = False
                        buffer_cursor = idx + len(match.data)

                        # 5. Execute any triggered actions
                        if self._run_receive_action(match, action):
                            self._append_comm_line(
                                'Communication stopped by receive sequence "{}".'.format(match.name),
                                show_channel=False
                            )
                            self.routes.stop_communication()
                            return

                # 6. Dump any trailing unmatched bytes (like <CR><LF>) at the end of the buffer
                remaining = event.data[buffer_cursor:]
                if remaining:
                    self._append_comm_data(remaining, "RX", show_header=is_first_chunk)

            else:
                self._append_comm_data(event.data, "RX")

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

    def _get_channel_label(self, direction):
        """Return alias for TX/RX if set in project settings, else the direction."""
        aliases = self.project_settings.get("channel_aliases", ("", ""))
        index = 0 if direction == "TX" else 1
        if index < len(aliases):
            alias = aliases[index].strip()
            if alias:
                return alias
        return direction

    def _should_show_comm_data(self, direction):
        """Whether raw TX/RX byte lines should appear in the communication panel."""
        filt = self.project_settings.get("contents_filter", "all")
        if filt == "all":
            return True
        if filt == "channel1":
            return direction == "TX"
        if filt == "channel2":
            return direction == "RX"
        if filt == "comments_only":
            return False
        return True

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
        label = self._get_channel_label(direction)
        text_widget.insert(tk.END, timestamp + " ", "meta")
        text_widget.insert(tk.END, "[{}]".format(label), "meta")
        text_widget.insert(tk.END, " - ", "meta")

    def _insert_comm_payload(self, text_widget, data, mode, data_tag):
        for text, segment_tag in format_comm_segments(data, mode):
            widget_tag = "meta" if segment_tag == "control" else data_tag
            text_widget.insert(tk.END, text, widget_tag)

    def _insert_comm_line_ending(self, text_widget, ending):
        for text, _segment_tag in format_line_ending_segments(ending):
            text_widget.insert(tk.END, text, "meta")

    def _append_comm_line(self, line, tag="status", direction="RX", show_channel=True):
        if not self._comm_texts:
            return

        def insert_lines():
            for text_widget in self._comm_texts.values():
                if show_channel:
                    self._insert_comm_header(text_widget, direction)
                text_widget.insert(tk.END, line, tag)
                text_widget.insert(tk.END, "\n")
                text_widget.see(tk.END)

        self._with_comm_text_enabled(insert_lines)

    def _get_rx_inline_suffix(self, matches):
            """
            Comment text formatting is now handled directly inside _handle_comm_event 
            to allow line-by-line printing of burst packets.
            """
            return "", False

    def _append_comm_blank_line(self):
        if not self._comm_texts:
            return

        def insert_blank():
            for text_widget in self._comm_texts.values():
                text_widget.insert(tk.END, "\n")
                text_widget.see(tk.END)

        self._with_comm_text_enabled(insert_blank)

    def _append_comm_data(
        self,
        data,
        direction,
        inline_suffix="",
        extra_line_break=False,
        show_header=True,
    ):
        if not self._comm_texts:
            return

        if not self._should_show_comm_data(direction):
            if (
                self.project_settings.get("contents_filter") == "comments_only"
                and inline_suffix
            ):
                self._append_comm_line(
                    inline_suffix, tag="status", direction=direction
                )
                if extra_line_break:
                    self._append_comm_blank_line()
            return

        lines = list(iter_comm_lines(data))
        if not lines and data:
            lines = [(data, b"")]

        data_tag = "rx_data" if direction == "RX" else "tx_data"
        last_line_index = len(lines) - 1

        def insert_data():
            for tab_name, text_widget in self._comm_texts.items():
                for index, (line_bytes, ending) in enumerate(lines):
                    # ONLY print the timestamp header if the flag is True
                    if index == 0 and show_header:
                        self._insert_comm_header(text_widget, direction)

                    self._insert_comm_payload(text_widget, line_bytes, tab_name, data_tag)
                    self._insert_comm_line_ending(text_widget, ending)

                    if inline_suffix and index == last_line_index:
                        text_widget.insert(tk.END, "  {}".format(inline_suffix), "meta")

                    text_widget.insert(tk.END, "\n")

                if extra_line_break and inline_suffix:
                    text_widget.insert(tk.END, "\n")

                text_widget.see(tk.END)

        self._with_comm_text_enabled(insert_data)


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
            return False

        if action.action_type == "Answer":
            if action.answer_send_index >= 0:
                self._send_answer_sequence(action.answer_send_index, match.name)
            return False

        if action.action_type == "Trigger" and action.snapshot_trigger:
            self._append_comm_line(
                'Snapshot triggered by receive sequence "{}".'.format(match.name)
            )
            return False

        if action.action_type == "Stop" and action.stop_communication:
            return True

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
            if not self.comm_service.send_bytes(payload, label=name):
                return
        except Exception as exc:
            self._append_comm_line(
                'Automatic answer for "{}" failed: {}'.format(trigger_name, exc)
            )

    def apply_project_settings(self, settings):
        self.set_keyboard_console_enabled(False)
        was_open = self.comm_service.is_connected()
        if was_open:
            self.routes.stop_communication()

        self.project_settings.update(settings)
        self.com_port.set(self.project_settings.get("channel"))
        self.comm_service.configure_session(self.project_settings.as_dict())
        self._update_flow_control_bar()
        self.mark_project_dirty()

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

        right_pane = ttk.PanedWindow(paned, orient=tk.VERTICAL)
        paned.add(right_pane, weight=2)

        comm_frame = self._build_communication_panel()
        script_frame = self._build_script_editor_panel()
        right_pane.add(comm_frame, weight=3)
        right_pane.add(script_frame, weight=1)

    def _build_script_editor_panel(self):
            import tksheet
            
            frame = ttk.LabelFrame(self, text="", padding=4)

            header = tk.Frame(frame)
            header.pack(fill=tk.X, pady=(0, 4))
            tk.Label(
                header,
                text="Script Editor",
                font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.LEFT)

            # Start with a handful of blank rows so it reads as a real
            # spreadsheet grid rather than a single empty line.
            initial_rows = [[""] for _ in range(15)]

            # Create the Sheet container safely matching the window backdrop
            self._script_sheet = tksheet.Sheet(
                frame,
                data=initial_rows,
                headers=["Command Script (Type, Edit, or Paste directly)"],
                height=180,
                enable_delete_key=True,
                # Excel-style row numbers down the left edge
                show_row_index=True,
                row_index_width=40,
                # Fix: Keep margins at 0 integer values to prevent string errors
                empty_horizontal=0,
                empty_vertical=0,
                # Fix: Set the underlying canvas background color natively
                table_background="#ffffff",
                # Visible cell gridlines like a real spreadsheet
                grid_color="#c0c0c0",
                header_bg="#e8e8e8",
                header_fg="#000000",
                index_bg="#e8e8e8",
                index_fg="#000000",
            )
            
            # Enable all standard Excel-like interactive features
            self._script_sheet.enable_bindings((
                "single_select",
                "drag_select",
                "select_all",
                "row_select",
                "edit_cell",         
                "undo",
                "copy",
                "paste",
                "cut",
                "rc_select",
                "rc_insert_row",
                "rc_delete_row",
                "arrowkeys",
                "delete",             
                "clear_clipboard",   
                "insert_row",        
                "delete_row",
                # Lets the user drag row heights / the column edge, like Excel
                "row_height_resize",
                "column_width_resize",
                "double_click_column_resize",
            ))
            
            self._script_sheet.column_width(column=0, width=570)
            self._script_sheet.pack(fill=tk.BOTH, expand=True)

            # Connect UI modifications to update the unsaved changes state flag
            self._script_sheet.extra_bindings([
                ("end_edit_cell", lambda event: self.mark_project_dirty()),
                ("after_paste", lambda event: self.mark_project_dirty()),
                ("after_delete", lambda event: self.mark_project_dirty())
            ])

            return frame

    def get_script_text(self):
        """Extracts text lines out of the single-column grid matrix sequentially."""
        if not hasattr(self, "_script_sheet"):
            return ""
        
        lines = []
        sheet_data = self._script_sheet.get_sheet_data()
        for row in sheet_data:
            if row and row[0] is not None:
                cmd_str = str(row[0]).strip()
                if cmd_str:
                    lines.append(cmd_str)
        return "\n".join(lines)

    def clear_script_editor(self):
        """Resets the editor back to a single empty spreadsheet field."""
        if hasattr(self, "_script_sheet"):
            self._script_sheet.set_sheet_data([[""]])
            self._script_sheet.redraw()

    def focus_script_editor(self):
        if hasattr(self, "_script_text"):
            self._script_text.focus_set()

    def clear_script_editor(self):
            """Clear the table."""
            if hasattr(self, "_script_tree"):
                for item in self._script_tree.get_children():
                    self._script_tree.delete(item)
                self._script_entry.delete(0, tk.END)
                self._script_entry.focus_set()

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

        self._send_rows = []
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
            if not self.comm_service.send_bytes(payload, label=name):
                return False
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
        self.mark_project_dirty()

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
        self._refresh_receive_tree()
        self.mark_project_dirty()
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
            self._refresh_receive_tree()
            self.mark_project_dirty()

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
        action = parse_receive_action(normalized, normalized[1])
        answer_display = format_answer_display(
            action, self._send_rows, self._normalize_send_row
        )
        return (normalized[0], normalized[1], sequence_display, answer_display)

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
        self.mark_project_dirty()

    def delete_receive_sequence(self, index):
        if 0 <= index < len(self._receive_rows):
            self._receive_rows.pop(index)
            self._refresh_receive_tree()
            self.mark_project_dirty()

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

        columns = ("active", "name", "sequence", "answer")
        self.receive_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=8
        )
        self.receive_tree.heading("active", text="Active")
        self.receive_tree.heading("name", text="Name")
        self.receive_tree.heading("sequence", text="Sequence")
        self.receive_tree.heading("answer", text="Answer")
        self.receive_tree.column("active", width=50, anchor=tk.CENTER)
        self.receive_tree.column("name", width=100, anchor=tk.W)
        self.receive_tree.column("sequence", width=140, anchor=tk.W)
        self.receive_tree.column("answer", width=100, anchor=tk.W)

        self._receive_rows = []
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
        def clear_texts():
            for text_widget in self._comm_texts.values():
                text_widget.delete("1.0", tk.END)

        self._with_comm_text_enabled(clear_texts)

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
        self._update_keyboard_console_bindings()
        return frame


if __name__ == "__main__":
    app = HomePage()
    app.mainloop()