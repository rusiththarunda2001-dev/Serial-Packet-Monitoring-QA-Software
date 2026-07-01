"""Application UI routing between Docklight screens."""

import tkinter.messagebox as messagebox
from tkinter import filedialog

from core.checksum_rules import DEFAULT_CHECKSUM
from core.project_file import (
    PROJECT_FILE_EXTENSION,
    PROJECT_FILE_TYPES,
    ProjectFileError,
)
from core.receive_actions import (
    ReceiveActionConfig,
    parse_receive_action,
    receive_action_fields,
)
from ui.edit_receive_sequence import DEFAULT_CHECKSUM_DETECT, EditReceiveSequence
from ui.edit_send_request import EditSendRequest
from ui.project_setting import ProjectSetting


class Routes:
    """Handles navigation from the home page to modal dialogs."""

    def __init__(self, home):
        self.home = home
        self._open_dialog = None

    def bind(self):
        self.home.send_tree.bind("<ButtonRelease-1>", self.on_send_row_click)
        self.home.receive_tree.bind("<ButtonRelease-1>", self.on_receive_row_click)

    def show_dialog(self, dialog_factory):
        if self._open_dialog is not None and self._open_dialog.winfo_exists():
            self._open_dialog.lift()
            self._open_dialog.focus_force()
            return

        dialog = dialog_factory()
        self._open_dialog = dialog
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Destroy>", self._on_dialog_closed, add="+")

    def _on_dialog_closed(self, _event):
        self._open_dialog = None

    def open_project_settings(self):
        def create_dialog():
            return ProjectSetting(self.home)

        self.show_dialog(create_dialog)

    def new_project(self):
        if not self.home.confirm_discard_unsaved_changes():
            return

        self.home.reset_project_state()
        self.home.mark_project_clean(path=None)

    def open_project(self):
        if not self.home.confirm_discard_unsaved_changes():
            return

        path = filedialog.askopenfilename(
            parent=self.home,
            title="Open Project",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not path:
            return

        try:
            self.home.load_project_from_path(path)
        except ProjectFileError as exc:
            messagebox.showerror("Open Project", str(exc), parent=self.home)

    def save_project(self):
        path = self.home.get_project_path()
        if not path:
            return self.save_project_as()

        try:
            self.home.save_project_to_path(path)
        except ProjectFileError as exc:
            messagebox.showerror("Save Project", str(exc), parent=self.home)
            return False
        return True

    def save_project_as(self):
        initial = self.home.get_project_path()
        if not initial:
            initial = "Untitled{}".format(PROJECT_FILE_EXTENSION)

        path = filedialog.asksaveasfilename(
            parent=self.home,
            title="Save Project As",
            defaultextension=PROJECT_FILE_EXTENSION,
            initialfile=initial,
            filetypes=PROJECT_FILE_TYPES,
        )
        if not path:
            return False

        try:
            self.home.save_project_to_path(path)
        except ProjectFileError as exc:
            messagebox.showerror("Save Project", str(exc), parent=self.home)
            return False
        return True

    def start_communication(self):
        if self.home.comm_service.is_connected():
            port = self.home.project_settings.get("channel")
            self.home.port_status.set("Communication port {} open".format(port))
            return

        try:
            self.home.comm_service.connect(self.home.project_settings.as_dict())
        except Exception as exc:
            messagebox.showerror(
                "Communication Error",
                "Could not open {}:\n{}".format(
                    self.home.project_settings.get("channel"),
                    exc,
                ),
                parent=self.home,
            )
            self.home._communication_open = False
            self.home.port_status.set("Communication port closed")
            return

        port = self.home.project_settings.get("channel")
        self.home._communication_open = True
        self.home.port_status.set("Communication port {} open".format(port))

    def stop_communication(self):
        self.home.set_keyboard_console_enabled(False)
        self.home.stop_repeat_senders()
        self.home.comm_service.disconnect()
        self.home._communication_open = False
        self.home.port_status.set("Communication port closed")

    def toggle_keyboard_console(self):
        if self.home._keyboard_console_enabled:
            self.home.set_keyboard_console_enabled(False)
            return

        if self.home.project_settings.get("comm_mode") != "send_receive":
            messagebox.showwarning(
                "Keyboard Console",
                "The keyboard console is only available in Send/Receive mode.",
                parent=self.home,
            )
            return

        if not self.home.comm_service.is_connected():
            messagebox.showwarning(
                "Keyboard Console",
                "Start communication before using the keyboard console.",
                parent=self.home,
            )
            return

        self.home.set_keyboard_console_enabled(True)

    def open_send_sequence_editor(self, row_index):
        if not (0 <= row_index < len(self.home._send_rows)):
            return

        row_count = len(self.home._send_rows)
        send_row = self.home.get_send_row(row_index)

        def create_dialog():
            return EditSendRequest(
                self.home,
                row_index=row_index,
                index=str(row_index + 1),
                name=send_row[1],
                sequence=send_row[2],
                row_count=row_count,
                periodic=send_row[3],
                repeat_interval=send_row[6],
                checksum=send_row[4],
                display_mode=self.home.get_display_mode(),
            )

        self.show_dialog(create_dialog)

    def add_send_sequence(self):
        self.home._send_rows.append(
            (
                "",
                "New Sequence",
                "",
                False,
                DEFAULT_CHECKSUM,
                self.home.get_display_mode(),
                0.0,
            )
        )
        self.home._refresh_send_tree()
        self.home.mark_project_dirty()
        self.open_send_sequence_editor(len(self.home._send_rows) - 1)

    def open_receive_sequence_editor(self, row_index):
        if not (0 <= row_index < len(self.home._receive_rows)):
            return

        row_count = len(self.home._receive_rows)
        row = self.home.get_receive_row(row_index)
        action = parse_receive_action(row, row[1])

        def create_dialog():
            return EditReceiveSequence(
                self.home,
                row_index=row_index,
                index=str(row_index + 1),
                name=row[1],
                sequence=row[2],
                row_count=row_count,
                checksum=row[3],
                checksum_detect=row[4],
                display_mode=self.home.get_display_mode(),
                action=action,
            )

        self.show_dialog(create_dialog)

    def add_receive_sequence(self):
        default_action = ReceiveActionConfig()
        self.home._receive_rows.append(
            (
                "☐",
                "New Sequence",
                "",
                DEFAULT_CHECKSUM,
                DEFAULT_CHECKSUM_DETECT,
                self.home.get_display_mode(),
                *receive_action_fields(default_action),
            )
        )
        self.home._refresh_receive_tree()
        self.home.mark_project_dirty()
        self.open_receive_sequence_editor(len(self.home._receive_rows) - 1)

    def on_send_row_click(self, event):
        column = self.home.send_tree.identify_column(event.x)
        if column == "#1":
            return

        row_id = self.home.send_tree.identify_row(event.y)
        if not row_id:
            return

        self.home.send_tree.selection_set(row_id)
        row_index = self.home.send_tree.index(row_id)
        self.open_send_sequence_editor(row_index)

    def on_receive_row_click(self, event):
        column = self.home.receive_tree.identify_column(event.x)
        row_id = self.home.receive_tree.identify_row(event.y)
        if not row_id:
            return

        if column == "#1":
            self._toggle_receive_active(row_id)
            return

        self.home.receive_tree.selection_set(row_id)
        row_index = self.home.receive_tree.index(row_id)
        self.open_receive_sequence_editor(row_index)

    def _toggle_receive_active(self, row_id):
        values = list(self.home.receive_tree.item(row_id, "values"))
        values[0] = "☐" if values[0] == "☑" else "☑"
        self.home.receive_tree.item(row_id, values=values)

        row_index = self.home.receive_tree.index(row_id)
        if 0 <= row_index < len(self.home._receive_rows):
            row = list(self.home.get_receive_row(row_index))
            row[0] = values[0]
            self.home._receive_rows[row_index] = tuple(row)
            self.home.mark_project_dirty()


if __name__ == "__main__":
    print("routes.py is not the app entry point.")
    print("Run main.py instead:")
    print("  .venv\\Scripts\\python.exe main.py")
    print("Or double-click run.bat")
