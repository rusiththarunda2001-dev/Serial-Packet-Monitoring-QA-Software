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

    def is_connected(self) -> bool:
        return self._port is not None and self._port.is_open

    def connect(self, settings: dict) -> None:
        if self.is_connected():
            return

        port_name = settings.get("channel", "COM1").strip()
        baud_rate = int(settings.get("baud_rate", "9600"))
        data_bits = settings.get("data_bits", "8")
        parity = settings.get("parity", "None")
        stop_bits = settings.get("stop_bits", "1")

        self._port = serial.Serial(
            port=port_name,
            baudrate=baud_rate,
            bytesize=BYTESIZE_MAP.get(data_bits, serial.EIGHTBITS),
            parity=PARITY_MAP.get(parity, serial.PARITY_NONE),
            stopbits=STOP_BITS_MAP.get(stop_bits, serial.STOPBITS_ONE),
            timeout=0.1,
        )

        self._reset_framing()
        self._running.set()
        self._reader_thread = threading.Thread(
            target=self._read_loop,
            name="serial-reader",
            daemon=True,
        )
        self._reader_thread.start()

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

    def send_bytes(self, data: bytes, label: str = "") -> None:
        if not self.is_connected():
            raise RuntimeError("Serial port is not open.")

        with self._write_lock:
            self._port.write(data)
            self._port.flush()

        self._on_event(TxEvent(data=data, label=label))

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
