#!/usr/bin/env python3
import smbus
import time
import os

# I2C Setup
bus = smbus.SMBus(1)
PCA9555_ADDR = 0x20

INPUT_PORT_1 = 0x01
OUTPUT_PORT_1 = 0x03
CONFIG_PORT_1 = 0x07

def init_gpio():
    """GPIO konfigurieren"""
    config = bus.read_byte_data(PCA9555_ADDR, CONFIG_PORT_1)
    config |= 0x80   # Bit 7 = Input (Taster)
    config &= ~0x20  # Bit 5 = Output (Lampe)
    bus.write_byte_data(PCA9555_ADDR, CONFIG_PORT_1, config)
    
    # Lampe aus
    set_lamp(False)

def read_button():
    """Taster lesen"""
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
    print("Reboot-Taster aktiv...")
    
    while True:
        if read_button():  # Taster gedrückt
            print("Taster gedrückt!")
            set_lamp(True)          # 1. Lampe EIN
            print("Lampe aktiviert - Reboot in 2 Sekunden...")
            time.sleep(2)           # Kurz warten
            os.system("reboot") # 2. Reboot
            break
        
        time.sleep(0.1)  # 100ms Polling

if __name__ == "__main__":
    main()

