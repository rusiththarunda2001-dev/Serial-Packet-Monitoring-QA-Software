"""Dockable assistant panel. Answers come from Google Gemini (core/bot_client.py).

The assistant only suggests scripts. Nothing in the project changes until the
user clicks "Insert into script" or "Replace script".
"""

import queue
import re
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from core import ai_settings
from core.bot_client import BotClient, BotError, NO_KEY_MESSAGE
from core.bot_context import SCRIPT_FENCE, build_system_text
from core.bot_files import (
    FILE_DIALOG_TYPES,
    MAX_ATTACHMENTS,
    MAX_REQUEST_FILE_BYTES,
    AttachmentError,
    format_size,
    load_attachment,
)
from core.bot_sequences import SEQUENCE_FENCE, parse_sequence_block
from core.script_engine import check_script
from ui.bot_settings_dialog import BotSettingsDialog

POLL_MS = 50
IDLE_HINT = "Enter to send, Shift+Enter for a new line."
# A fenced block; group 1 is the language after ``` (empty, "docklight" or
# "docklight-sequences"), group 2 the content.
CODE_BLOCK = re.compile(r"```[ \t]*([\w-]*)[ \t]*\n(.*?)```", re.DOTALL)
FILE_QUESTION = "Please look at the attached file and tell me briefly what it contains."
BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_CODE = re.compile(r"`([^`\n]+)`")

PRIVACY_NOTICE = (
    "The assistant uses Google Gemini. When you ask a question, this is sent to Google:\n\n"
    "• your question and the earlier messages in this chat\n"
    "• the project settings (COM port, baud rate, flow control…)\n"
    "• the names and data of your send and receive sequences\n"
    "• the script in the Script Editor\n"
    "• the last 150 lines of the communication window, if sharing is switched on "
    "(you can switch it off with the gear button)\n"
    "• any file you attach with the 📎 button\n\n"
    "Your API key is used to send it. Do not use the assistant for data that must not "
    "leave this PC.\n\nContinue?"
)

QUICK_PROMPTS = (
    ("Write script", "Write a script that ", False),
    ("Explain error", "Explain the last error in the communication window and how to fix it.", True),
    ("No reply?", "Why did I get no reply from my device? What should I check?", True),
)


class ChatbotPanel(ttk.Frame):
    def __init__(self, parent, home=None, client_factory=BotClient):
        super().__init__(parent, padding=10, width=320)
        self.home = home if home is not None else parent.winfo_toplevel()
        self._client_factory = client_factory
        self._chat = []              # list of (role, text); role is "user" or "model"
        self._events = queue.Queue()
        self._request = None         # dict for the answer being written now
        self._request_number = 0
        self._poll_id = None
        self._pending_files = []     # Attachments for the next question

        self.grid_propagate(False)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Assistant", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky=tk.W)
        clear_button = ttk.Button(header, text="Clear chat", command=self.clear_chat)
        clear_button.grid(row=0, column=1, padx=(4, 0))
        gear = ttk.Button(header, text="⚙", width=3, command=self.open_settings)
        gear.grid(row=0, column=2, padx=(4, 0))
        self._tooltip(gear, "Assistant Settings (API key, model, data sharing)")
        self._tooltip(clear_button, "Start a new conversation")

        history_frame = ttk.Frame(self)
        history_frame.grid(row=1, column=0, sticky="nsew")
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)
        self._history = tk.Text(history_frame, wrap=tk.WORD, state=tk.DISABLED,
                                font=("Segoe UI", 10), padx=8, pady=8, cursor="arrow")
        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self._history.yview)
        self._history.configure(yscrollcommand=scrollbar.set)
        self._history.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._history.tag_configure("speaker", font=("Segoe UI", 10, "bold"))
        self._history.tag_configure("you", foreground="#1a4d8f")
        self._history.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        self._history.tag_configure("code", font=("Consolas", 10), background="#f0f0f0")
        self._history.tag_configure("error", foreground="#b00020")
        self._history.tag_configure("note", foreground="#666666", font=("Segoe UI", 9, "italic"))

        quick = ttk.Frame(self)
        quick.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for column, (label, text, send_now) in enumerate(QUICK_PROMPTS):
            quick.columnconfigure(column, weight=1)
            ttk.Button(quick, text=label,
                       command=lambda t=text, s=send_now: self._quick_prompt(t, s)).grid(
                row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0))

        attach_row = ttk.Frame(self)
        attach_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        attach_row.columnconfigure(1, weight=1)
        attach_button = ttk.Button(attach_row, text="📎 Attach file", command=self.attach_file)
        attach_button.grid(row=0, column=0, sticky=tk.W)
        self._tooltip(attach_button, "Attach a PDF, text/log/script or Excel file to your next "
                                     "question. The file is sent to Google with it.")
        self._files_label = ttk.Label(attach_row, text="", foreground="#1a4d8f",
                                      font=("Segoe UI", 8), wraplength=200)
        self._files_label.grid(row=0, column=1, sticky=tk.W, padx=(6, 0))
        self._remove_files_button = ttk.Button(attach_row, text="✕", width=3,
                                               command=self.remove_attachments)
        self._tooltip(self._remove_files_button, "Remove the attached files")

        entry_row = ttk.Frame(self)
        entry_row.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        entry_row.columnconfigure(0, weight=1)
        self._message_entry = tk.Text(entry_row, height=3, wrap=tk.WORD, font=("Segoe UI", 10),
                                      undo=True)
        self._message_entry.grid(row=0, column=0, sticky="ew")
        self._message_entry.bind("<Return>", self._on_enter)
        self._message_entry.bind("<Shift-Return>", lambda _e: None)  # new line
        self._send_button = ttk.Button(entry_row, text="Send", width=6, command=self._send_or_stop)
        self._send_button.grid(row=0, column=1, sticky="ns", padx=(6, 0))

        self._status = ttk.Label(self, text=IDLE_HINT, foreground="#666666", font=("Segoe UI", 8))
        self._status.grid(row=5, column=0, sticky=tk.W, pady=(2, 0))

        self._show_welcome()

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _tooltip(self, widget, text):
        attach = getattr(self.home, "_attach_toolbar_tooltip", None)
        if attach is not None:
            attach(widget, text)

    def focus_message_entry(self):
        self._message_entry.focus_set()

    def _write(self, text, *tags):
        self._history.configure(state=tk.NORMAL)
        self._history.insert(tk.END, text, tags)
        self._history.configure(state=tk.DISABLED)
        self._history.see(tk.END)

    def _write_widget(self, widget):
        self._history.configure(state=tk.NORMAL)
        self._history.window_create(tk.END, window=widget, padx=2, pady=4)
        self._history.insert(tk.END, "\n")
        self._history.configure(state=tk.DISABLED)
        self._history.see(tk.END)

    def _show_welcome(self):
        self._write("Assistant\n", "speaker")
        self._write("Hi! I can write scripts for you, answer questions about EC Docklight "
                    "and explain what you see in the communication window.\n")
        self._write("Use 📎 Attach file to ask about a PDF manual, a log or an Excel file, or "
                    "to create send and receive sequences from a protocol description.\n\n",
                    "note")
        if not ai_settings.load_api_key():
            self._show_key_needed()

    def _show_key_needed(self):
        self._write("To use the assistant, add your Gemini API key.\n", "note")
        button = ttk.Button(self._history, text="Add API key…", command=self.open_settings)
        self._write_widget(button)
        self._write("\n")

    def open_settings(self):
        BotSettingsDialog(self, on_saved=self._on_settings_saved,
                          client_factory=self._client_factory)

    # ------------------------------------------------------------------
    # Attached files
    # ------------------------------------------------------------------

    def attach_file(self):
        if len(self._pending_files) >= MAX_ATTACHMENTS:
            messagebox.showinfo("Docklight Assistant",
                                "You can attach up to {} files to one question.".format(MAX_ATTACHMENTS),
                                parent=self)
            return
        path = filedialog.askopenfilename(parent=self, title="Attach a file for the assistant",
                                          filetypes=FILE_DIALOG_TYPES)
        if not path:
            return
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            attachment = load_attachment(path)
        except AttachmentError as exc:
            messagebox.showwarning("Docklight Assistant", str(exc), parent=self)
            return
        finally:
            self.configure(cursor="")

        total = sum(item.request_size for item in self._pending_files) + attachment.request_size
        if total > MAX_REQUEST_FILE_BYTES:
            messagebox.showwarning(
                "Docklight Assistant",
                "Together the attached files are too large ({}). The limit for one question "
                "is {}.".format(format_size(total), format_size(MAX_REQUEST_FILE_BYTES)),
                parent=self)
            return
        if any(item.name == attachment.name for item in self._pending_files):
            self._pending_files = [item for item in self._pending_files
                                   if item.name != attachment.name]
        self._pending_files.append(attachment)
        self._update_files_label()
        if attachment.truncated:
            self._status.configure(text="The file is long; only the first part will be sent.")
        self.focus_message_entry()

    def remove_attachments(self):
        self._pending_files = []
        self._update_files_label()

    def _update_files_label(self):
        if self._pending_files:
            self._files_label.configure(
                text="📎 " + ", ".join(item.name for item in self._pending_files))
            self._remove_files_button.grid(row=0, column=2, padx=(4, 0))
        else:
            self._files_label.configure(text="")
            self._remove_files_button.grid_remove()

    def _on_settings_saved(self):
        if ai_settings.load_api_key():
            self._status.configure(text="Settings saved. You can ask a question now.")
        self.focus_message_entry()

    def clear_chat(self):
        self._cancel_request()
        self._chat = []
        self.remove_attachments()
        self._history.configure(state=tk.NORMAL)
        for child in self._history.winfo_children():
            child.destroy()
        self._history.delete("1.0", tk.END)
        self._history.configure(state=tk.DISABLED)
        self._status.configure(text=IDLE_HINT)
        self._show_welcome()

    def _quick_prompt(self, text, send_now):
        self._message_entry.delete("1.0", tk.END)
        self._message_entry.insert("1.0", text)
        self._message_entry.focus_set()
        if send_now and self._request is None:
            self._send_or_stop()

    # ------------------------------------------------------------------
    # Asking a question
    # ------------------------------------------------------------------

    def _on_enter(self, _event):
        self._send_or_stop()
        return "break"

    def _send_or_stop(self):
        if self._request is not None:
            self._cancel_request(note="Stopped.")
            return
        question = self._message_entry.get("1.0", "end-1c").strip()
        if not question and self._pending_files:
            question = FILE_QUESTION
        if question:
            self.ask(question)

    def ask(self, question):
        """Send a question. Returns False if it could not be sent."""
        if self._request is not None:
            return False
        settings = ai_settings.load_ai_settings()
        key = ai_settings.load_api_key()
        if not key:
            self._write("Assistant\n", "speaker")
            self._write(NO_KEY_MESSAGE + "\n", "error")
            self._show_key_needed()
            return False
        if not settings["privacy_notice_accepted"]:
            if not messagebox.askokcancel("Docklight Assistant", PRIVACY_NOTICE, parent=self):
                return False
            settings["privacy_notice_accepted"] = True
            try:
                ai_settings.save_ai_settings(settings)
            except OSError:
                pass  # ask again next time; not a reason to stop

        try:
            snapshot = self.home.get_bot_snapshot(settings["share_comm_data"])
        except Exception:
            snapshot = {}
        system_text = build_system_text(snapshot)
        attachments = tuple(self._pending_files)
        self.remove_attachments()

        self._message_entry.delete("1.0", tk.END)
        self._write("You\n", "speaker", "you")
        for attachment in attachments:
            self._write("📎 " + attachment.label() + "\n", "note")
        self._write(question + "\n\n", "you")
        self._write("Assistant\n", "speaker")
        self._history.mark_set("answer_start", "end-1c")
        self._history.mark_gravity("answer_start", tk.LEFT)

        self._request_number += 1
        cancel = threading.Event()
        self._request = {"number": self._request_number, "cancel": cancel,
                         "question": question, "attachments": attachments, "text": ""}
        history = list(self._chat)
        number = self._request_number

        def work():
            try:
                client = self._client_factory(key, settings["model"])
                for piece in client.stream_reply(system_text, history, question, cancel,
                                                 attachments=attachments):
                    if cancel.is_set():
                        return
                    self._events.put((number, "chunk", piece))
                self._events.put((number, "done", None))
            except BotError as exc:
                self._events.put((number, "error", str(exc)))
            except Exception:
                self._events.put((number, "error", "The assistant could not answer. "
                                  "Try again in a moment."))

        threading.Thread(target=work, daemon=True, name="bot-reply").start()
        self._send_button.configure(text="Stop")
        self._status.configure(text="Thinking…")
        if self._poll_id is None:
            self._poll_id = self.after(POLL_MS, self._poll)
        return True

    def _cancel_request(self, note=None):
        request = self._request
        if request is None:
            return
        request["cancel"].set()
        self._request = None
        if request["text"]:
            self._render_answer(request["text"])
            self._remember(request)
        if note:
            self._write(note + "\n", "note")
        self._write("\n")
        self._finish_ui()

    def _remember(self, request):
        """Keep the question (with its files, for follow-up questions) and the answer."""
        self._chat.append(("user", request["question"], request["attachments"]))
        self._chat.append(("model", request["text"]))

    def _finish_ui(self):
        self._send_button.configure(text="Send")
        self._status.configure(text=IDLE_HINT)

    def _poll(self):
        self._poll_id = None
        try:
            while True:
                number, kind, value = self._events.get_nowait()
                request = self._request
                if request is None or number != request["number"]:
                    continue  # an answer that was stopped
                if kind == "chunk":
                    request["text"] += value
                    self._write(value)
                    self._status.configure(text="Writing…")
                elif kind == "done":
                    self._request = None
                    self._render_answer(request["text"])
                    self._remember(request)
                    self._write("\n")
                    self._finish_ui()
                else:  # error
                    self._request = None
                    if request["attachments"] and not self._pending_files:
                        # Keep the files so the question can simply be sent again.
                        self._pending_files = list(request["attachments"])
                        self._update_files_label()
                    if request["text"]:
                        self._render_answer(request["text"])
                    self._write(value + "\n\n", "error")
                    self._finish_ui()
        except queue.Empty:
            pass
        if self._request is not None:
            self._poll_id = self.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------
    # Showing an answer
    # ------------------------------------------------------------------

    def _render_answer(self, text):
        """Replace the raw streamed text with formatted text and script boxes."""
        self._history.configure(state=tk.NORMAL)
        # "end-1c": deleting up to END would also remove the newline after "Assistant".
        self._history.delete("answer_start", "end-1c")
        self._history.configure(state=tk.DISABLED)

        position = 0
        for match in CODE_BLOCK.finditer(text):
            language = match.group(1).lower()
            if language == SEQUENCE_FENCE:
                self._write_formatted(text[position:match.start()])
                self._write_sequence_box(match.group(2))
            elif language in ("", SCRIPT_FENCE):
                self._write_formatted(text[position:match.start()])
                lines = [line.rstrip() for line in match.group(2).strip("\n").split("\n")]
                self._write_script_box(lines)
            else:
                continue  # some other code block: shown as plain text below
            position = match.end()
        self._write_formatted(text[position:].rstrip() + "\n")

    def _write_formatted(self, text):
        """Simple formatting: **bold** and `code`; list markers become bullets."""
        if not text:
            return
        text = re.sub(r"(?m)^(\s*)[*-] ", r"\1• ", text)
        text = re.sub(r"(?m)^#{1,6}\s*", "", text)
        pattern = re.compile(BOLD.pattern + "|" + INLINE_CODE.pattern)
        position = 0
        for match in pattern.finditer(text):
            self._write(text[position:match.start()])
            if match.group(1) is not None:
                self._write(match.group(1), "bold")
            else:
                self._write(match.group(2), "code")
            position = match.end()
        self._write(text[position:])

    def _script_problems(self, lines):
        try:
            send_names = [str(row[1]) for row in self.home._send_rows]
            receive_rows = []
            for index in range(len(self.home._receive_rows)):
                row = self.home.get_receive_row(index)
                receive_rows.append((str(row[1]), row[0] == "☑"))
        except Exception:
            send_names, receive_rows = None, None
        return check_script("\n".join(lines), send_names, receive_rows)

    def _write_script_box(self, lines):
        # Make the box as wide as the chat area so long commands are not cut off.
        code_font = tkfont.Font(font=("Consolas", 9))
        box_px = max(220, self._history.winfo_width() - 50)
        chars = max(20, box_px // max(1, code_font.measure("0")) - 3)
        box = tk.Frame(self._history, bd=1, relief=tk.SOLID, bg="#fafafa")
        code = tk.Text(box, height=min(max(len(lines), 1), 15), width=chars, wrap=tk.NONE,
                       font=code_font, bg="#fafafa", relief=tk.FLAT, padx=4, pady=4)
        if any(len(line) > chars for line in lines):
            code.configure(wrap=tk.CHAR, height=min(15, sum(len(line) // chars + 1 for line in lines)))
        code.insert("1.0", "\n".join(lines))
        code.configure(state=tk.DISABLED)
        code.pack(fill=tk.X)

        problems = self._script_problems(lines)
        if problems:
            tk.Label(box, text="Check before using:\n" + "\n".join(problems), bg="#fff4e5",
                     fg="#8a4b00", justify=tk.LEFT, wraplength=box_px - 10, anchor="w",
                     font=("Segoe UI", 8)).pack(fill=tk.X)

        buttons = tk.Frame(box, bg="#fafafa")
        buttons.pack(fill=tk.X, pady=3)
        ttk.Button(buttons, text="Insert into script",
                   command=lambda: self._insert_script(lines, replace=False)).pack(side=tk.LEFT, padx=3)
        ttk.Button(buttons, text="Replace script",
                   command=lambda: self._insert_script(lines, replace=True)).pack(side=tk.LEFT)
        self._write_widget(box)

    def _write_sequence_box(self, block_text):
        """A box listing the sequences the assistant proposes, with "Add to project"."""
        proposal = parse_sequence_block(block_text)
        box_px = max(220, self._history.winfo_width() - 50)
        box = tk.Frame(self._history, bd=1, relief=tk.SOLID, bg="#fafafa")

        lines = []
        if proposal.send:
            lines.append("Send sequences:")
            lines.extend("  • " + item.summary() for item in proposal.send)
        if proposal.receive:
            lines.append("Receive sequences:")
            lines.extend("  • " + item.summary() for item in proposal.receive)
        if not lines:
            lines.append("No sequences could be read.")
        tk.Label(box, text="\n".join(lines), bg="#fafafa", justify=tk.LEFT, anchor="w",
                 wraplength=box_px - 10, font=("Consolas", 9)).pack(fill=tk.X, padx=4, pady=4)

        if proposal.problems:
            tk.Label(box, text="Not included:\n" + "\n".join(proposal.problems), bg="#fff4e5",
                     fg="#8a4b00", justify=tk.LEFT, wraplength=box_px - 10, anchor="w",
                     font=("Segoe UI", 8)).pack(fill=tk.X)

        if not proposal.is_empty():
            buttons = tk.Frame(box, bg="#fafafa")
            buttons.pack(fill=tk.X, pady=3)
            add_button = ttk.Button(buttons, text="Add to project")
            add_button.configure(command=lambda: self._add_sequences(proposal, add_button))
            add_button.pack(side=tk.LEFT, padx=3)
        self._write_widget(box)

    def _add_sequences(self, proposal, button):
        count_text = []
        if proposal.send:
            count_text.append("{} send".format(len(proposal.send)))
        if proposal.receive:
            count_text.append("{} receive".format(len(proposal.receive)))
        question = ("Add {} sequence(s) to the project?\n\nExisting sequences are not changed. "
                    "New receive sequences are switched on (ticked). Check the byte values "
                    "against your device documentation before you use them.").format(
                        " and ".join(count_text))
        if not messagebox.askyesno("Docklight Assistant", question, parent=self):
            return

        added_send, added_receive, notes = self.home.add_assistant_sequences(proposal)
        if added_send or added_receive:
            button.configure(state=tk.DISABLED, text="Added")
            self._status.configure(text="Added {} send and {} receive sequence(s).".format(
                len(added_send), len(added_receive)))
        else:
            self._status.configure(text="Nothing was added.")
        if notes:
            messagebox.showinfo("Docklight Assistant", "\n".join(notes), parent=self)

    def _insert_script(self, lines, replace):
        if getattr(self.home, "_active_script", None) is not None:
            messagebox.showinfo("Docklight Assistant",
                                "A script is running. Stop it first, then insert the new lines.",
                                parent=self)
            return
        current = ""
        try:
            current = self.home.get_script_text()
        except Exception:
            pass
        if replace and current.strip():
            if not messagebox.askyesno("Docklight Assistant",
                                       "Replace the whole script in the Script Editor with "
                                       "these lines?", parent=self):
                return
        self.home.insert_script_lines(lines, replace=replace)
        self._status.configure(
            text="Script replaced." if replace else "Lines added to the end of the script.")
