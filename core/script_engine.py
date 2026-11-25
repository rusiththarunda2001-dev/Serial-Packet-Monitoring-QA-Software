"""Simple script engine.

Scripts are lines of simple commands typed in the script grid, for example:

    StartCommunication()
    SendSequence("Ping", 100, 3)
    WaitForSequence("Pong", 1, 1000)
    Createlog("test_log.txt", "ASCII")

The script runs on a background thread. Everything that touches the window or
the serial port is handed to the Tk (UI) thread, and every command waits until
that work is really done before the next line runs.

All messages shown to the user are written in plain language: the people who
write these scripts are not programmers.
"""

import ast
import difflib
import inspect
import sys
import threading
import time
import traceback
import tkinter.messagebox as messagebox
from pathlib import Path

from core.comm_service import IDLE_FLUSH_SECONDS
from core.sequence_codec import SequenceEncodeError, count_wildcards, parse_parameter_values

SCRIPT_FILENAME = "<script>"
APP_DIR = Path(__file__).resolve().parent.parent

# An example of each command, shown when a command is written the wrong way.
COMMAND_EXAMPLES = {
    "Pause": "Pause(500)   (wait 500 milliseconds)",
    "Comment": 'Comment("Test started")',
    "SendSequence": ('SendSequence("Ping", 100, 3)   (send "Ping" 3 times, 100 ms apart)   or   '
                     'SendSequence("Read", 0, 1, "05")   (fill the ? byte of "Read" with 05, '
                     'e.g. the device address)'),
    "StartCommunication": "StartCommunication()",
    "WaitForSequence": 'WaitForSequence("Pong", 1, 1000)   (wait up to 1000 ms for "Pong" once)',
    "GetReceiveCounter": 'GetReceiveCounter("Pong")   (how many times "Pong" was received since the script started)',
    "ResetReceiveCounter": "ResetReceiveCounter()   (count received sequences from 0 again)",
    "StopCommunication": "StopCommunication()",
    "Createlog": 'Createlog("log.txt", "ASCII")   (save the ASCII tab to log.txt)',
    "ClearScreen": "ClearScreen()",
    "StartLogging": 'StartLogging("test_log.txt", "ASCII")   (save everything from now on to test_log.txt)',
    "StopLogging": "StopLogging()",
    "SetRTS": 'SetRTS("ON")   or   SetRTS("OFF")',
    "SetDTR": 'SetDTR("ON")   or   SetDTR("OFF")',
    "ShowMessage": 'ShowMessage("Switch on the device, then click OK")',
}

ON_OFF_VALUES = {
    "on": True, "off": False,
    "true": True, "false": False,
    "1": True, "0": False,
}
# Kept for code that refers to the old name.
COMMAND_USAGE = COMMAND_EXAMPLES

LOG_TYPES = {
    "hex": "HEX",
    "ascii": "ASCII",
    "decimal": "Decimal",
    "binary": "Binary",
}

# Only harmless helpers are available inside scripts (no import, open, exec...).
SAFE_BUILTINS = {
    "str": str,
    "int": int,
    "float": float,
    "len": len,
    "range": range,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
}

# Longest time Createlog/StopCommunication wait for queued data to be sent.
SEND_FLUSH_TIMEOUT = 5.0
# Time given to a device to answer before Createlog saves the window. Received
# bytes are shown only after a quiet gap of IDLE_FLUSH_SECONDS, so wait longer.
LOG_SETTLE_TIME = IDLE_FLUSH_SECONDS + 0.1

NOT_STARTED_MESSAGE = (
    "Communication is not started. Press the Play button in the toolbar first, "
    "or add StartCommunication() at the top of the script."
)


class ScriptCommandError(Exception):
    """A command was used wrongly or could not do its job; stops the script."""


class ScriptRun:
    """State of one script run. A stopped run stays stopped even if a new run starts."""

    def __init__(self):
        self._stopped = threading.Event()

    def stop(self):
        self._stopped.set()

    def is_stopped(self):
        return self._stopped.is_set()


# ----------------------------------------------------------------------
# Error messages
# ----------------------------------------------------------------------

def _script_line(error):
    """Grid row of the script line where the error happened, if known."""
    if isinstance(error, SyntaxError) and error.filename == SCRIPT_FILENAME:
        return error.lineno
    frames = [
        frame
        for frame in traceback.extract_tb(error.__traceback__)
        if frame.filename == SCRIPT_FILENAME
    ]
    return frames[-1].lineno if frames else None


def _current_script_row():
    """Grid row of the script line that is running now (called from a command)."""
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_filename == SCRIPT_FILENAME:
            return frame.f_lineno
        frame = frame.f_back
    return None


def _unknown_command_message(name):
    name = str(name)
    by_case = {command.lower(): command for command in COMMAND_EXAMPLES}
    if name.lower() in by_case:
        right = by_case[name.lower()]
        return '"{}" must be written with the same capital letters: {}'.format(name, right)

    message = '"{}" is not a known command.'.format(name)
    close = difflib.get_close_matches(name, list(COMMAND_EXAMPLES), n=1, cutoff=0.6)
    if close:
        return message + " Did you mean {}?".format(close[0])
    return message + " The commands you can use are: {}.".format(", ".join(COMMAND_EXAMPLES))


SYNTAX_MESSAGE = (
    'This line is not written correctly. Check that text is inside "quotes", '
    "every bracket is closed and values are separated by commas. "
    'Example: SendSequence("Ping", 100, 3)'
)


def _format_script_error(error):
    """Turn any script failure into one plain-language line for the window."""
    if isinstance(error, ScriptCommandError):
        details = str(error)
    elif isinstance(error, SyntaxError):
        details = SYNTAX_MESSAGE
    elif isinstance(error, NameError):
        details = _unknown_command_message(getattr(error, "name", None) or error)
    elif isinstance(error, ImportError):
        details = "Lines starting with import are not allowed in a script."
    else:
        details = "Something went wrong on this line ({}).".format(error)

    line_number = _script_line(error)
    if line_number is not None:
        return "Script stopped at row {}: {}".format(line_number, details)
    return "Script stopped: {}".format(details)


def _check_script_lines(tree):
    """Find lines that Python accepts but that do nothing, e.g. 'ClearScreen'."""
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Name):
            name = node.value.id
            if name in COMMAND_EXAMPLES:
                return node.lineno, "{} needs brackets at the end, like this: {}".format(
                    name, COMMAND_EXAMPLES[name])
    return None


def _standalone_call_rows(tree, command):
    """Rows where `command(...)` is a statement of its own (its result is not used)."""
    rows = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == command):
            rows.add(node.lineno)
    return rows


def _shown(value):
    """How a value the user typed is quoted back in a message."""
    if isinstance(value, str):
        return '"{}"'.format(value)
    return str(value)


class CustomScriptCommands:
    """The simple commands available to scripts."""

    def __init__(self, home_page, run=None):
        self.home = home_page
        self.run = run or ScriptRun()
        # Receive detections made after this snapshot count for WaitForSequence.
        self._receive_baseline = home_page.receive_match_totals()
        # ... and for GetReceiveCounter (moved forward by ResetReceiveCounter only).
        self._counter_baseline = dict(self._receive_baseline)
        self._counter_reset = False
        # Script rows where GetReceiveCounter(...) stands alone (result is shown).
        self.show_counter_rows = set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stopped(self):
        return self.run.is_stopped()

    def _paused(self):
        return getattr(self.home, "_script_paused", False) and not self._stopped()

    def _check_stop(self):
        if self._stopped():
            raise SystemExit()

    def _wait_while_paused(self):
        while self._paused():
            time.sleep(0.05)
        self._check_stop()

    def _sleep_ms(self, milliseconds):
        """Sleep that reacts to Stop at once and holds the clock while paused."""
        remaining = milliseconds / 1000.0
        last = time.monotonic()
        while True:
            self._check_stop()
            now = time.monotonic()
            if not self._paused():
                remaining -= now - last
            last = now
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))

    def _post(self, func):
        """Run func on the Tk thread without waiting (used for log lines)."""
        try:
            self.home.after(0, func)
        except Exception:
            raise SystemExit()  # the window is closing

    def _run_on_ui(self, func):
        """Run func on the Tk thread, wait until it is done and return its result."""
        done = threading.Event()
        box = {}

        def task():
            try:
                box["result"] = func()
            except BaseException as exc:  # handed back to the script thread
                box["error"] = exc
            finally:
                done.set()

        self._post(task)
        while not done.wait(0.05):
            self._check_stop()
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def _log(self, text, tag="status"):
        self._post(lambda: self.home._append_comm_line(text, tag=tag, show_channel=False))

    def _flush_display(self, settle=0.0):
        """Wait until queued sends are written and everything received is shown."""
        comm = self.home.comm_service
        deadline = time.monotonic() + SEND_FLUSH_TIMEOUT
        while comm.pending_sends() > 0 and comm.is_connected():
            self._check_stop()
            if time.monotonic() >= deadline:
                break  # device holds off (flow control); do not hang the script
            time.sleep(0.01)
        if settle > 0 and comm.is_connected():
            self._sleep_ms(settle * 1000)
        self._run_on_ui(self.home.drain_comm_events)

    def _open_communication(self):
        """Open the port(s) and wait; stop the script with the reason if it fails."""
        reason = self._run_on_ui(
            lambda: self.home.routes.start_communication(show_error=False)
        )
        if not self.home.comm_service.is_connected():
            raise ScriptCommandError("Could not start communication. {}".format(
                reason or "The COM port could not be opened."))

    @staticmethod
    def _number(value, label, example, minimum=None, unit=""):
        """Read a number the user typed, with a plain-language error."""
        number = None
        if isinstance(value, bool):
            number = None
        elif isinstance(value, int):
            number = value
        elif isinstance(value, float) and value.is_integer():
            number = int(value)
        elif isinstance(value, str):
            try:
                number = int(value.strip())
            except ValueError:
                number = None
        if number is None:
            raise ScriptCommandError(
                "{} must be a number{}. You wrote {}. Example: {}".format(
                    label, unit, _shown(value), example)
            )
        if minimum is not None and number < minimum:
            if minimum == 0:
                rule = "cannot be below 0"
            else:
                rule = "must be at least {}".format(minimum)
            raise ScriptCommandError(
                "{} {}. You wrote {}. Example: {}".format(label, rule, number, example)
            )
        return number

    def _find_send_index(self, name):
        names = [str(row[1]) for row in self.home._send_rows]
        if name in names:
            return names.index(name)
        wanted = name.strip().casefold()
        for index, row_name in enumerate(names):
            if row_name.strip().casefold() == wanted:
                return index
        raise ScriptCommandError(
            'There is no send sequence called "{}". Check the name in the Send '
            "Sequences list.".format(name)
        )

    def _find_receive_index(self, name_or_index, command="WaitForSequence"):
        if isinstance(name_or_index, bool) or not isinstance(name_or_index, (str, int)):
            raise ScriptCommandError(
                "{} needs the name of a receive sequence in quotes. "
                "Example: {}".format(command, COMMAND_EXAMPLES[command])
            )
        try:
            return self.home.find_receive_row_index(name_or_index)
        except ValueError:
            if isinstance(name_or_index, int):
                raise ScriptCommandError(
                    "There is no receive sequence number {}.".format(name_or_index))
            raise ScriptCommandError(
                'There is no receive sequence called "{}". Check the name in the '
                "Receive Sequences list.".format(name_or_index)
            )

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def Pause(self, milliseconds):
        """Waits the given number of milliseconds."""
        delay = self._number(
            milliseconds, "The time in Pause", COMMAND_EXAMPLES["Pause"],
            minimum=0, unit=" of milliseconds (no letters)",
        )
        self._wait_while_paused()
        self._sleep_ms(delay)

    def Comment(self, message):
        """Prints a message with a timestamp, followed by a blank line."""
        text = str(message)
        self._wait_while_paused()
        self._flush_display()  # keep the comment after data already sent

        def _show():
            timestamp = self.home._format_comm_timestamp()
            self.home._append_comm_line(
                "{} - {}".format(timestamp, text), tag="status", show_channel=False
            )
            self.home._append_comm_blank_line()

        self._run_on_ui(_show)

    def SendSequence(self, sequence_name, frequency, count, parameters=None):
        """Sends a named sequence count times, waiting frequency milliseconds between sends.

        parameters: values for the ? bytes of the sequence (e.g. the device
        address on an RS485 bus), as HEX text "05" / "05 0A" or a number 0-255.
        """
        example = COMMAND_EXAMPLES["SendSequence"]
        name = str(sequence_name)
        interval = self._number(
            frequency, "The time between sends in SendSequence", example,
            minimum=0, unit=" of milliseconds (no letters)",
        )
        loops = self._number(
            count, "The number of sends in SendSequence", example, minimum=1,
        )
        index = self._find_send_index(name)
        params = self._send_parameters(index, parameters)

        comm = self.home.comm_service
        if not comm.is_connected():
            raise ScriptCommandError(NOT_STARTED_MESSAGE)
        if comm.is_monitoring():
            raise ScriptCommandError(
                "Sending is not possible in Monitoring mode. Switch to Send/Receive "
                "mode in Project Settings."
            )

        for number in range(loops):
            self._wait_while_paused()
            error = self._run_on_ui(lambda: self.home.send_sequence_for_script(index, params))
            if error:
                raise ScriptCommandError(self._send_failed_message(name, error))
            if number < loops - 1:  # no extra wait after the last send
                self._sleep_ms(interval)

    def _send_parameters(self, index, parameters):
        """Check the values for the ? bytes of send sequence index; returns bytes or None."""
        row = self.home.get_send_row(index)
        name, sequence = row[1], row[2]
        needed = count_wildcards(sequence)
        example = 'SendSequence("{}", 0, 1, "{}")'.format(name, " ".join(["05"] * max(1, needed)))
        if not needed:
            if parameters is None:
                return None
            raise ScriptCommandError(
                'The send sequence "{}" has no parameter bytes (?), so it does not need the '
                "4th value. Remove it, or put a ? in the sequence where the value goes "
                "(e.g. the device address).".format(name))
        if parameters is None:
            raise ScriptCommandError(
                'The send sequence "{}" has {} parameter byte(s) (?), for example the device '
                "address. Give the value(s) as the 4th value: {}".format(name, needed, example))
        try:
            values = parse_parameter_values(parameters)
        except SequenceEncodeError as exc:
            raise ScriptCommandError(
                "The 4th value of SendSequence is not valid: {}. Example: {}".format(exc, example))
        if len(values) != needed:
            raise ScriptCommandError(
                'The send sequence "{}" has {} parameter byte(s) (?) but {} value(s) were given. '
                "Example: {}".format(name, needed, len(values), example))
        return values

    def _send_failed_message(self, name, error):
        if error == "communication is not started":
            return NOT_STARTED_MESSAGE
        if "queue is full" in error:
            return (
                'Could not send "{}": the device is not accepting data. Check the '
                "cable and the Flow Control setting."
            ).format(name)
        if error == "the send sequence no longer exists":
            return 'The send sequence "{}" was removed while the script was running.'.format(name)
        if "not connected" in error.lower() or "not open" in error.lower():
            return NOT_STARTED_MESSAGE
        return (
            'Could not send "{}": the sequence is empty or not written correctly. '
            "Open it in the Send Sequences list and check it."
        ).format(name)

    def StartCommunication(self):
        """Opens the COM port(s) and waits until they are open."""
        self._wait_while_paused()
        self._open_communication()

    def WaitForSequence(self, nameOrIndex, maxCounter=1, timeout=-1):
        """Waits for an active receive sequence and returns how often it was detected."""
        example = COMMAND_EXAMPLES["WaitForSequence"]
        max_counter = self._number(maxCounter, "The count in WaitForSequence", example)
        if max_counter == 0 or max_counter < -1:
            raise ScriptCommandError(
                "The count in WaitForSequence must be 1 or more (or -1 to count until "
                "the time is up). You wrote {}.".format(max_counter)
            )
        timeout_ms = self._number(
            timeout, "The wait time in WaitForSequence", example,
            unit=" of milliseconds (no letters)",
        )
        if timeout_ms < -1:
            raise ScriptCommandError(
                "The wait time in WaitForSequence must be 0 or more (or -1 to wait "
                "with no time limit). You wrote {}.".format(timeout_ms)
            )
        if max_counter == -1 and timeout_ms == -1:
            raise ScriptCommandError(
                "WaitForSequence with count -1 also needs a wait time, otherwise it "
                'would wait forever. Example: WaitForSequence("Pong", -1, 5000)'
            )

        row_index = self._find_receive_index(nameOrIndex)
        row = self.home.get_receive_row(row_index)
        name = row[1]
        if row[0] != "☑":
            raise ScriptCommandError(
                'The receive sequence "{}" is switched off. Tick its box in the '
                "Receive Sequences list first.".format(name)
            )

        self._wait_while_paused()
        if not self.home.comm_service.is_connected():
            self._open_communication()

        try:
            count = self.home.wait_for_receive_sequence(
                row_index,
                max_counter=max_counter,
                timeout=timeout_ms,
                since=self._receive_baseline,
                should_stop=self._stopped,
                is_paused=self._paused,
            )
        except (ValueError, RuntimeError):
            if not self.home.comm_service.is_connected():
                raise ScriptCommandError(
                    'Communication was stopped while waiting for "{}".'.format(name))
            raise ScriptCommandError('Could not wait for "{}".'.format(name))

        # Detections up to now are used up; the next wait counts new ones only.
        self._receive_baseline[row_index] = self.home.receive_match_totals().get(row_index, 0)

        row_number = _current_script_row()
        prefix = "Row {}: ".format(row_number) if row_number else ""
        if max_counter == -1:
            self._log('{}"{}" was received {} time(s) in {} ms.'.format(
                prefix, name, count, timeout_ms))
        elif count < max_counter:
            if count == 0:
                what = '"{}" was not received'.format(name)
            else:
                what = '"{}" was received only {} of {} times'.format(name, count, max_counter)
            self._log(
                "{}{} within {} ms. The script continues.".format(prefix, what, timeout_ms),
                tag="error",
            )
        return count

    def GetReceiveCounter(self, nameOrIndex):
        """How many times an active receive sequence was detected since the script
        started (or since the last ResetReceiveCounter). Does not wait."""
        row_index = self._find_receive_index(nameOrIndex, "GetReceiveCounter")
        name = self.home.get_receive_row(row_index)[1]
        if self.home.get_receive_row(row_index)[0] != "☑":
            raise ScriptCommandError(
                'The receive sequence "{}" is switched off, so it is never counted. Tick '
                "its box in the Receive Sequences list first.".format(name)
            )
        self._wait_while_paused()
        # Show (and so detect) everything that has already arrived before counting.
        if self.home.comm_service.is_connected():
            self._flush_display()
        total = self.home.receive_match_totals().get(row_index, 0)
        count = max(0, total - self._counter_baseline.get(row_index, 0))

        # On a row of its own the result is shown; inside an "if" it is only used.
        row_number = _current_script_row()
        if row_number in self.show_counter_rows:
            since = "the counters were reset" if self._counter_reset else "the script started"
            self._log('Row {}: "{}" was received {} time(s) since {}.'.format(
                row_number, name, count, since), tag="meta")
        return count

    def ResetReceiveCounter(self):
        """Counts all receive sequences from 0 again (GetReceiveCounter and
        WaitForSequence only count what is received after this line)."""
        self._wait_while_paused()
        if self.home.comm_service.is_connected():
            self._flush_display()  # data from before this line is counted before the reset
        totals = self.home.receive_match_totals()
        self._counter_baseline = dict(totals)
        self._receive_baseline = dict(totals)
        self._counter_reset = True
        self._log("Receive counters set to 0.", tag="meta")

    def StopCommunication(self):
        """Sends what is still queued, then closes the COM port(s)."""
        self._wait_while_paused()
        if self.home.comm_service.is_connected():
            self._flush_display()
        self._run_on_ui(self.home.routes.stop_communication)

    def _log_type(self, command, log_type):
        key = str(log_type).strip().lower()
        if key not in LOG_TYPES:
            raise ScriptCommandError(
                'The log type {} is not known. Use "HEX", "ASCII", "Decimal" or '
                '"Binary". Example: {}'.format(_shown(log_type), COMMAND_EXAMPLES[command])
            )
        return LOG_TYPES[key]

    def _log_path(self, command, path):
        """Full path of a log file. A plain name goes next to the project file
        (or the application folder if the project is not saved yet); '.txt' is
        added when the name has no extension."""
        file_name = str(path).strip()
        if not file_name:
            raise ScriptCommandError(
                "{} needs a file name. Example: {}".format(command, COMMAND_EXAMPLES[command]))
        file_path = Path(file_name).expanduser()
        if not file_path.suffix:
            file_path = file_path.with_name(file_path.name + ".txt")
        if not file_path.is_absolute():
            project_path = self.home.get_project_path()
            base = Path(project_path).parent if project_path else APP_DIR
            file_path = base / file_path
        if not file_path.parent.is_dir():
            raise ScriptCommandError(
                'Could not save the log: the folder "{}" does not exist.'.format(file_path.parent)
            )
        return file_path

    def Createlog(self, path, log_type):
        """Saves the contents of one communication tab to a text file."""
        tab_name = self._log_type("Createlog", log_type)
        file_path = self._log_path("Createlog", path)

        self._wait_while_paused()
        self._flush_display(settle=LOG_SETTLE_TIME)

        def _read_tab():
            widget = self.home._comm_texts.get(tab_name)
            return None if widget is None else widget.get("1.0", "end-1c")

        content = self._run_on_ui(_read_tab)
        if content is None:
            raise ScriptCommandError('Could not save the log: the "{}" tab was not found.'.format(tab_name))

        replaced = file_path.exists()
        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(content)
        except PermissionError:
            raise ScriptCommandError(
                'Could not save the log to "{}". The file may be open in another '
                "program, or the folder may be read-only.".format(file_path))
        except OSError:
            raise ScriptCommandError(
                'Could not save the log to "{}". Check the file name and folder.'.format(file_path))

        self._log("Log saved to {}{}".format(
            file_path, " (the old file was replaced)" if replaced else ""), tag="meta")

    def ClearScreen(self):
        """Clears the communication window."""
        self._wait_while_paused()
        self._flush_display()
        self._run_on_ui(self.home._clear_communication_panel)

    def StartLogging(self, path, log_type):
        """Saves everything shown in one tab to a file, from now until StopLogging()
        or the end of the script. An existing file is added to, not replaced."""
        tab_name = self._log_type("StartLogging", log_type)
        file_path = self._log_path("StartLogging", path)

        self._wait_while_paused()
        self._flush_display()  # data from before this line is not logged
        existed = file_path.exists()
        was_logging = self.home.is_comm_logging()

        def _start():
            self.home.start_comm_log(str(file_path), tab_name, owner=self.run)

        try:
            self._run_on_ui(_start)
        except PermissionError:
            raise ScriptCommandError(
                'Could not start logging to "{}". The file may be open in another '
                "program, or the folder may be read-only.".format(file_path))
        except OSError:
            raise ScriptCommandError(
                'Could not start logging to "{}". Check the file name and folder.'.format(file_path))

        note = ""
        if was_logging:
            note = " The previous log file was closed."
        if existed:
            note += " New data is added to the end of the existing file."
        self._run_on_ui(lambda: self.home._append_comm_line(
            "Logging started: {} ({}).{}".format(file_path, tab_name, note),
            tag="meta", show_channel=False))

    def StopLogging(self):
        """Stops StartLogging() and closes the log file."""
        self._wait_while_paused()
        if not self.home.is_comm_logging():
            self._log("Logging was not running, so there was nothing to stop.", tag="meta")
            return
        self._flush_display(settle=LOG_SETTLE_TIME)  # include the last replies

        def _stop():
            path = self.home._comm_log["path"]
            self.home._append_comm_line(
                "Logging stopped. The log is saved in {}".format(path),
                tag="meta", show_channel=False)
            self.home.stop_comm_log()

        self._run_on_ui(_stop)

    def _set_line(self, command, line_name, value):
        key = str(value).strip().lower()
        if isinstance(value, bool):
            state = value
        elif key in ON_OFF_VALUES:
            state = ON_OFF_VALUES[key]
        else:
            raise ScriptCommandError(
                '{} needs "ON" or "OFF". You wrote {}. Example: {}'.format(
                    command, _shown(value), COMMAND_EXAMPLES[command]))

        if self.home.is_monitoring_mode():
            raise ScriptCommandError(
                "{} is not possible in Monitoring mode. Switch to Send/Receive mode "
                "in Project Settings.".format(command))
        if self.home.project_settings.get("flow_control") != "manual":
            raise ScriptCommandError(
                '{} only works when Flow Control is set to "Manual" in Project '
                "Settings.".format(command))

        self._wait_while_paused()
        self._flush_display()  # data sent before this line goes out first

        def _apply():
            self.home.comm_service.configure_session(self.home.project_settings.as_dict())
            self.home.comm_service.set_manual_handshake(**{line_name: state})
            self.home._refresh_handshake_indicators()
            self.home._append_comm_line(
                "{} set to {}".format(line_name.upper(), "ON" if state else "OFF"),
                tag="meta", show_channel=False)

        self._run_on_ui(_apply)

    def SetRTS(self, state):
        """Switches the RTS line ON or OFF (Flow Control must be Manual)."""
        self._set_line("SetRTS", "rts", state)

    def SetDTR(self, state):
        """Switches the DTR line ON or OFF (Flow Control must be Manual)."""
        self._set_line("SetDTR", "dtr", state)

    def ShowMessage(self, message):
        """Shows a message and waits until the user clicks OK."""
        text = str(message)
        self._wait_while_paused()
        self._flush_display()
        self._run_on_ui(lambda: messagebox.showinfo("Script", text, parent=self.home))
        self._check_stop()


def _checked(command, func):
    """Wrap a command so a missing or extra value gives a readable message."""
    signature = inspect.signature(func)

    def wrapper(*args, **kwargs):
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            raise ScriptCommandError(
                "{} is missing a value or has too many. Write it like this: {}".format(
                    command, COMMAND_EXAMPLES[command]))
        return func(*args, **kwargs)

    return wrapper


_NO_VALUE = object()


def _literal(node):
    """The value written in the script for this argument, or _NO_VALUE if it is
    not a plain value (for example a variable)."""
    try:
        return ast.literal_eval(node)
    except Exception:
        return _NO_VALUE


def _matches_name(name, names):
    if name in names:
        return True
    wanted = name.strip().casefold()
    return any(str(item).strip().casefold() == wanted for item in names)


def _check_command_values(name, args, send_names, receive_rows):
    """Problems with the plain values given to one command (nothing is run)."""
    values = [_literal(arg) for arg in args]

    def number_problem(index, label, minimum=None, unit=""):
        if index >= len(values) or values[index] is _NO_VALUE:
            return None
        try:
            CustomScriptCommands._number(
                values[index], label, COMMAND_EXAMPLES[name], minimum=minimum, unit=unit)
        except ScriptCommandError as exc:
            return str(exc)
        return None

    ms = " of milliseconds (no letters)"
    problems = []
    if name == "Pause":
        problems.append(number_problem(0, "The time in Pause", 0, ms))
    elif name == "SendSequence":
        if values and isinstance(values[0], str) and send_names is not None:
            if not _matches_name(values[0], send_names):
                problems.append(
                    'There is no send sequence called "{}". Check the name in the Send '
                    "Sequences list.".format(values[0]))
        problems.append(number_problem(1, "The time between sends in SendSequence", 0, ms))
        problems.append(number_problem(2, "The number of sends in SendSequence", 1))
        if len(values) > 3 and values[3] is not _NO_VALUE:
            try:
                parse_parameter_values(values[3])
            except SequenceEncodeError as exc:
                problems.append("The 4th value of SendSequence is not valid: {}.".format(exc))
    elif name in ("WaitForSequence", "GetReceiveCounter"):
        if values and isinstance(values[0], str) and receive_rows is not None:
            found = [active for row_name, active in receive_rows
                     if _matches_name(values[0], [row_name])]
            if not found:
                problems.append(
                    'There is no receive sequence called "{}". Check the name in the '
                    "Receive Sequences list.".format(values[0]))
            elif not found[0]:
                problems.append(
                    'The receive sequence "{}" is switched off. Tick its box in the '
                    "Receive Sequences list first.".format(values[0]))
        if name == "WaitForSequence":
            problems.append(number_problem(1, "The count in WaitForSequence"))
            problems.append(number_problem(2, "The wait time in WaitForSequence", unit=ms))
    elif name in ("Createlog", "StartLogging"):
        if len(values) > 1 and values[1] is not _NO_VALUE:
            if str(values[1]).strip().lower() not in LOG_TYPES:
                problems.append(
                    'The log type {} is not known. Use "HEX", "ASCII", "Decimal" or '
                    '"Binary". Example: {}'.format(_shown(values[1]), COMMAND_EXAMPLES[name]))
    elif name in ("SetRTS", "SetDTR"):
        if values and values[0] is not _NO_VALUE and not isinstance(values[0], bool):
            if str(values[0]).strip().lower() not in ON_OFF_VALUES:
                problems.append('{} needs "ON" or "OFF". You wrote {}. Example: {}'.format(
                    name, _shown(values[0]), COMMAND_EXAMPLES[name]))
    return [problem for problem in problems if problem]


def check_script(script_text, send_names=None, receive_rows=None):
    """Read a script without running it and list its problems.

    send_names: names of the send sequences (None = do not check names).
    receive_rows: list of (name, is_active) for the receive sequences.
    Returns a list of plain-language messages, each starting with the row.
    """
    try:
        tree = ast.parse(script_text, SCRIPT_FILENAME)
    except SyntaxError as exc:
        return ["Row {}: {}".format(exc.lineno or 1, SYNTAX_MESSAGE)]

    problems = []
    for statement in tree.body:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            problems.append((statement.lineno,
                             "Lines starting with import are not allowed in a script."))
            continue
        if (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Name)
                and statement.value.id in COMMAND_EXAMPLES):
            name = statement.value.id
            problems.append((statement.lineno, "{} needs brackets at the end, like this: {}".format(
                name, COMMAND_EXAMPLES[name])))
            continue
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name):
                problems.append((node.lineno, "This line uses something that is not a script "
                                 "command. The commands you can use are: {}.".format(
                                     ", ".join(COMMAND_EXAMPLES))))
                continue
            name = node.func.id
            if name in SAFE_BUILTINS:
                continue
            if name not in COMMAND_EXAMPLES:
                problems.append((node.lineno, _unknown_command_message(name)))
                continue
            signature = inspect.signature(getattr(CustomScriptCommands, name))
            try:
                signature.bind(None, *node.args, **{kw.arg: kw.value for kw in node.keywords if kw.arg})
            except TypeError:
                problems.append((node.lineno, "{} is missing a value or has too many. Write it "
                                 "like this: {}".format(name, COMMAND_EXAMPLES[name])))
                continue
            for message in _check_command_values(name, node.args, send_names, receive_rows):
                problems.append((node.lineno, message))

    problems.sort(key=lambda item: item[0])
    return ["Row {}: {}".format(row, message) for row, message in problems]


def run_script(script_text, home_page):
    """Runs the script on a background thread."""
    previous = getattr(home_page, "_active_script", None)
    if previous is not None:
        previous.stop()

    run = ScriptRun()
    home_page._active_script = run
    home_page._script_paused = False
    home_page._script_stopped = False

    def _show_error(message):
        home_page._append_comm_line(message, tag="error", direction="TX", show_channel=False)

    commands_box = {}

    def _flush_before_log_close():
        """When the script ends while logging, wait for the last sent data and the
        replies so they are in the log before it is closed."""
        commands = commands_box.get("commands")
        if commands is None or run.is_stopped() or not home_page.is_comm_logging():
            return
        try:
            commands._flush_display(settle=LOG_SETTLE_TIME)
        except BaseException:
            pass  # window closing or stopped; close the log anyway

    def _execute():
        try:
            commands = CustomScriptCommands(home_page, run)
            commands_box["commands"] = commands
            exec_globals = {
                name: _checked(name, getattr(commands, name)) for name in COMMAND_EXAMPLES
            }
            exec_globals["__builtins__"] = dict(SAFE_BUILTINS)
            tree = ast.parse(script_text, SCRIPT_FILENAME)
            commands.show_counter_rows = _standalone_call_rows(tree, "GetReceiveCounter")
            problem = _check_script_lines(tree)
            if problem is not None:
                row, details = problem
                message = "Script stopped at row {}: {}".format(row, details)
                home_page.after(0, lambda: _show_error(message))
                return
            exec(compile(tree, SCRIPT_FILENAME, "exec"), exec_globals)
        except SystemExit:
            pass  # stopped by the user
        except Exception as exc:
            if not run.is_stopped():
                message = _format_script_error(exc)
                try:
                    home_page.after(0, lambda: _show_error(message))
                except Exception:
                    pass
        finally:
            _flush_before_log_close()

            def _ui_finish():
                # A log started by this script is closed when the script ends.
                log_path = home_page.stop_comm_log(owner=run)
                if log_path:
                    home_page._append_comm_line(
                        "Logging stopped because the script ended. The log is saved "
                        "in {}".format(log_path),
                        tag="meta", show_channel=False)

                # A newer run owns the buttons; leave them alone.
                if home_page._active_script is not run:
                    return
                home_page._active_script = None
                home_page._btn_script_play.set_state(True)
                home_page._btn_script_pause.set_state(False)
                home_page._btn_script_stop.set_state(False)

            try:
                home_page.after(0, _ui_finish)
            except Exception:
                pass

    threading.Thread(target=_execute, daemon=True, name="script-engine").start()
