"""USB control for ATOM Matrix. Requires pyserial. Import has no side effects.

    from matrix_control import set_state, MatrixController
    set_state('running', port='COM3')
    with MatrixController('COM3') as matrix:
        matrix.set_state('attention')
        print(matrix.get_state())
"""
import json
import math
import threading
import time
import uuid

import serial
from serial.tools import list_ports

STATES = ('done', 'running', 'attention', 'idle')


def detect_port(timeout=3.0, *, _deadline=None):
    """Find one FTDI ATOM Matrix by a read-only firmware identity handshake.

    Raises RuntimeError for zero or multiple responding devices. Never chooses
    an arbitrary device when multiple Matrices are connected. Specify a port
    explicitly for unlisted USB bridges or to choose among multiple devices.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be a finite positive number')
    candidates = [p.device for p in list_ports.comports()
                  if (p.vid, p.pid) == (0x0403, 0x6001)]
    found = []
    for port in candidates:
        if _deadline is not None and time.monotonic() >= _deadline:
            raise TimeoutError('Discovery deadline exceeded before all candidates were checked')
        try:
            with MatrixController(port, min(timeout, 1.0)) as matrix:
                deadline = time.monotonic() + timeout
                if _deadline is not None:
                    deadline = min(deadline, _deadline)
                while time.monotonic() < deadline:
                    matrix.timeout = min(1.0, max(0.01, deadline - time.monotonic()))
                    try:
                        matrix._request('identify')
                    except TimeoutError:
                        # USB may appear before boot is ready to receive bytes.
                        continue
                    found.append(port)
                    break
        except (serial.SerialException, TimeoutError, RuntimeError):
            continue
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise RuntimeError('Multiple Matrices found: ' + ', '.join(found)
                           + '; specify port explicitly')
    raise RuntimeError('No Matrix responded; check USB, firmware and port ownership'
                       + '; candidates: ' + ', '.join(candidates))


class MatrixController:
    """Persistent connection; methods wait for the device's matching ACK.

    Use one owner per serial port. Calls on this object are thread-safe.
    Raises ValueError for invalid input, TimeoutError for a missing ACK,
    RuntimeError for a rejected command, or serial.SerialException for USB errors.
    """

    def __init__(self, port=None, timeout=5.0, reconnect_timeout=5.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be a finite positive number')
        self.timeout = timeout
        if not math.isfinite(reconnect_timeout) or reconnect_timeout <= 0:
            raise ValueError('reconnect_timeout must be a finite positive number')
        self.reconnect_timeout = reconnect_timeout
        self._requested_port = port
        self._closed = False
        self.port = port if port is not None else detect_port(min(timeout, 3.0))
        self._lock = threading.RLock()
        self._serial = None
        self._open_port(self.port)

    def _open_port(self, port):
        self._serial = serial.Serial(port=None, baudrate=115200,
                                     timeout=min(0.1, self.timeout), write_timeout=self.timeout)
        # Do not intentionally toggle the ESP32 reset/download control lines.
        self._serial.dtr = False
        self._serial.rts = False
        self._serial.port = port
        try:
            self._serial.open()
        except Exception:
            self._disconnect()
            raise
        self.port = port

    def _disconnect(self):
        if self._serial is not None:
            try:
                self._serial.close()
            except (serial.SerialException, OSError):
                pass
        self.port = None

    def _request(self, op, state=None, *, timeout=None):
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise serial.SerialException('Matrix is disconnected')
            budget = self.timeout if timeout is None else timeout
            self._serial.timeout = min(0.1, budget)
            self._serial.write_timeout = budget
            request_id = uuid.uuid4().hex
            request = {'id': request_id, 'op': op}
            if state is not None:
                request['state'] = state
            self._serial.reset_input_buffer()
            # Leading newline recovers from a previous interrupted transmission.
            payload = ('\n' + json.dumps(request) + '\n').encode('ascii')
            if self._serial.write(payload) != len(payload):
                raise serial.SerialException('Incomplete command write')
            deadline = time.monotonic() + budget
            buffer = bytearray()
            while time.monotonic() < deadline:
                chunk = self._serial.read(1)
                if not chunk:
                    continue
                if chunk != b'\n':
                    buffer.extend(chunk)
                    if len(buffer) > 4096:
                        buffer.clear()
                    continue
                line = bytes(buffer)
                buffer.clear()
                try:
                    reply = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue  # Boot and orientation logs share this UART.
                if not isinstance(reply, dict) or reply.get('id') != request_id:
                    continue
                if reply.get('ok') is not True:
                    raise RuntimeError(reply.get('error', 'Device rejected command'))
                if op == 'identify':
                    if reply.get('device') != 'm5stack-matrix-agent' or reply.get('protocol') != 1:
                        raise RuntimeError('Not a compatible Matrix firmware')
                    return reply
                result = reply.get('state')
                if result not in STATES or (op == 'set' and result != state):
                    raise RuntimeError('Invalid state in device acknowledgement')
                return result
            raise TimeoutError('Matrix did not acknowledge the command; device state is unknown')

    def reconnect(self):
        """Close the stale handle, reopen and verify firmware; return COMx.

        Auto mode rediscovers ports (including changed COM numbers); explicit
        port mode retries that port only. Does not change the displayed state.
        Raises TimeoutError if recovery fails within reconnect_timeout.
        An explicit call may reopen a controller previously closed by the caller.
        """
        with self._lock:
            self._disconnect()
            self._closed = False
            deadline = time.monotonic() + self.reconnect_timeout
            last_error = None
            while time.monotonic() < deadline:
                try:
                    port = self._requested_port
                    if port is None:
                        port = detect_port(min(1.0, self.reconnect_timeout), _deadline=deadline)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._open_port(port)
                    self._request('identify', timeout=min(1.0, remaining))
                    return self.port
                except (serial.SerialException, OSError, TimeoutError, RuntimeError) as error:
                    last_error = error
                    self._disconnect()
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        time.sleep(min(0.2, remaining))
            self._disconnect()
            raise TimeoutError('Matrix reconnection timed out') from last_error

    def get_connect_state(self, timeout=0.5):
        """Probe firmware without reconnecting; return COMx or 'disconnect'.

        A short live handshake detects stale handles after physical USB removal.
        This checks communication now; it does not change the animation.
        """
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be a finite positive number')
        with self._lock:
            if self._closed or self._serial is None or not self._serial.is_open:
                return 'disconnect'
            try:
                self._request('identify', timeout=timeout)
                return self.port
            except (serial.SerialException, OSError, TimeoutError, RuntimeError):
                self._disconnect()
                return 'disconnect'

    def _perform(self, op, state=None):
        with self._lock:
            if self._closed:
                raise serial.SerialException('Controller closed; call reconnect() explicitly')
            try:
                return self._request(op, state)
            except (serial.SerialException, OSError, TimeoutError):
                self.reconnect()
                try:
                    return self._request(op, state)  # Replay this request once.
                except (serial.SerialException, OSError, TimeoutError):
                    self._disconnect()
                    raise

    def set_state(self, state):
        """Set done/running/attention/idle; return the acknowledged state.

        Re-sending the current state does not restart its animation.
        """
        if not isinstance(state, str) or state.strip().lower() not in STATES:
            raise ValueError('state must be done, running, attention, or idle')
        return self._perform('set', state.strip().lower())

    def get_state(self):
        """Query the currently displayed mode without changing it."""
        return self._perform('get')

    def close(self):
        with self._lock:
            self._closed = True
            self._disconnect()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def set_state(state, port=None, timeout=5.0):
    """Open USB, set a state, wait for ACK, then close USB."""
    # Validate before opening the device.
    if not isinstance(state, str) or state.strip().lower() not in STATES:
        raise ValueError('state must be done, running, attention, or idle')
    with MatrixController(port, timeout) as matrix:
        return matrix.set_state(state)
