"""M5Stack ATOM Matrix: four agent-status demo animations.

25 WS2812 LEDs on GPIO27; front button GPIO39 (external pull-up).
Press the face to change mode; each animation repeats until the next press.
RGB components stay at or below 40/255 to keep brightness comfortable.
"""
from machine import Pin
from orientation import Gravity, Orientation
import neopixel
import time
import math
import sys
import select
import json
from device_protocol import Receiver, STATES

leds = neopixel.NeoPixel(Pin(27), 25)
button = Pin(39, Pin.IN)
IDLE_MS = 4200
ATTENTION_MS = 3000
WATERFALL_MS = 2100
DONE_MS = 7000
NAMES = ('DONE', 'RUNNING', 'ATTENTION', 'IDLE')
CHECK = ((0, 2), (1, 3), (2, 2), (3, 1), (4, 0))
rotation = 0


def pixel(x, y, color, level=1.0):
    for _ in range(rotation):
        x, y = 4 - y, x
    leds[y * 5 + x] = tuple(int(v * level) for v in color)


def render(state, elapsed):
    leds.fill((0, 0, 0))
    if state == 0:
        # Draw once, hold the whole check for five seconds, then fade to black.
        phase = elapsed % DONE_MS
        fade = max(0.0, min(1.0, (DONE_MS - phase) / 1000))
        fade = fade * fade * (3 - 2 * fade)
        for index, (x, y) in enumerate(CHECK):
            progress = max(0.0, min(1.0, (phase - index * 160) / 200))
            glow = progress * progress * (3 - 2 * progress)
            pixel(x, y, (0, 40, 5), glow * fade)
    elif state == 1:
        # Half-speed falling bands; periodic cosine keeps the wrap seamless.
        head = (elapsed % WATERFALL_MS) / 300
        for y in range(5):
            for x in range(5):
                distance = (head - y - (0, 0, 0.55, 1.1, 1.1)[x]) % 7
                level = (0.5 + 0.5 * math.cos(2 * math.pi * distance / 7)) ** 2
                pixel(x, y, (36, 25, 0), level)
    elif state == 2:
        # Breathe out through the three square layers, hold, then breathe in.
        phase = elapsed % ATTENTION_MS
        if phase < 300 or phase >= 2700:
            radius_limit = -1
        elif phase < 600 or phase >= 2400:
            radius_limit = 0
        elif phase < 900 or phase >= 2100:
            radius_limit = 1
        else:
            radius_limit = 2
        for y in range(5):
            for x in range(5):
                if max(abs(x - 2), abs(y - 2)) <= radius_limit:
                    pixel(x, y, (40, 0, 0))
    else:
        # Quiet blue water: a wide rolling crest over a dim lower body.
        for x in range(5):
            surface = 2.1 + 0.85 * math.sin(x * 0.9 - 2 * math.pi * (elapsed % IDLE_MS) / IDLE_MS)
            for y in range(5):
                crest = max(0.0, 1.0 - abs(y - surface) / 1.25)
                body = 0.16 if y > surface else 0
                pixel(x, y, (3, 15, 36), max(crest, body))
    # Each animation owns its envelope; flowing water never fades at a wrap.
    leds.write()


def run():
    global rotation
    state = 3
    render(state, 1000)  # Blue immediately, including during IMU initialization.
    receiver = Receiver()
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    orientation = Orientation()
    try:
        gravity = Gravity()
        print('ACCEL', gravity.read())
    except Exception as error:
        gravity = None
        print('IMU ERROR', error)
    start = time.ticks_ms()
    raw_previous = button.value()
    stable = raw_previous
    changed = start
    last_imu = start
    imu_errors = 0
    print('MATRIX_DEMO READY; mode=usb; button=next; animation=repeat')
    print('STATE', NAMES[state])
    while True:
        now = time.ticks_ms()
        if gravity is not None and time.ticks_diff(now, last_imu) >= 50:
            last_imu = now
            try:
                rotation = orientation.update(gravity.read(), now)
                imu_errors = 0
            except OSError as error:
                imu_errors += 1
                if imu_errors == 1:
                    print('IMU READ ERROR', error)
        raw = button.value()
        if raw != raw_previous:
            raw_previous = raw
            changed = now
        pressed = False
        if raw != stable and time.ticks_diff(now, changed) >= 40:
            stable = raw
            pressed = stable == 0
        elapsed = time.ticks_diff(now, start)
        duration = (DONE_MS, WATERFALL_MS, ATTENTION_MS, IDLE_MS)[state]
        if pressed:
            state = (state + 1) % 4
            start = now
            elapsed = 0
            print('STATE', NAMES[state])
        elif elapsed >= duration:
            # Preserve the frame's overshoot instead of pausing at the seam.
            start = time.ticks_add(start, duration)
            elapsed = time.ticks_diff(now, start)
            print('LOOP', NAMES[state])
        # Bounded work per frame: partial USB messages never block animation.
        for _ in range(256):
            if not poller.poll(0):
                break
            char = sys.stdin.read(1)
            if not char:
                break
            command = receiver.feed(char)
            if command is None:
                continue
            if 'error' in command:
                print(json.dumps({'id': command['id'], 'ok': False,
                                  'error': command['error']}))
                continue
            if command['op'] == 'set' and state != command['state']:
                state = command['state']
                start = now
                elapsed = 0
                print('STATE', NAMES[state])
            print(json.dumps({'id': command['id'], 'ok': True, 'state': STATES[state],
                              'device': 'm5stack-matrix-agent', 'protocol': 1}))
        render(state, elapsed)
        time.sleep_ms(30)


if __name__ == '__main__':
    run()
