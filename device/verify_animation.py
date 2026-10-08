"""Host-side exhaustive frame check without attached hardware."""
import importlib.util
import sys
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import time
time.ticks_diff = lambda a, b: a - b


class Pixels:
    def __init__(self, pin, count):
        self.data = [(0, 0, 0)] * count

    def fill(self, color):
        self.data[:] = [color] * len(self.data)

    def __getitem__(self, index):
        return self.data[index]

    def __setitem__(self, index, color):
        assert 0 <= index < 25
        assert len(color) == 3 and all(0 <= c <= 40 for c in color)
        self.data[index] = color

    def write(self):
        pass


class Pin:
    IN = 0

    def __init__(self, *args):
        pass


sys.modules['machine'] = types.SimpleNamespace(Pin=Pin, I2C=object)
sys.modules['neopixel'] = types.SimpleNamespace(NeoPixel=Pixels)
spec = importlib.util.spec_from_file_location('animation', Path(__file__).with_name('main.py'))
animation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(animation)
for state in range(4):
    frames = set()
    for elapsed in range(0, 5000, 30):
        animation.render(state, elapsed)
        frames.add(tuple(animation.leds.data))
    assert len(frames) > 10, 'Animation must change over time'
    animation.render(state, 1000)
    active = [c for c in animation.leds.data if any(c)]
    assert active, 'Each state must illuminate pixels'
    if state == 0:
        assert all(g > r and g > b for r, g, b in active)
    elif state == 1:
        assert all(r >= g > 0 and b == 0 for r, g, b in active)
    elif state == 2:
        assert all(r > 0 and g == b == 0 for r, g, b in active)
    else:
        assert all(b > r and b > g for r, g, b in active)
    print(animation.NAMES[state], len(frames), 'distinct frames: OK')

# Red breathes slowly: off, center, 3x3, full, 3x3, center, off.
def red_rings(elapsed):
    animation.render(2, elapsed)
    return tuple(animation.leds.data[index][0] for index in (12, 7, 2))

for elapsed, expected in ((0, (0, 0, 0)), (300, (19, 0, 0)),
                          (600, (40, 5, 0)), (750, (40, 19, 0)),
                          (1050, (40, 40, 5)), (1200, (40, 40, 19)),
                          (1500, (40, 40, 40)), (2699, (40, 40, 40)),
                          (3000, (40, 40, 20)), (3150, (40, 40, 5)),
                          (3450, (40, 20, 0)), (3600, (40, 5, 0)),
                          (3900, (20, 0, 0)), (4199, (0, 0, 0)),
                          (4200, (0, 0, 0))):
    assert red_rings(elapsed) == expected, 'Unexpected red rings at %dms' % elapsed
for start, end in ((0, 600), (450, 1050), (900, 1500),
                   (2700, 3300), (3150, 3750), (3600, 4200)):
    frames = set()
    for elapsed in range(start, end, 30):
        animation.render(2, elapsed)
        frames.add(tuple(animation.leds.data))
    assert len(frames) >= 15, 'Red transition must breathe smoothly at %dms' % start
animation.render(2, animation.ATTENTION_MS - 1)
before = tuple(animation.leds.data)
animation.render(2, 0)
assert max(abs(a[0] - b[0]) for a, b in zip(before, animation.leds.data)) <= 1
print('PASS: red breathes smoothly, holds, and loops without flashing')

# Regression: yellow must stay lit past 5s and cross its period without a jump.
for elapsed in (0, 2070, 2099, 2100, 2130, 4999, 5000, 5030, 6000):
    animation.render(1, elapsed)
    frame = tuple(animation.leds.data)
    assert max(c[0] for c in frame) >= 25, 'Waterfall must not fade to black'
    animation.render(1, elapsed + animation.WATERFALL_MS)
    assert tuple(animation.leds.data) == frame, 'Waterfall period must match'
animation.render(1, animation.WATERFALL_MS - 1)
before = tuple(animation.leds.data)
animation.render(1, 0)
assert max(abs(a[0] - b[0]) for a, b in zip(before, animation.leds.data)) <= 1
print('PASS: yellow waterfall has a seamless wrap and no 5-second blackout')

# Blue flows continuously at its own period, including across the old 5s cut.
for elapsed in (0, 4199, 4200, 4230, 4999, 5000, 5030, 9000):
    animation.render(3, elapsed)
    frame = tuple(animation.leds.data)
    assert max(c[2] for c in frame) >= 25, 'Blue must not fade to black'
    animation.render(3, elapsed + animation.IDLE_MS)
    assert tuple(animation.leds.data) == frame
animation.render(3, animation.IDLE_MS - 1)
before = tuple(animation.leds.data)
animation.render(3, 0)
assert max(abs(a[2] - b[2]) for a, b in zip(before, animation.leds.data)) <= 1
print('PASS: blue seamless wave and no 5-second blackout')

# Full green check remains steady, then reaches black before a fresh stroke.
for elapsed in (1000, 3000, 5999):
    animation.render(0, elapsed)
    assert sum(c[1] == 40 for c in animation.leds.data) == 5
animation.render(0, 6500)
assert max(c[1] for c in animation.leds.data) == 20
animation.render(0, 6999)
before = tuple(animation.leds.data)
animation.render(0, 0)
assert tuple(animation.leds.data) == before
print('PASS: green hold and seamless fade/restart')

# Every rotation is a bijection and preserves the rendered pixels/colors.
for state in range(4):
    animation.rotation = 0
    animation.render(state, 1000)
    baseline = sorted(animation.leds.data)
    for rotation in range(4):
        animation.rotation = rotation
        animation.render(state, 1000)
        assert sorted(animation.leds.data) == baseline

from orientation import Orientation
for vector, expected in (((0, 1, 0), 0), ((-1, 0, 0), 1),
                         ((0, -1, 0), 2), ((1, 0, 0), 3)):
    orientation = Orientation()
    for now in range(0, 1000, 50):
        orientation.update(vector, now)
    assert orientation.rotation == expected
    for now in range(1000, 2000, 50):
        orientation.update((0, 0, 1), now)
    assert orientation.rotation == expected, 'Flat position must hold direction'
    for now in range(2000, 3000, 50):
        orientation.update((0.707, 0.707, 0), now)
    assert orientation.rotation == expected, 'Diagonal position must not chatter'
orientation = Orientation()
orientation.update((1, 0, 0), 0)
orientation.update((1, 0, 0), 200)
assert orientation.rotation == 0, 'Must debounce before rotating'
orientation.update((1, 0, 0), 250)
assert orientation.rotation == 3
print('PASS: four rotations, flat/diagonal hold and debounce')
