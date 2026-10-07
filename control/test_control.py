import json
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import serial
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'device'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from device_protocol import Receiver
from matrix_control import MatrixController, detect_port, set_state


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.data = bytearray()
        self.state = 'idle'
        self.receiver = Receiver()

    def open(self): self.is_open = True
    def close(self): self.is_open = False
    def reset_input_buffer(self): self.data.clear()

    def write(self, payload):
        for char in payload.decode():
            command = self.receiver.feed(char)
            if command:
                if command.get('op') == 'set':
                    self.state = ('done', 'running', 'attention', 'idle')[command['state']]
                self.data.extend(b'LOOP IDLE\n{"id":"stale","ok":true}\n')
                self.data.extend((json.dumps({'id': command['id'], 'ok': True,
                                              'state': self.state, 'device': 'm5stack-matrix-agent',
                                              'protocol': 1}) + '\n').encode())
        return len(payload)

    def read(self, count):
        result = bytes(self.data[:count])
        del self.data[:count]
        return result


class ControlTests(unittest.TestCase):
    def test_fragmented_invalid_and_overlong_input_recovers(self):
        receiver = Receiver()
        for line in ('oops\n', '[]\n', '{"id":"x","op":"set","state":"bad"}\n',
                     'a' * 300 + '\n'):
            replies = [reply for c in line if (reply := receiver.feed(c)) is not None]
            self.assertIn('error', replies[-1])
        command = None
        for c in '{"id":"x","op":"set","state":"running"}\n':
            command = receiver.feed(c)
        self.assertEqual(command['state'], 1)

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_ack_matching_all_states_and_one_shot(self):
        with MatrixController('COM3') as matrix:
            self.assertEqual(matrix.get_state(), 'idle')
            for state in ('done', 'running', 'attention', 'idle'):
                self.assertEqual(matrix.set_state(state), state)
                self.assertEqual(matrix.get_state(), state)
            self.assertEqual(matrix.set_state(' RUNNING '), 'running')
        self.assertEqual(set_state('attention', port='COM3'), 'attention')

    @patch('matrix_control.serial.Serial')
    def test_bad_state_does_not_open_port(self, serial_class):
        with self.assertRaises(ValueError):
            set_state('unknown')
        serial_class.assert_not_called()

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_missing_ack_raises_timeout(self):
        with MatrixController('COM3', timeout=0.01) as matrix:
            matrix._serial.read = lambda count: b''
            with self.assertRaises(TimeoutError):
                matrix._request('get')

    @patch('matrix_control.serial.Serial', FakeSerial)
    @patch('matrix_control.list_ports.comports')
    def test_discovery_unique_absent_and_ambiguous(self, ports):
        ports.return_value = [SimpleNamespace(device='COM9', vid=0x0403, pid=0x6001),
                              SimpleNamespace(device='COM8', vid=123, pid=456)]
        self.assertEqual(detect_port(), 'COM9')
        with MatrixController() as matrix:
            self.assertEqual(matrix.port, 'COM9')
        ports.return_value.append(SimpleNamespace(device='COM10', vid=0x0403, pid=0x6001))
        with self.assertRaisesRegex(RuntimeError, 'Multiple'):
            detect_port()
        ports.return_value = []
        with self.assertRaisesRegex(RuntimeError, 'No Matrix'):
            detect_port()

    @patch('matrix_control.list_ports.comports')
    @patch('matrix_control.MatrixController._request', return_value=None)
    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_explicit_port_skips_discovery(self, request, ports):
        with MatrixController('COM7') as matrix:
            self.assertEqual(matrix.port, 'COM7')
        ports.assert_not_called()

    @patch('matrix_control.serial.Serial', FakeSerial)
    @patch('matrix_control.list_ports.comports')
    @patch('matrix_control.MatrixController._request')
    def test_discovery_retries_boot_timeout_and_rejects_wrong_device(self, request, ports):
        ports.return_value = [SimpleNamespace(device='COM9', vid=0x0403, pid=0x6001)]
        request.side_effect = [TimeoutError(), {'device': 'm5stack-matrix-agent'}]
        self.assertEqual(detect_port(), 'COM9')
        self.assertEqual(request.call_count, 2)
        request.side_effect = RuntimeError('Not a compatible Matrix firmware')
        with self.assertRaisesRegex(RuntimeError, 'No Matrix'):
            detect_port()

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_identity_checks_firmware_tag(self):
        with MatrixController('COM3') as matrix:
            write = matrix._serial.write
            def wrong_identity(payload):
                result = write(payload)
                matrix._serial.data = matrix._serial.data.replace(
                    b'm5stack-matrix-agent', b'unrelated-device')
                return result
            matrix._serial.write = wrong_identity
            with self.assertRaisesRegex(RuntimeError, 'Not a compatible'):
                matrix._request('identify')

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_stale_handle_automatically_reconnects_and_replays(self):
        with MatrixController('COM3') as matrix:
            old = matrix._serial
            old.close()
            self.assertEqual(matrix.set_state('attention'), 'attention')
            self.assertIsNot(matrix._serial, old)
            self.assertEqual(matrix.get_connect_state(), 'COM3')

    @patch('matrix_control.serial.Serial', FakeSerial)
    @patch('matrix_control.detect_port', side_effect=['COM3', 'COM9'])
    def test_auto_reconnect_can_follow_changed_port(self, detect):
        with MatrixController() as matrix:
            matrix._serial.close()
            self.assertEqual(matrix.set_state('running'), 'running')
            self.assertEqual(matrix.port, 'COM9')
            self.assertEqual(detect.call_count, 2)

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_connection_probe_reports_failure_without_reconnecting(self):
        with MatrixController('COM3') as matrix:
            old = matrix._serial
            old.read = lambda count: b''
            self.assertEqual(matrix.get_connect_state(timeout=0.01), 'disconnect')
            self.assertIs(matrix._serial, old)
            self.assertFalse(old.is_open)
            self.assertEqual(matrix.reconnect(), 'COM3')
            self.assertEqual(matrix.get_connect_state(), 'COM3')

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_explicit_close_requires_explicit_reconnect(self):
        matrix = MatrixController('COM3')
        matrix.close()
        self.assertEqual(matrix.get_connect_state(), 'disconnect')
        with self.assertRaises(serial.SerialException):
            matrix.set_state('done')
        self.assertEqual(matrix.reconnect(), 'COM3')
        matrix.close()

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_reconnect_failure_is_bounded_and_next_call_can_recover(self):
        with MatrixController('COM3', reconnect_timeout=0.03) as matrix:
            matrix._serial.close()
            start = time.monotonic()
            with patch('matrix_control.serial.Serial', side_effect=serial.SerialException('gone')):
                with self.assertRaises(TimeoutError):
                    matrix.set_state('done')
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertEqual(matrix.get_connect_state(), 'disconnect')
            self.assertEqual(matrix.set_state('done'), 'done')

    @patch('matrix_control.serial.Serial', FakeSerial)
    def test_lost_ack_recovers_but_device_rejection_does_not_retry(self):
        with MatrixController('COM3', timeout=0.01) as matrix:
            matrix._serial.read = lambda count: b''
            self.assertEqual(matrix.set_state('running'), 'running')
            with patch.object(matrix, '_request', side_effect=RuntimeError('rejected')):
                with patch.object(matrix, 'reconnect') as reconnect:
                    with self.assertRaises(RuntimeError):
                        matrix.set_state('done')
                    reconnect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
