"""Passively verify manual mode and repeated animation after a reset."""
from pathlib import Path
import time
import serial

port = serial.Serial()
port.port = 'COM3'
port.baudrate = 115200
port.timeout = 0.25
port.dtr = False
port.rts = False
port.open()
capture = bytearray()
try:
    deadline = time.monotonic() + 24
    while time.monotonic() < deadline:
        capture.extend(port.read(max(1, port.in_waiting)))
finally:
    port.close()
output = capture.decode('utf-8', errors='replace')
Path(__file__).with_name('firmware').joinpath('runtime.log').write_text(output, encoding='utf-8')
print(output)
assert 'Traceback' not in output, 'Device reported an exception'
assert 'mode=usb' in output, 'Missing USB-mode startup'
assert output.count('LOOP ') >= 2, 'Expected repeated animation cycles'
print('PASS: USB mode and repeated animation observed on device.')
