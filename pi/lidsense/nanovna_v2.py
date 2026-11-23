"""NanoVNA V2 (S-A-A-2 / V2Plus) USB driver.

Refactored from the original ghg.py ``VNADevice_NanoRFE`` class. It uses the same
binary register protocol, with these fixes:
  * every serial read has a deadline (the old loop could hang forever)
  * the averaging count is always applied (old ``setSweep`` could skip it)
  * the port can be reopened after a USB reset
  * it works as a context manager, so the port is always closed
"""
from __future__ import annotations

import time
from struct import pack, unpack_from

import numpy as np
import serial

_CMD_READ = 0x10
_CMD_READFIFO = 0x18
_CMD_WRITE = 0x20
_CMD_WRITE2 = 0x21
_CMD_WRITE8 = 0x23

_ADDR_SWEEP_START = 0x00
_ADDR_SWEEP_STEP = 0x10
_ADDR_SWEEP_POINTS = 0x20
_ADDR_SWEEP_VALS_PER_FREQ = 0x22
_ADDR_VALUES_FIFO = 0x30
_ADDR_FW_MAJOR = 0xF3
_ADDR_FW_MINOR = 0xF4

WRITE_SLEEP = 0.05
POINT_BYTES = 32


class NanoVNAError(IOError):
    pass


class NanoVNAV2:
    def __init__(self, port: str = "/dev/ttyACM0", timeout_s: float = 5.0):
        self.port_name = port
        self.timeout_s = timeout_s
        self.ser: serial.Serial | None = None
        self.start_hz = 0.0
        self.stop_hz = 0.0
        self.points = 0
        self.avg = 1
        self.firmware = (0, 0)

    # ---------------------------------------------------------------- lifecycle
    def open(self) -> "NanoVNAV2":
        self.close()
        self.ser = serial.Serial(self.port_name, timeout=0.2)
        self._reset_protocol()
        major, minor = self._read_version()
        if major == 0xFF:
            raise NanoVNAError("NanoVNA is in DFU (firmware update) mode")
        self.firmware = (major, minor)
        return self

    def close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # ---------------------------------------------------------------- protocol
    def _reset_protocol(self) -> None:
        self.ser.write(pack("<Q", 0))
        time.sleep(WRITE_SLEEP)

    def _read_exact(self, n: int, deadline_s: float) -> bytes:
        buf = b""
        end = time.monotonic() + deadline_s
        while len(buf) < n:
            if time.monotonic() > end:
                raise NanoVNAError(f"timeout: got {len(buf)} of {n} bytes")
            buf += self.ser.read(n - len(buf))
        return buf

    def _read_version(self) -> tuple[int, int]:
        self.ser.reset_input_buffer()
        self.ser.write(pack("<BBBB", _CMD_READ, _ADDR_FW_MAJOR, _CMD_READ, _ADDR_FW_MINOR))
        resp = self._read_exact(2, 2.0)
        return resp[0], resp[1]

    def set_sweep(self, start_hz: float, stop_hz: float, points: int, avg: int = 1) -> None:
        if points < 2 or points > 1024:
            raise ValueError("points must be 2..1024")
        step = (stop_hz - start_hz) / (points - 1)
        cmd = pack("<BBQ", _CMD_WRITE8, _ADDR_SWEEP_START, int(start_hz))
        cmd += pack("<BBQ", _CMD_WRITE8, _ADDR_SWEEP_STEP, int(step))
        cmd += pack("<BBH", _CMD_WRITE2, _ADDR_SWEEP_POINTS, points)
        cmd += pack("<BBH", _CMD_WRITE2, _ADDR_SWEEP_VALS_PER_FREQ, avg)
        self.ser.write(cmd)
        time.sleep(WRITE_SLEEP)
        self.start_hz, self.stop_hz, self.points, self.avg = start_hz, stop_hz, points, avg

    def frequencies(self) -> np.ndarray:
        return np.linspace(self.start_hz, self.stop_hz, self.points)

    def read_s11_raw(self) -> np.ndarray:
        """Return the raw (uncalibrated) complex S11 = reflected/forward per point."""
        if self.ser is None:
            raise NanoVNAError("device not open")
        fwd = np.zeros(self.points, complex)
        refl = np.zeros(self.points, complex)
        count = np.zeros(self.points, int)

        self._reset_protocol()
        self.ser.write(pack("<BBB", _CMD_WRITE, _ADDR_VALUES_FIFO, 0))  # clear FIFO
        time.sleep(WRITE_SLEEP)
        self.ser.reset_input_buffer()

        left = self.points * self.avg
        while left > 0:
            n = min(255, left)
            self.ser.write(pack("<BBB", _CMD_READFIFO, _ADDR_VALUES_FIFO, n))
            data = self._read_exact(n * POINT_BYTES, self.timeout_s * self.avg)
            for i in range(n):
                fr, fi, r0r, r0i, _r1r, _r1i, idx = unpack_from(
                    "<iiiiiihxxxxxx", data, i * POINT_BYTES)
                if 0 <= idx < self.points:
                    fwd[idx] += complex(fr, fi)
                    refl[idx] += complex(r0r, r0i)
                    count[idx] += 1
            left -= n

        if np.any(count != self.avg):
            bad = int(np.argmax(count != self.avg))
            raise NanoVNAError(f"incomplete sweep at point {bad}: {count[bad]}/{self.avg} values")
        return refl / fwd
