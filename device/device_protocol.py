"""Bounded newline-delimited JSON commands; compatible with MicroPython."""
import json

STATES = ('done', 'running', 'attention', 'idle')


class Receiver:
    def __init__(self):
        self.buffer = ''
        self.overflow = False

    def feed(self, char):
        if char == '\r':
            return None
        if char != '\n':
            if len(self.buffer) < 256 and not self.overflow:
                self.buffer += char
            else:
                self.overflow = True
            return None
        line, overflow = self.buffer, self.overflow
        self.buffer, self.overflow = '', False
        if overflow:
            return {'id': None, 'error': 'line too long'}
        if not line:
            return None
        request_id = None
        try:
            command = json.loads(line)
            if not isinstance(command, dict):
                raise ValueError('expected object')
            request_id = command.get('id')
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 40:
                raise ValueError('invalid id')
            op = command.get('op')
            if op in ('get', 'identify'):
                return {'id': request_id, 'op': op}
            state = command.get('state')
            if op != 'set' or state not in STATES:
                raise ValueError('expected set with done/running/attention/idle')
            return {'id': request_id, 'op': op, 'state': STATES.index(state)}
        except (ValueError, TypeError) as error:
            return {'id': request_id, 'error': str(error)}
