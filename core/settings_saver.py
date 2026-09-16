"""In-memory project settings for the current application session."""

from copy import deepcopy

DEFAULT_PROJECT_SETTINGS = {
    "comm_mode": "send_receive",
    "channel": "COM1",
    "baud_rate": "9600",
    "data_bits": "8",
    "parity": "None",
    "stop_bits": "1",
    "parity_error_char": "63 ('?')",
    "flow_control": "off",
    "contents_filter": "all",
    "channel_aliases": ("", ""),
}


class ProjectSettings:
    """Session-scoped settings that reset when the application exits."""

    def __init__(self, values=None):
        self._values = deepcopy(DEFAULT_PROJECT_SETTINGS)
        if values:
            self._values.update(values)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def as_dict(self):
        return deepcopy(self._values)

    def update(self, values):
        self._values.update(values)
