"""UI-only dockable chat panel for Docklight."""

import tkinter as tk
from tkinter import ttk


class ChatbotPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10, width=300)
        self.grid_propagate(False)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Docklight Chatbot",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky=tk.W)
        home_page = parent.winfo_toplevel()

        history_frame = ttk.Frame(self)
        history_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)

        self._history = tk.Text(
            history_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Segoe UI", 10),
            padx=8,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(
            history_frame, orient=tk.VERTICAL, command=self._history.yview
        )
        self._history.configure(yscrollcommand=scrollbar.set)
        self._history.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._message = tk.StringVar()
        self._message_entry = ttk.Entry(self, textvariable=self._message)
        self._message_entry.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self._message_entry.bind("<Return>", self._send_message)

        send_button = ttk.Button(
            self, text="Send", command=self._send_message
        )
        send_button.grid(row=2, column=1, sticky=tk.E, padx=(8, 0), pady=(10, 0))
        if hasattr(home_page, "_attach_toolbar_tooltip"):
            home_page._attach_toolbar_tooltip(send_button, "Send Message")

        self._append_message(
            "Assistant",
            "This chat window is UI-only. AI responses are not connected yet.",
        )
        self._message_entry.focus_set()

    def focus_message_entry(self):
        self._message_entry.focus_set()

    def _append_message(self, speaker, message):
        self._history.configure(state=tk.NORMAL)
        self._history.insert(tk.END, "{}: {}\n\n".format(speaker, message))
        self._history.configure(state=tk.DISABLED)
        self._history.see(tk.END)

    def _send_message(self, _event=None):
        message = self._message.get().strip()
        if not message:
            return "break"

        self._message.set("")
        self._append_message("You", message)
        self._append_message(
            "Assistant",
            "AI responses are not connected yet; your message was not sent to a service.",
        )
        return "break"
