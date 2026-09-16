"""Project Settings dialog UI."""

import tkinter as tk
from tkinter import ttk

from core.comm_service import list_available_ports


class ProjectSetting(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.home = parent
        self.title("Project Settings")
        self.geometry("540x520")
        self.resizable(False, False)
        self.configure(bg="#f0f0f0")
        self.transient(parent)
        self.grab_set()

        self._active_tab = "communication"
        self._tab_labels = {}
        self._tab_underlines = {}
        self._tab_frames = {}
        self._com_port_combos = {}

        self._build_layout()
        self._load_settings(self.home.project_settings.as_dict())

    def _build_layout(self):
        footer = tk.Frame(self, bg="#f0f0f0", padx=16)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 12))
        self._build_footer(footer)

        main = tk.Frame(self, bg="#f0f0f0", padx=16)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))

        self._build_tabs(main)

        self.content_holder = tk.Frame(main, bg="#f0f0f0")
        self.content_holder.pack(fill=tk.BOTH, expand=True)

        self._tab_frames["communication"] = tk.Frame(self.content_holder, bg="#f0f0f0")
        self._tab_frames["flow_control"] = tk.Frame(self.content_holder, bg="#f0f0f0")
        self._tab_frames["comm_filter"] = tk.Frame(self.content_holder, bg="#f0f0f0")

        self._build_communication_tab(self._tab_frames["communication"])
        self._build_flow_control_tab(self._tab_frames["flow_control"])
        self._build_comm_filter_tab(self._tab_frames["comm_filter"])

        self._show_tab("communication")

    def _build_tabs(self, parent):
        tab_bar = tk.Frame(parent, bg="#f0f0f0")
        tab_bar.pack(fill=tk.X)

        tabs = (
            ("communication", "Communication"),
            ("flow_control", "Flow Control"),
            ("comm_filter", "Comm. Filter / Alias"),
        )

        for tab_id, label in tabs:
            tab = tk.Label(
                tab_bar,
                text=label,
                bg="#f0f0f0",
                fg="#333333",
                font=("Segoe UI", 9),
                padx=8,
                pady=6,
                cursor="hand2",
            )
            tab.pack(side=tk.LEFT, anchor=tk.SW)
            tab.bind("<Button-1>", lambda _e, tid=tab_id: self._show_tab(tid))

            underline = tk.Frame(tab_bar, bg="#f0f0f0", height=2)
            underline.place(in_=tab, relx=0, rely=1, relwidth=1, anchor=tk.SW)

            self._tab_labels[tab_id] = tab
            self._tab_underlines[tab_id] = underline

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 12))

    def _show_tab(self, tab_id):
        self._active_tab = tab_id
        for frame in self._tab_frames.values():
            frame.pack_forget()
        self._tab_frames[tab_id].pack(fill=tk.BOTH, expand=True)

        for tid, label in self._tab_labels.items():
            if tid == tab_id:
                label.config(fg="#1a5fb4", font=("Segoe UI", 9, "bold"))
                self._tab_underlines[tid].config(bg="#1a5fb4")
            else:
                label.config(fg="#333333", font=("Segoe UI", 9))
                self._tab_underlines[tid].config(bg="#f0f0f0")

    def _add_separator(self, parent):
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=14)

    def _build_communication_tab(self, parent):
        self._build_communication_mode(parent)
        self._build_channel_selection(parent)
        self._add_separator(parent)
        self._build_com_port_settings(parent)

    def _build_communication_mode(self, parent):
        section = tk.Frame(parent, bg="#f0f0f0")
        section.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            section,
            text="Communication Mode",
            bg="#f0f0f0",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, pady=(0, 4))

        self.comm_mode = tk.StringVar(value="send_receive")
        ttk.Radiobutton(
            section,
            text="Send/Receive",
            variable=self.comm_mode,
            value="send_receive",
        ).pack(anchor=tk.W)

    def _build_channel_selection(self, parent):
        section = tk.Frame(parent, bg="#f0f0f0")
        section.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            section,
            text="Send/Receive on Comm. Channel",
            bg="#f0f0f0",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, pady=(0, 4))

        self.channel_combo = ttk.Combobox(section, values=[], state="readonly")
        self.channel_combo.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            section,
            text="Choose a COM port from the list of currently available devices.",
            bg="#f0f0f0",
            fg="#555555",
            font=("Segoe UI", 8),
            justify=tk.LEFT,
            wraplength=500,
        ).pack(anchor=tk.W)

    def _build_com_port_settings(self, parent):
        section = tk.Frame(parent, bg="#f0f0f0")
        section.pack(fill=tk.X)

        tk.Label(
            section,
            text="COM Port Settings",
            bg="#f0f0f0",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, pady=(0, 8))

        grid = tk.Frame(section, bg="#f0f0f0")
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        settings = [
            ("baud_rate", "Baud Rate", "9600", ["1200", "2400", "4800", "9600", "19200", "38400", "115200"]),
            ("data_bits", "Data Bits", "8", ["5", "6", "7", "8"]),
            ("parity", "Parity", "None", ["None", "Even", "Odd", "Mark", "Space"]),
            ("stop_bits", "Stop Bits", "1", ["1", "1.5", "2"]),
            (
                "parity_error_char",
                "Parity Error Char.",
                "63 ('?')",
                ["63 ('?')", "35 ('#')", "42 ('*')", "248 ('@')"],
            ),
        ]

        for index, (key, label, default, values) in enumerate(settings):
            row = index // 2
            col = index % 2

            cell = tk.Frame(grid, bg="#f0f0f0")
            cell.grid(row=row, column=col, sticky=tk.EW, padx=(0, 12), pady=6)

            tk.Label(cell, text=label, bg="#f0f0f0", font=("Segoe UI", 9)).pack(
                anchor=tk.W
            )
            combo = ttk.Combobox(cell, values=values, state="readonly")
            combo.set(default)
            combo.pack(fill=tk.X, pady=(2, 0))
            self._com_port_combos[key] = combo

    def _build_flow_control_tab(self, parent):
        section = ttk.LabelFrame(parent, text="Flow Control Support", padding=10)
        section.pack(fill=tk.X, pady=(4, 12))

        self.flow_control = tk.StringVar(value="off")

        ttk.Radiobutton(section, text="Off", variable=self.flow_control, value="off").pack(
            anchor=tk.W, pady=(0, 6)
        )

        manual_row = tk.Frame(section)
        manual_row.pack(fill=tk.X, anchor=tk.W, pady=(0, 6))
        ttk.Radiobutton(
            manual_row,
            text="Manual:",
            variable=self.flow_control,
            value="manual",
        ).pack(side=tk.LEFT, anchor=tk.N)
        tk.Label(
            manual_row,
            text=(
                "- RTS / DTR can be set or reset manually. CTS / DSR lines are "
                "displayed, but not used for synchronization."
            ),
            justify=tk.LEFT,
            wraplength=420,
        ).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Radiobutton(
            section,
            text="Hardware Handshaking - RTS/CTS",
            variable=self.flow_control,
            value="hardware",
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Radiobutton(
            section,
            text="Software Handshaking - XON/XOFF",
            variable=self.flow_control,
            value="software",
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Radiobutton(
            section,
            text="RS485 Transceiver Control - Set RTS high while sending",
            variable=self.flow_control,
            value="rs485",
        ).pack(anchor=tk.W)

        warning = tk.Frame(parent, bg="#f0f0f0")
        warning.pack(fill=tk.X)

        tk.Label(
            warning,
            text="Warning:",
            bg="#f0f0f0",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W)

        tk.Label(
            warning,
            text=(
                "The 'RS485 Transceiver Control' option is an advanced setting for "
                "RS485 converters/interfaces that require the RTS signal. It is not "
                "supported by many USB-to-Serial devices or Virtual COM drivers!"
            ),
            bg="#f0f0f0",
            justify=tk.LEFT,
            wraplength=500,
        ).pack(anchor=tk.W)

    def _build_comm_filter_tab(self, parent):
        filter_section = ttk.LabelFrame(parent, text="Contents Filter", padding=10)
        filter_section.pack(fill=tk.X, pady=(4, 12))

        self.contents_filter = tk.StringVar(value="all")

        ttk.Radiobutton(
            filter_section,
            text="Show all original communication data (channel 1 and channel 2)",
            variable=self.contents_filter,
            value="all",
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Radiobutton(
            filter_section,
            text="Show channel 1 or [TX] data only",
            variable=self.contents_filter,
            value="channel1",
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Radiobutton(
            filter_section,
            text="Show channel 2 or [RX] data only",
            variable=self.contents_filter,
            value="channel2",
        ).pack(anchor=tk.W, pady=(0, 6))

        ttk.Radiobutton(
            filter_section,
            text="Hide all communication data, show comments only",
            variable=self.contents_filter,
            value="comments_only",
        ).pack(anchor=tk.W)

        alias_section = tk.Frame(parent, bg="#f0f0f0")
        alias_section.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            alias_section,
            text="Channel Alias",
            bg="#f0f0f0",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, pady=(0, 4))

        tk.Label(
            alias_section,
            text="Alternative labels for the two communication channels / data",
            bg="#f0f0f0",
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(0, 8))

        header = tk.Frame(alias_section, bg="#f0f0f0")
        header.pack(fill=tk.X, pady=(0, 4))
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)

        tk.Label(header, text="", bg="#f0f0f0", width=10).grid(row=0, column=0, sticky=tk.W)
        tk.Label(
            header,
            text="Original channel name",
            bg="#f0f0f0",
            font=("Segoe UI", 9),
        ).grid(row=0, column=1, sticky=tk.W, padx=(0, 8))
        tk.Label(
            header,
            text="Use this alias instead",
            bg="#f0f0f0",
            font=("Segoe UI", 9),
        ).grid(row=0, column=2, sticky=tk.W)

        channels = (("Channel 1", "TX"), ("Channel 2", "RX"))
        self.channel_alias_entries = []

        for row_index, (channel_label, default_name) in enumerate(channels, start=1):
            row = tk.Frame(alias_section, bg="#f0f0f0")
            row.pack(fill=tk.X, pady=4)
            row.columnconfigure(1, weight=1)
            row.columnconfigure(2, weight=1)

            tk.Label(
                row,
                text=channel_label,
                bg="#f0f0f0",
                font=("Segoe UI", 9),
                width=10,
                anchor=tk.W,
            ).grid(row=0, column=0, sticky=tk.W)

            original_entry = ttk.Entry(row)
            original_entry.insert(0, default_name)
            original_entry.config(state="readonly")
            original_entry.grid(row=0, column=1, sticky=tk.EW, padx=(0, 8))

            alias_entry = ttk.Entry(row)
            alias_entry.grid(row=0, column=2, sticky=tk.EW)
            self.channel_alias_entries.append(alias_entry)

    def _refresh_channel_ports(self, selected_channel=None):
        channel = (selected_channel or self.channel_combo.get() or "COM1").strip()
        ports = list_available_ports(include=channel)
        self.channel_combo["values"] = ports
        if ports:
            self.channel_combo.config(state="readonly")
            if channel in ports:
                self.channel_combo.set(channel)
            else:
                self.channel_combo.set(ports[0])
        else:
            self.channel_combo.config(state="normal")
            self.channel_combo.set(channel)

    def _load_settings(self, settings):
        self.comm_mode.set(settings.get("comm_mode", "send_receive"))
        self._refresh_channel_ports(settings.get("channel", "COM1"))

        for key, combo in self._com_port_combos.items():
            combo.set(settings.get(key, combo.get()))

        self.flow_control.set(settings.get("flow_control", "off"))
        self.contents_filter.set(settings.get("contents_filter", "all"))

        aliases = settings.get("channel_aliases", ("", ""))
        for index, entry in enumerate(self.channel_alias_entries):
            entry.delete(0, tk.END)
            if index < len(aliases):
                entry.insert(0, aliases[index])

    def _collect_settings(self):
        return {
            "comm_mode": self.comm_mode.get(),
            "channel": self.channel_combo.get().strip(),
            "baud_rate": self._com_port_combos["baud_rate"].get(),
            "data_bits": self._com_port_combos["data_bits"].get(),
            "parity": self._com_port_combos["parity"].get(),
            "stop_bits": self._com_port_combos["stop_bits"].get(),
            "parity_error_char": self._com_port_combos["parity_error_char"].get(),
            "flow_control": self.flow_control.get(),
            "contents_filter": self.contents_filter.get(),
            "channel_aliases": tuple(
                entry.get().strip() for entry in self.channel_alias_entries
            ),
        }

    def _on_ok(self):
        self.home.apply_project_settings(self._collect_settings())
        self.destroy()

    def _on_cancel(self):
        self.destroy()

    def _build_footer(self, parent):
        btn_group = tk.Frame(parent, bg="#f0f0f0")
        btn_group.pack(side=tk.RIGHT)

        ttk.Button(btn_group, text="OK", width=10, command=self._on_ok).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_group, text="Cancel", width=10, command=self._on_cancel).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_group, text="Help", width=10).pack(side=tk.LEFT)


if __name__ == "__main__":
    from core.settings_saver import ProjectSettings

    root = tk.Tk()
    root.withdraw()
    root.project_settings = ProjectSettings()
    root.apply_project_settings = lambda settings: root.project_settings.update(settings)
    ProjectSetting(root)
    root.mainloop()
