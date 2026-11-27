"""Serial port communication with background receive and transmit threads.

Two communication modes, as in Docklight:

* Send/Receive - one COM port. Docklight sends and receives on it.
* Monitoring   - two COM ports, receive only. Each port listens to one
  device of a link between two other devices (e.g. via a monitoring cable),
  so the conversation between them can be shown in one window.
  Data from the first port is channel 1, from the second port channel 2.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import serial
from serial.tools import list_ports

PARITY_MAP = {
    "None": serial.PARITY_NONE,
    "Even": serial.PARITY_EVEN,
    "Odd": serial.PARITY_ODD,
    "Mark": serial.PARITY_MARK,
    "Space": serial.PARITY_SPACE,
}

STOP_BITS_MAP = {
    "1": serial.STOPBITS_ONE,
    "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}

BYTESIZE_MAP = {
    "5": serial.FIVEBITS,
    "6": serial.SIXBITS,
    "7": serial.SEVENBITS,
    "8": serial.EIGHTBITS,
}

COMM_MODE_SEND_RECEIVE = "send_receive"
COMM_MODE_MONITORING = "monitoring"
COMM_MODES = (COMM_MODE_SEND_RECEIVE, COMM_MODE_MONITORING)


@dataclass
class TxEvent:
    data: bytes
    label: str = ""


@dataclass
class RxEvent:
    data: bytes
    # Send/Receive: always 1. Monitoring: 1 or 2 (which port received it).
    channel: int = 1


@dataclass
class ErrorEvent:
    message: str
    fatal: bool = True


CommEvent = TxEvent | RxEvent | ErrorEvent
CommCallback = Callable[[CommEvent], None]

IDLE_FLUSH_SECONDS = 0.12
MODEM_POLL_SECONDS = 0.1  # How often the reader thread refreshes modem-line state
MAX_PENDING_SENDS = 256  # Sends wait in this queue while the device holds off (CTS / XOFF)

# Flow control modes, matching Docklight's "Flow Control Support" options:
#   off      - no flow control; RTS and DTR are switched on when the port opens
#   manual   - RTS/DTR set by the user; CTS/DSR/DCD/RI only displayed
#   hardware - RTS/CTS handshaking done by the Windows serial driver
#   software - XON/XOFF handshaking done by the Windows serial driver
#   rs485    - driver raises RTS while sending (RTS_CONTROL_TOGGLE)
# Flow control applies to Send/Receive mode. Monitoring ports only listen.
FLOW_CONTROL_MODES = ("off", "manual", "hardware", "software", "rs485")

RS485_UNSUPPORTED_MESSAGE = (
    "{} does not support 'RS485 Transceiver Control' (RTS toggle).\n\n"
    "Many USB-to-Serial devices and Virtual COM drivers do not support this "
    "setting. Use an on-board COM port or a PCI COM card, or an RS485 converter "
    "with automatic send/receive switching and set Flow Control to 'Off'."
)


def friendly_port_error(port_name: str, exc: BaseException) -> str:
    """Explain why a COM port could not be opened, in words a user understands."""
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, FileNotFoundError) or "filenotfounderror" in lowered or "cannot find" in lowered:
        return (
            "{} was not found. Check that the device is plugged in and that the "
            "right COM port is selected in Project Settings."
        ).format(port_name)
    if isinstance(exc, PermissionError) or "permissionerror" in lowered or "access is denied" in lowered:
        return (
            "{} is already being used by another program. Close the other program "
            "and try again."
        ).format(port_name)
    if "semaphore" in lowered or "not functioning" in lowered or "does not recognize" in lowered:
        return (
            "{} is not responding. Unplug the device, plug it in again and try once more."
        ).format(port_name)
    if isinstance(exc, ValueError):
        return (
            "{} could not be opened with the current settings (baud rate, data bits, "
            "parity or stop bits). Check them in Project Settings."
        ).format(port_name)
    return (
        "{} could not be opened. Check that the device is connected and that the "
        "COM port settings are correct."
    ).format(port_name)


def _open_port(port: serial.Serial) -> None:
    """Open a port; on failure raise a SerialException with a user-friendly message."""
    try:
        port.open()
    except (ValueError, OSError, serial.SerialException) as exc:
        raise serial.SerialException(friendly_port_error(port.port, exc)) from exc


def _com_port_sort_key(port_name: str):
    match = re.match(r"^COM(\d+)$", port_name, re.IGNORECASE)
    if match:
        return (0, int(match.group(1)), port_name.lower())
    return (1, port_name.lower())


def list_available_ports(include: str | None = None) -> list[str]:
    """Return currently available serial port names."""
    ports = [port.device for port in list_ports.comports()]
    if include:
        include = include.strip()
        if include and include not in ports:
            ports.append(include)
    return sorted(set(ports), key=_com_port_sort_key)


class _Channel:
    """One open serial port plus its receive framing state."""

    def __init__(self, number: int, port: serial.Serial):
        self.number = number
        self.port = port
        self.reader: Optional[threading.Thread] = None
        self.rx_buffer = bytearray()
        self.framing_lock = threading.Lock()
        self.last_rx_at = 0.0


class CommService:
    """Owns the serial port(s), reader/writer threads, and TX/RX event dispatch."""

    def __init__(self, on_event: CommCallback):
        self._on_event = on_event
        self._channels: list[_Channel] = []
        self._running = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self._closer: Optional[threading.Thread] = None
        self._tx_queue: queue.Queue[tuple[bytes, str]] = queue.Queue()
        self._write_lock = threading.Lock()
        self._comm_mode = COMM_MODE_SEND_RECEIVE
        self._flow_control = "off"
        self._manual_rts = False
        self._manual_dtr = False

        # Modem input lines of the Send/Receive port, refreshed by its reader
        # thread so the UI thread never has to touch the driver for status reads.
        self._modem_inputs = {"cts": False, "dsr": False, "dcd": False, "ri": False}
        self._last_modem_poll = 0.0

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def _port(self) -> Optional[serial.Serial]:
        """The Send/Receive port (channel 1)."""
        channels = self._channels
        return channels[0].port if channels else None

    def is_connected(self) -> bool:
        port = self._port
        return port is not None and port.is_open

    def is_monitoring(self) -> bool:
        return self._comm_mode == COMM_MODE_MONITORING

    def can_send(self) -> bool:
        """True when the port is open in Send/Receive mode."""
        return self.is_connected() and not self.is_monitoring()

    def get_flow_control(self) -> str:
        return self._flow_control

    def get_comm_mode(self) -> str:
        return self._comm_mode

    def configure_session(self, settings: dict) -> None:
        """Apply mode and flow control for UI/manual control without opening ports."""
        mode = settings.get("comm_mode", COMM_MODE_SEND_RECEIVE)
        if mode not in COMM_MODES:
            mode = COMM_MODE_SEND_RECEIVE
        self._comm_mode = mode

        flow = settings.get("flow_control", "off")
        if flow not in FLOW_CONTROL_MODES:
            flow = "off"
        if flow == "manual" and self._flow_control != "manual":
            self._manual_rts = False
            self._manual_dtr = False
        self._flow_control = flow

    # ------------------------------------------------------------------
    # Manual RTS/DTR (Send/Receive mode)
    # ------------------------------------------------------------------

    def get_handshake_state(self) -> dict:
        """Return RTS/DTR/CTS/DSR/DCD/RI line states for the UI.

        Safe to call from the UI thread: input lines come from a cache that the
        reader thread keeps fresh, so no driver call can block here.
        """
        if self.is_connected():
            port = self._port
            try:
                rts = bool(port.rts)
                dtr = bool(port.dtr)
            except Exception:
                rts, dtr = self._manual_rts, self._manual_dtr
            state = {"rts": rts, "dtr": dtr}
            state.update(self._modem_inputs)
            return state

        return {
            "rts": self._manual_rts,
            "dtr": self._manual_dtr,
            "cts": False,
            "dsr": False,
            "dcd": False,
            "ri": False,
        }

    def set_manual_handshake(
        self, rts: Optional[bool] = None, dtr: Optional[bool] = None
    ) -> None:
        """Set RTS/DTR directly via OS driver pin overrides in Manual mode."""
        if self._flow_control != "manual" or self.is_monitoring():
            return

        if rts is not None:
            self._manual_rts = bool(rts)
            if self.is_connected():
                self._port.rts = self._manual_rts
        if dtr is not None:
            self._manual_dtr = bool(dtr)
            if self.is_connected():
                self._port.dtr = self._manual_dtr

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def _clear_tx_queue(self) -> None:
        """Thread-safe purge of pending transmit queue items."""
        with self._tx_queue.mutex:
            dropped = len(self._tx_queue.queue)
            self._tx_queue.queue.clear()
            # Keep the unfinished-task count in step so pending_sends() is right.
            self._tx_queue.unfinished_tasks = max(
                0, self._tx_queue.unfinished_tasks - dropped
            )
            if self._tx_queue.unfinished_tasks == 0:
                self._tx_queue.all_tasks_done.notify_all()

    def pending_sends(self) -> int:
        """Number of queued sends that have not been written (and shown) yet."""
        return self._tx_queue.unfinished_tasks

    @staticmethod
    def _new_port(port_name: str, settings: dict) -> serial.Serial:
        """Create an unopened port with the shared COM settings applied."""
        port = serial.Serial()
        port.port = port_name
        port.baudrate = int(settings.get("baud_rate", "9600"))
        port.bytesize = BYTESIZE_MAP.get(settings.get("data_bits", "8"), serial.EIGHTBITS)
        port.parity = PARITY_MAP.get(settings.get("parity", "None"), serial.PARITY_NONE)
        port.stopbits = STOP_BITS_MAP.get(
            settings.get("stop_bits", "1"), serial.STOPBITS_ONE
        )
        port.timeout = 0.1
        # Like Docklight, a send waits for as long as the device holds off
        # (CTS low / XOFF). Stop Communication cancels a waiting write.
        port.write_timeout = None
        return port

    def _open_send_receive_port(self, settings: dict) -> serial.Serial:
        port_name = settings.get("channel", "COM1").strip()
        flow = self._flow_control

        # Configure everything on the unopened port so the driver applies the
        # flow control mode and RTS/DTR levels in one step when it opens.
        # (Setting RTS/DTR after open() would pulse both lines high first.)
        port = self._new_port(port_name, settings)
        port.rtscts = flow == "hardware"
        port.xonxoff = flow == "software"
        port.dsrdtr = False

        if flow == "manual":
            port.rts = self._manual_rts
            port.dtr = self._manual_dtr
        elif flow == "rs485":
            from serial.rs485 import RS485Settings

            port.rs485_mode = RS485Settings(
                rts_level_for_tx=True,
                rts_level_for_rx=False,
                loopback=False,
            )
        else:
            # Off / hardware / software: RTS and DTR on when the port opens
            port.rts = True
            port.dtr = True

        try:
            port.open()
        except (ValueError, serial.SerialException) as exc:
            # "could not open port" = port missing/busy; anything else while
            # applying RS485 settings means the driver rejected RTS toggle.
            if flow == "rs485" and "could not open port" not in str(exc).lower():
                raise serial.SerialException(
                    RS485_UNSUPPORTED_MESSAGE.format(port_name)
                ) from exc
            raise serial.SerialException(friendly_port_error(port_name, exc)) from exc
        return port

    def _open_monitoring_ports(self, settings: dict) -> list[serial.Serial]:
        names = [
            settings.get("channel", "COM1").strip(),
            settings.get("channel2", "COM2").strip(),
        ]
        if not names[1]:
            raise serial.SerialException(
                "Monitoring mode needs a second COM port (channel 2)."
            )
        if names[0].lower() == names[1].lower():
            raise serial.SerialException(
                "Monitoring mode needs two different COM ports "
                "(channel 1 and channel 2 are both {}).".format(names[0])
            )

        opened: list[serial.Serial] = []
        try:
            for name in names:
                # Listen only: no handshaking, so the monitor never holds off
                # either device.
                port = self._new_port(name, settings)
                port.rtscts = False
                port.xonxoff = False
                port.dsrdtr = False
                _open_port(port)
                opened.append(port)
        except Exception:
            for port in opened:
                try:
                    port.close()
                except Exception:
                    pass
            raise
        return opened

    def connect(self, settings: dict) -> None:
        if self.is_connected():
            return

        # If a previous disconnect() is still closing the OS handles in the
        # background, wait briefly so reopening doesn't fail with "access denied".
        closer = self._closer
        if closer is not None and closer.is_alive():
            closer.join(timeout=2.0)

        self.configure_session(settings)

        # Drain leftover state and queue items from previous sessions
        self._clear_tx_queue()
        self._modem_inputs = {"cts": False, "dsr": False, "dcd": False, "ri": False}
        self._last_modem_poll = 0.0

        if self.is_monitoring():
            ports = self._open_monitoring_ports(settings)
        else:
            ports = [self._open_send_receive_port(settings)]

        self._channels = [
            _Channel(number, port) for number, port in enumerate(ports, start=1)
        ]
        self._running.set()

        if not self.is_monitoring():
            self._writer_thread = threading.Thread(
                target=self._write_loop,
                name="serial-writer",
                daemon=True,
            )
            self._writer_thread.start()

        for channel in self._channels:
            channel.reader = threading.Thread(
                target=self._read_loop,
                args=(channel,),
                name="serial-reader-{}".format(channel.number),
                daemon=True,
            )
            channel.reader.start()

    def disconnect(self) -> None:
        """Stop I/O and release the port(s) without ever blocking the caller.

        The actual close() can block for a long time on Windows when RTS/CTS is
        active and bytes are stuck in the driver, so it runs on a helper thread.
        """
        self._running.clear()
        self._clear_tx_queue()

        channels, self._channels = self._channels, []
        for channel in channels:
            self._flush_pending_rx(channel)

        writer, self._writer_thread = self._writer_thread, None

        self._closer = threading.Thread(
            target=self._close_ports,
            args=(channels, writer),
            name="serial-closer",
            daemon=True,
        )
        self._closer.start()

    @staticmethod
    def _close_ports(channels, writer) -> None:
        for channel in channels:
            port = channel.port
            steps = (
                port.cancel_write,  # abort any write stuck on CTS
                port.reset_output_buffer,  # drop bytes the driver is holding
                lambda: setattr(port, "rtscts", False),  # stop waiting on CTS
                port.close,
            )
            for step in steps:
                try:
                    step()
                except Exception:
                    pass

        threads = [writer] + [channel.reader for channel in channels]
        for thread in threads:
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)

    # ------------------------------------------------------------------
    # Transmit (Send/Receive mode only)
    # ------------------------------------------------------------------

    def send_bytes(self, data: bytes, label: str = "") -> bool:
        """Queue data for sending. Returns False only if the send queue is full."""
        if not self.is_connected():
            raise RuntimeError("Serial port is not open.")
        if self.is_monitoring():
            raise RuntimeError("Sending is not available in Monitoring mode.")

        if self._tx_queue.qsize() >= MAX_PENDING_SENDS:
            return False

        self._tx_queue.put((data, label))
        return True

    def _write_loop(self) -> None:
        """Background worker loop handling blocking OS write operations."""
        while self._running.is_set():
            try:
                data, label = self._tx_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            port = self._port
            if port is None or not port.is_open:
                self._tx_queue.task_done()
                break

            event_to_emit = None

            with self._write_lock:
                try:
                    # Blocks until the driver has sent the data. With RTS/CTS or
                    # XON/XOFF the driver pauses while the device holds off; with
                    # RS485 the driver raises RTS for the duration of the send.
                    port.write(data)
                    event_to_emit = TxEvent(data=data, label=label)
                except (serial.SerialException, OSError) as exc:
                    event_to_emit = ErrorEvent(
                        message="Could not send data to {}. Check that the device is "
                        "still connected.".format(port.port)
                    )

            # Dispatch event OUTSIDE the lock; skip if we are shutting down so a
            # closing port doesn't generate a spurious error.
            if event_to_emit is not None and self._running.is_set():
                self._on_event(event_to_emit)

            self._tx_queue.task_done()

    # ------------------------------------------------------------------
    # Receive (one reader thread per channel)
    # ------------------------------------------------------------------

    def _flush_pending_rx(self, channel: _Channel) -> None:
        """Emit buffered RX after a pause between incoming bytes."""
        with channel.framing_lock:
            if not channel.rx_buffer:
                return
            data = bytes(channel.rx_buffer)
            channel.rx_buffer.clear()

        # Dispatch outside the lock to avoid lock-ordering deadlocks with the UI
        if data:
            self._on_event(RxEvent(data=data, channel=channel.number))

    def _maybe_flush_idle(self, channel: _Channel) -> None:
        if time.monotonic() - channel.last_rx_at < IDLE_FLUSH_SECONDS:
            return
        self._flush_pending_rx(channel)
        channel.last_rx_at = time.monotonic()

    @staticmethod
    def _process_rx(channel: _Channel, chunk: bytes) -> None:
        """Frame RX by idle gap so embedded CR/LF bytes stay in one message."""
        if not chunk:
            return
        with channel.framing_lock:
            channel.rx_buffer.extend(chunk)

    def _poll_modem_lines(self, port) -> None:
        """Refresh cached CTS/DSR/DCD/RI. Runs on the channel 1 reader thread only."""
        now = time.monotonic()
        if now - self._last_modem_poll < MODEM_POLL_SECONDS:
            return
        self._last_modem_poll = now
        try:
            self._modem_inputs = {
                "cts": bool(port.cts),
                "dsr": bool(port.dsr),
                "dcd": bool(port.cd),
                "ri": bool(port.ri),
            }
        except Exception:
            pass

    def _read_loop(self, channel: _Channel) -> None:
        port = channel.port
        poll_modem = channel.number == 1 and not self.is_monitoring()

        while self._running.is_set():
            if not port.is_open:
                break

            try:
                waiting = port.in_waiting
                size = waiting if waiting > 0 else 1
                chunk = port.read(size)
            except (serial.SerialException, OSError) as exc:
                # Port was closed deliberately: exit quietly
                if not self._running.is_set():
                    break

                message = (
                    "The connection to {} was lost. Check that the device is still "
                    "plugged in, then start communication again."
                ).format(port.port)
                self._on_event(ErrorEvent(message=message))
                break

            if poll_modem:
                self._poll_modem_lines(port)

            if chunk:
                channel.last_rx_at = time.monotonic()
                self._process_rx(channel, chunk)
            else:
                self._maybe_flush_idle(channel)
