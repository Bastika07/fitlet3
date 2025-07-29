#!/usr/bin/env python3
import smbus
import time

# I2C Setup
bus = smbus.SMBus(1)
PCA9555_ADDR = 0x20

INPUT_PORT_1 = 0x01
OUTPUT_PORT_1 = 0x03
CONFIG_PORT_1 = 0x07

def init_gpio():
    """GPIO konfigurieren"""
    config = bus.read_byte_data(PCA9555_ADDR, CONFIG_PORT_1)
    config |= 0x80   # Bit 7 = Input (Schalter)
    config &= ~0x20  # Bit 5 = Output (Lampe)
    bus.write_byte_data(PCA9555_ADDR, CONFIG_PORT_1, config)

def read_switch():
    """Schalter-Status lesen"""
    data = bus.read_byte_data(PCA9555_ADDR, INPUT_PORT_1)
    return not bool(data & 0x80)  # Invertiert (Pull-up)

def set_lamp(state):
    """Lampe ein/aus"""
    data = bus.read_byte_data(PCA9555_ADDR, OUTPUT_PORT_1)
    if state:
        data |= 0x20   # Lampe EIN
    else:
        data &= ~0x20  # Lampe AUS
    bus.write_byte_data(PCA9555_ADDR, OUTPUT_PORT_1, data)

def main():
    init_gpio()
    print("Status-Schalter aktiv...")
    
    while True:
        switch_state = read_switch()
        set_lamp(switch_state)  # Lampe = Schalter-Status
        
        time.sleep(0.1)  # 100ms Polling

if __name__ == "__main__":
    main()

