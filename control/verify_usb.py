"""Live integration check. Run after resetting the device; leaves it blue."""
import time
from matrix_control import MatrixController, detect_port, set_state

print('AUTO', detect_port())
with MatrixController() as matrix:
    assert matrix.get_state() == 'idle', 'Boot default must be blue/idle'
    print('PASS: boot state is idle')
    for state in ('done', 'running', 'attention', 'idle'):
        assert matrix.set_state(state) == state
        time.sleep(0.4)
        assert matrix.get_state() == state
        assert matrix.set_state(state) == state
        print('PASS: USB set/query/repeated set', state)
    matrix._serial.write(b'not-json\n' + b'x' * 300 + b'\n')
    time.sleep(0.3)
    assert matrix.get_state() == 'idle'
    print('PASS: malformed and oversized messages preserve state and recover')
assert set_state('running') == 'running'
with MatrixController() as matrix:
    assert matrix.get_state() == 'running', 'Closing USB must preserve state'
assert set_state('idle') == 'idle'
print('PASS: one-shot function, reopen, retained state; final state idle')
