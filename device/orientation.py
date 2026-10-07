"""BMI270 accelerometer and stable four-way orientation for ATOM Matrix v1.1."""
from machine import Pin, I2C
import struct
import time


class Gravity:
    def __init__(self):
        self.bus = I2C(0, scl=Pin(21), sda=Pin(25), freq=400000)
        if self.bus.readfrom_mem(0x68, 0x00, 1)[0] != 0x24:
            raise RuntimeError('Expected BMI270')
        self.write(0x7E, 0xB6)
        time.sleep_ms(10)
        self.write(0x7C, 0)
        time.sleep_ms(2)
        self.write(0x59, 0)
        with open('bmi270_config.bin', 'rb') as config:
            for offset in range(0, 8192, 32):
                block = config.read(32)
                if len(block) != 32:
                    raise RuntimeError('Incomplete BMI270 config')
                self.bus.writeto_mem(0x68, 0x5B,
                                    bytes(((offset >> 1) & 15, offset >> 5)))
                self.bus.writeto_mem(0x68, 0x5E, block)
        self.write(0x59, 1)
        time.sleep_ms(150)
        status = self.bus.readfrom_mem(0x68, 0x21, 1)[0] & 15
        if status != 1:
            raise RuntimeError('BMI270 config status %d' % status)
        self.write(0x40, 0xA8)  # 100 Hz, normal averaging, performance mode
        self.write(0x41, 0)     # +/-2g (16384 LSB/g)
        self.write(0x7D, 4)     # Accelerometer only
        time.sleep_ms(80)
        print('IMU BMI270 READY')

    def write(self, register, value):
        self.bus.writeto_mem(0x68, register, bytes((value,)))

    def read(self):
        values = struct.unpack('<hhh', self.bus.readfrom_mem(0x68, 0x0C, 6))
        return tuple(v / 16384 for v in values)


class Orientation:
    def __init__(self):
        self.rotation = 0
        self.candidate = 0
        self.since = 0
        self.filtered = None

    def update(self, acceleration, now):
        x, y, z = acceleration
        # Ignore free fall and strong shaking; accelerometer is not gravity then.
        magnitude2 = x*x + y*y + z*z
        if not 0.55 < magnitude2 < 1.65:
            self.filtered = None
            self.candidate = self.rotation
            self.since = now
            return self.rotation
        if self.filtered is None:
            self.filtered = (x, y)
        else:
            fx, fy = self.filtered
            self.filtered = (fx * 0.7 + x * 0.3, fy * 0.7 + y * 0.3)
        x, y = self.filtered
        # ATOM Matrix raw BMI270 X/Y correspond to screen down-vector X/Y.
        # M5Unified's board correction is (-X,+Y,-Z), then convert proper
        # acceleration to gravity and screen Y-down coordinates.
        ax, ay = abs(x), abs(y)
        if max(ax, ay) < 0.38 or abs(ax - ay) < 0.14:
            self.candidate = self.rotation
            self.since = now
            return self.rotation
        target = (3 if x > 0 else 1) if ax > ay else (0 if y > 0 else 2)
        if target != self.candidate:
            self.candidate = target
            self.since = now
        elif target != self.rotation and time.ticks_diff(now, self.since) >= 250:
            self.rotation = target
            print('ORIENTATION', target * 90)
        return self.rotation
