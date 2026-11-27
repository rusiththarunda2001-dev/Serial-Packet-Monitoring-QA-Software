"""Assistant Settings window: Gemini API key, model and data sharing."""

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from core import ai_settings
from core.bot_client import BotClient, BotError

API_KEY_PAGE = "https://aistudio.google.com/apikey"


class BotSettingsDialog(tk.Toplevel):
    """Modal window. on_saved() is called after the user clicks Save."""

    def __init__(self, parent, on_saved=None, client_factory=BotClient):
        super().__init__(parent)
        self.title("Assistant Settings")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self._on_saved = on_saved
        self._client_factory = client_factory
        self._results = queue.Queue()
        self._test_number = 0

        settings = ai_settings.load_ai_settings()
        self._saved_key = ai_settings.load_saved_api_key()

        body = ttk.Frame(self, padding=14)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Gemini API key:").grid(row=0, column=0, sticky=tk.W, pady=(0, 2))
        self._key = tk.StringVar(value=self._saved_key)
        self._key_entry = ttk.Entry(body, textvariable=self._key, show="•", width=44)
        self._key_entry.grid(row=0, column=1, sticky="ew", pady=(0, 2))
        self._show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Show", variable=self._show_key,
                        command=self._toggle_show).grid(row=0, column=2, padx=(6, 0))

        link = ttk.Label(body, text="How to get a free key (opens aistudio.google.com)",
                         foreground="#0645ad", cursor="hand2")
        link.grid(row=1, column=1, columnspan=2, sticky=tk.W)
        link.bind("<Button-1>", lambda _e: webbrowser.open(API_KEY_PAGE))

        note = ("The key is kept in Windows Credential Manager on this PC. It is never "
                "saved in your project file or in logs.")
        if not self._saved_key and ai_settings.api_key_source() == "environment":
            note = ("Using the key from the GEMINI_API_KEY environment variable. Type a "
                    "key here to use a different one.")
        ttk.Label(body, text=note, wraplength=420, foreground="#555555").grid(
            row=2, column=1, columnspan=2, sticky=tk.W, pady=(4, 10))

        ttk.Label(body, text="Model:").grid(row=3, column=0, sticky=tk.W)
        self._model_labels = {label: model for model, label in ai_settings.MODEL_CHOICES}
        labels = list(self._model_labels)
        current = settings["model"]
        current_label = next((label for label, model in self._model_labels.items()
                              if model == current), None)
        if current_label is None:  # a model typed by hand earlier
            current_label = current
            labels.append(current)
            self._model_labels[current] = current
        self._model = tk.StringVar(value=current_label)
        ttk.Combobox(body, textvariable=self._model, values=labels, state="readonly",
                     width=42).grid(row=3, column=1, columnspan=2, sticky="ew")

        self._share = tk.BooleanVar(value=settings["share_comm_data"])
        ttk.Checkbutton(
            body, variable=self._share,
            text="Share communication data with the assistant (last 150 lines)",
        ).grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=(12, 0))
        ttk.Label(
            body, wraplength=420, foreground="#555555",
            text="Needed for questions like \"Explain the last error\". Turn it off if the "
                 "data must not leave this PC.",
        ).grid(row=5, column=0, columnspan=3, sticky=tk.W, padx=(22, 0))

        test_row = ttk.Frame(body)
        test_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        self._test_button = ttk.Button(test_row, text="Test connection", command=self._test)
        self._test_button.pack(side=tk.LEFT)
        self._test_status = ttk.Label(test_row, text="", wraplength=300)
        self._test_status.pack(side=tk.LEFT, padx=(10, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=3, sticky=tk.E, pady=(16, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=(6, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._key_entry.focus_set()
        self.after(50, self._place_and_grab)

    def _place_and_grab(self):
        try:
            owner = self.master.winfo_toplevel()
            self.update_idletasks()
            x = owner.winfo_rootx() + (owner.winfo_width() - self.winfo_width()) // 2
            y = owner.winfo_rooty() + (owner.winfo_height() - self.winfo_height()) // 3
            self.geometry("+{}+{}".format(max(0, x), max(0, y)))
            self.grab_set()
        except tk.TclError:
            pass

    def _toggle_show(self):
        self._key_entry.configure(show="" if self._show_key.get() else "•")

    def _chosen_model(self):
        return self._model_labels.get(self._model.get(), ai_settings.DEFAULT_MODEL)

    def _key_to_use(self):
        return self._key.get().strip() or ai_settings.load_api_key()

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    def _test(self):
        key = self._key_to_use()
        if not key:
            self._test_status.configure(text="Type your API key first.", foreground="#b00020")
            return
        self._test_number += 1
        number = self._test_number
        model = self._chosen_model()
        self._test_button.configure(state=tk.DISABLED)
        self._test_status.configure(text="Testing…", foreground="#555555")

        def work():
            try:
                self._client_factory(key, model).test_connection()
                self._results.put((number, None))
            except BotError as exc:
                self._results.put((number, str(exc)))
            except Exception:
                self._results.put((number, "The test failed. Try again in a moment."))

        threading.Thread(target=work, daemon=True, name="bot-test").start()
        self.after(100, self._poll_test)

    def _poll_test(self):
        if not self.winfo_exists():
            return
        try:
            number, error = self._results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_test)
            return
        if number != self._test_number:
            self.after(100, self._poll_test)
            return
        self._test_button.configure(state=tk.NORMAL)
        if error:
            self._test_status.configure(text=error, foreground="#b00020")
        else:
            self._test_status.configure(text="✔ Connected", foreground="#1b7f2a")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self):
        key = self._key.get().strip()
        try:
            if key != self._saved_key:
                ai_settings.save_api_key(key)
            settings = ai_settings.load_ai_settings()
            settings["model"] = self._chosen_model()
            settings["share_comm_data"] = bool(self._share.get())
            ai_settings.save_ai_settings(settings)
        except RuntimeError as exc:
            messagebox.showerror("Assistant Settings", str(exc), parent=self)
            return
        except OSError:
            messagebox.showerror(
                "Assistant Settings",
                "The settings could not be saved. Check that you can write to your "
                "user folder.", parent=self)
            return
        self.destroy()
        if self._on_saved is not None:
            self._on_saved()
