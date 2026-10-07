"""esptool wrapper with a larger Windows FTDI receive buffer."""
import serial
import esptool

original_open = serial.Serial.open


def buffered_open(port):
    original_open(port)
    if hasattr(port, 'set_buffer_size'):
        port.set_buffer_size(rx_size=131072, tx_size=131072)


serial.Serial.open = buffered_open
if __name__ == '__main__':
    esptool._main()
