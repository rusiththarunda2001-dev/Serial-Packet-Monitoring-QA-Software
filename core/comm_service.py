"""Serial port communication with background receive thread."""

from __future__ import annotations

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


@dataclass
class TxEvent:
    data: bytes
    label: str = ""


@dataclass
class RxEvent:
    data: bytes


@dataclass
class ErrorEvent:
    message: str


CommEvent = TxEvent | RxEvent | ErrorEvent
CommCallback = Callable[[CommEvent], None]

IDLE_FLUSH_SECONDS = 0.12
CTS_WAIT_TIMEOUT = 0.5
CTS_POLL_INTERVAL = 0.01
XON_BYTE = 0x11
XOFF_BYTE = 0x13


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


class CommService:
    """Owns the serial port, reader thread, and TX/RX event dispatch."""

    def __init__(self, on_event: CommCallback):
        self._on_event = on_event
        self._port: Optional[serial.Serial] = None
        self._running = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()
        self._framing_lock = threading.Lock()
        self._rx_buffer = bytearray()
        self._last_rx_at = 0.0
        self._flow_control = "off"
        self._manual_rts = False
        self._manual_dtr = False
        self._software_tx_allowed = True
        self._software_flow_lock = threading.Lock()

    def is_connected(self) -> bool:
        return self._port is not None and self._port.is_open

    def get_flow_control(self) -> str:
        return self._flow_control

    def configure_session(self, settings: dict) -> None:
        """Apply flow-control mode for UI/manual control without opening the port."""
        flow = settings.get("flow_control", "off")
        if flow == "manual" and self._flow_control != "manual":
            self._manual_rts = False
            self._manual_dtr = False
        self._flow_control = flow

    def get_handshake_state(self) -> dict:
        """Return RTS/DTR/CTS/DSR/DCD/RI line states for the UI."""
        if self.is_connected():
            port = self._port
            return {
                "rts": bool(port.rts),
                "dtr": bool(port.dtr),
                "cts": bool(getattr(port, "cts", False)),
                "dsr": bool(getattr(port, "dsr", False)),
                "dcd": bool(getattr(port, "cd", False)),
                "ri": bool(getattr(port, "ri", False)),
            }

        return {
            "rts": self._manual_rts,
            "dtr": self._manual_dtr,
            "cts": False,
            "dsr": False,
            "dcd": False,
            "ri": False,
        }

    def set_manual_handshake(self, rts: Optional[bool] = None, dtr: Optional[bool] = None) -> None:
        """Set RTS/DTR in Manual flow-control mode (works with port open or closed)."""
        if self._flow_control != "manual":
            return

        if rts is not None:
            self._manual_rts = bool(rts)
            if self.is_connected():
                self._port.rts = self._manual_rts
        if dtr is not None:
            self._manual_dtr = bool(dtr)
            if self.is_connected():
                self._port.dtr = self._manual_dtr

    def connect(self, settings: dict) -> None:
        if self.is_connected():
            return

        port_name = settings.get("channel", "COM1").strip()
        baud_rate = int(settings.get("baud_rate", "9600"))
        data_bits = settings.get("data_bits", "8")
        parity = settings.get("parity", "None")
        stop_bits = settings.get("stop_bits", "1")
        self._flow_control = settings.get("flow_control", "off")

        rtscts = False
        xonxoff = False

        self._port = serial.Serial(
            port=port_name,
            baudrate=baud_rate,
            bytesize=BYTESIZE_MAP.get(data_bits, serial.EIGHTBITS),
            parity=PARITY_MAP.get(parity, serial.PARITY_NONE),
            stopbits=STOP_BITS_MAP.get(stop_bits, serial.STOPBITS_ONE),
            timeout=0.1,
            rtscts=rtscts,
            xonxoff=xonxoff,
        )
        
        self._port.setDTR(False)
        self._port.setRTS(True)
        time.sleep(0.1)
        self._port.setDTR(True)
        self._port.setRTS(False)
        time.sleep(0.1)
        self._port.setDTR(False)
        self._port.setRTS(False)
        
        self._apply_flow_control_outputs()

        if self._flow_control == "software":
            with self._software_flow_lock:
                self._software_tx_allowed = True

        self._reset_framing()
        self._running.set()
        self._reader_thread = threading.Thread(
            target=self._read_loop,
            name="serial-reader",
            daemon=True,
        )
        self._reader_thread.start()

    def _apply_flow_control_outputs(self) -> None:
        if not self.is_connected():
            return

        if self._flow_control == "off":
            self._port.rts = True
            self._port.dtr = True
        elif self._flow_control == "manual":
            self._port.rts = self._manual_rts
            self._port.dtr = self._manual_dtr
        elif self._flow_control == "hardware":
            self._port.rts = False
        elif self._flow_control == "rs485":
            self._configure_rs485_mode()

    def _configure_rs485_mode(self) -> None:
        try:
            from serial.rs485 import RS485Settings

            self._port.rs485_mode = RS485Settings(
                rts_level_for_tx=True,
                rts_level_for_rx=False,
                loopback=False,
            )
        except (AttributeError, ImportError, ValueError, serial.SerialException):
            self._port.rts = False

    def disconnect(self) -> None:
        self._running.clear()
        self._flush_pending_rx()
        self._reset_framing()

        port = self._port
        self._port = None

        if port is not None:
            try:
                if port.is_open:
                    port.close()
            except serial.SerialException:
                pass

        reader = self._reader_thread
        self._reader_thread = None
        if reader is not None and reader.is_alive():
            reader.join(timeout=1.0)

    def _is_cts_ready(self) -> bool:
        return bool(getattr(self._port, "cts", False))

    def _wait_for_cts(self, timeout: float = CTS_WAIT_TIMEOUT) -> bool:
        """Wait until CTS is high. Returns False if CTS did not become ready in time."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._is_cts_ready():
                return True
            time.sleep(CTS_POLL_INTERVAL)
        return False

    def _write_hardware_rtscts(self, data: bytes) -> bool:
        """Send with RTS/CTS. Returns False if CTS is not ready (no data sent)."""
        if not data:
            return True

        self._port.rts = True
        try:
            for byte in data:
                if not self._wait_for_cts():
                    return False
                self._port.write(bytes([byte]))
            self._port.flush()
            return True
        finally:
            self._port.rts = False

    def _software_tx_enabled(self) -> bool:
        with self._software_flow_lock:
            return self._software_tx_allowed

    def _filter_software_flow_control(self, chunk: bytes) -> bytes:
        """Strip XON/XOFF from RX and update whether TX is allowed."""
        if self._flow_control != "software":
            return chunk

        payload = bytearray()
        with self._software_flow_lock:
            for byte in chunk:
                if byte == XOFF_BYTE:
                    self._software_tx_allowed = False
                elif byte == XON_BYTE:
                    self._software_tx_allowed = True
                else:
                    payload.append(byte)
        return bytes(payload)

    def send_bytes(self, data: bytes, label: str = "") -> bool:
        """Send data. Returns False if flow control blocked the send."""
        if not self.is_connected():
            raise RuntimeError("Serial port is not open.")

        with self._write_lock:
            if self._flow_control == "software":
                if not self._software_tx_enabled():
                    return False
            elif self._flow_control == "hardware":
                if not self._write_hardware_rtscts(data):
                    return False
                self._on_event(TxEvent(data=data, label=label))
                return True

            rs485_manual = (
                self._flow_control == "rs485"
                and not getattr(self._port, "rs485_mode", None)
            )
            if rs485_manual:
                self._port.rts = True
            try:
                self._port.write(data)
                self._port.flush()
            finally:
                if rs485_manual:
                    self._port.rts = False

        self._on_event(TxEvent(data=data, label=label))
        return True

    def _reset_framing(self) -> None:
        with self._framing_lock:
            self._rx_buffer.clear()

    def _flush_pending_rx(self) -> None:
        """Emit buffered RX after a pause between incoming bytes."""
        with self._framing_lock:
            if not self._rx_buffer:
                return

            data = bytes(self._rx_buffer)
            self._rx_buffer.clear()
            if data:
                self._on_event(RxEvent(data=data))

    def _maybe_flush_idle(self) -> None:
        if time.monotonic() - self._last_rx_at < IDLE_FLUSH_SECONDS:
            return
        self._flush_pending_rx()
        self._last_rx_at = time.monotonic()

    def _process_rx(self, chunk: bytes) -> None:
        """Frame RX by idle gap so embedded CR/LF bytes stay in one message."""
        chunk = self._filter_software_flow_control(chunk)
        if not chunk:
            return
        with self._framing_lock:
            self._rx_buffer.extend(chunk)

    def _read_loop(self) -> None:
        while self._running.is_set():
            port = self._port
            if port is None or not port.is_open:
                break

            try:
                waiting = port.in_waiting
                size = waiting if waiting > 0 else 1
                chunk = port.read(size)
            except serial.SerialException as exc:
                self._on_event(ErrorEvent(message=str(exc)))
                break

            if chunk:
                self._last_rx_at = time.monotonic()
                self._process_rx(chunk)
            else:
                self._maybe_flush_idle()
