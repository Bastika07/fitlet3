#!/bin/bash

# Fitlet3 Status Switch Installation Script - EFI Boot Version
# Für Systeme mit UEFI/EFI Boot

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "Dieses Script muss als root ausgeführt werden."
        exit 1
    fi
}

detect_boot_system() {
    print_info "Erkenne Boot-System..."
    
    if [ -d /sys/firmware/efi ]; then
        print_info "EFI/UEFI Boot System erkannt"
        BOOT_TYPE="EFI"
    else
        print_info "Legacy Boot System erkannt"
        BOOT_TYPE="LEGACY"
    fi
    
    # Suche Boot-Konfigurationsdateien
    BOOT_CONFIG=""
    if [ -f /boot/efi/config.txt ]; then
        BOOT_CONFIG="/boot/efi/config.txt"
        print_info "Boot-Konfiguration: /boot/efi/config.txt"
    elif [ -f /boot/firmware/config.txt ]; then
        BOOT_CONFIG="/boot/firmware/config.txt"
        print_info "Boot-Konfiguration: /boot/firmware/config.txt"
    elif [ -f /boot/config.txt ]; then
        BOOT_CONFIG="/boot/config.txt"
        print_info "Boot-Konfiguration: /boot/config.txt"
    else
        print_warning "Keine Boot-Konfigurationsdatei gefunden"
    fi
    
    # Suche Kernel-Kommandozeile
    CMDLINE_FILE=""
    if [ -f /boot/efi/cmdline.txt ]; then
        CMDLINE_FILE="/boot/efi/cmdline.txt"
    elif [ -f /boot/firmware/cmdline.txt ]; then
        CMDLINE_FILE="/boot/firmware/cmdline.txt"
    elif [ -f /boot/cmdline.txt ]; then
        CMDLINE_FILE="/boot/cmdline.txt"
    fi
    
    if [ -n "$CMDLINE_FILE" ]; then
        print_info "Kernel-Kommandozeile: $CMDLINE_FILE"
    else
        print_warning "Keine Kernel-Kommandozeile gefunden"
    fi
}

enable_i2c_efi() {
    print_info "Aktiviere I2C für EFI-System..."
    
    # I2C Module zu /etc/modules hinzufügen
    if ! grep -q "i2c-dev" /etc/modules; then
        echo "i2c-dev" >> /etc/modules
        print_info "i2c-dev zu /etc/modules hinzugefügt"
    fi
    
    # Modprobe Konfiguration
    if [ ! -f /etc/modprobe.d/i2c.conf ]; then
        cat > /etc/modprobe.d/i2c.conf << 'EOF'
# I2C Konfiguration für Fitlet3
options i2c_designware_core speed_mode=1
options i2c_designware_pci speed_mode=1
EOF
        print_info "I2C Modprobe-Konfiguration erstellt"
    fi
    
    # Boot-Konfiguration anpassen (falls verfügbar)
    if [ -n "$BOOT_CONFIG" ]; then
        if ! grep -q "dtparam=i2c" "$BOOT_CONFIG"; then
            echo "" >> "$BOOT_CONFIG"
            echo "# I2C Konfiguration für Fitlet3" >> "$BOOT_CONFIG"
            echo "dtparam=i2c_arm=on" >> "$BOOT_CONFIG"
            echo "dtparam=i2c2=on" >> "$BOOT_CONFIG"
            echo "dtparam=i2c2_baudrate=50000" >> "$BOOT_CONFIG"
            print_info "I2C zu Boot-Konfiguration hinzugefügt"
        fi
    fi
    
    # Kernel-Parameter anpassen (falls verfügbar)
    if [ -n "$CMDLINE_FILE" ]; then
        if ! grep -q "i2c-designware" "$CMDLINE_FILE"; then
            sed -i 's/$/ i2c-designware-pci.speed_mode=1/' "$CMDLINE_FILE"
            print_info "I2C Kernel-Parameter hinzugefügt"
        fi
    fi
    
    # I2C Module sofort laden
    modprobe i2c-dev 2>/dev/null || true
    modprobe i2c-designware-core 2>/dev/null || true
    modprobe i2c-designware-pci 2>/dev/null || true
    
    print_success "I2C für EFI-System aktiviert"
}

enable_i2c_systemd() {
    print_info "Erstelle systemd Service für I2C Initialisierung..."
    
    cat > /etc/systemd/system/fitlet3-i2c-init.service << 'EOF'
[Unit]
Description=Fitlet3 I2C Initialization
DefaultDependencies=false
After=sysinit.target local-fs.target
Before=basic.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'modprobe i2c-dev; modprobe i2c-designware-core; modprobe i2c-designware-pci'
TimeoutSec=30

[Install]
WantedBy=basic.target
EOF

    systemctl daemon-reload
    systemctl enable fitlet3-i2c-init.service
    print_success "I2C Initialisierungs-Service erstellt"
}

install_dependencies() {
    print_info "Installiere Abhängigkeiten..."
    apt update
    apt install -y python3 python3-smbus i2c-tools
}

test_i2c_efi() {
    print_info "Teste I2C auf EFI-System..."
    
    # Warte kurz auf Hardware-Initialisierung
    sleep 2
    
    # Teste verschiedene Busse
    for bus in 0 1 2 3; do
        if [ -e "/dev/i2c-$bus" ]; then
            print_info "Teste Bus $bus..."
            if timeout 5 i2cdetect -y "$bus" 2>/dev/null | grep -q "20"; then
                print_success "PCA9555 gefunden auf Bus $bus!"
                FOUND_BUS=$bus
                return 0
            fi
        fi
    done
    
    print_error "PCA9555 nicht gefunden!"
    print_info "Verfügbare I2C Busse:"
    ls -la /dev/i2c* 2>/dev/null || print_warning "Keine I2C Geräte gefunden"
    return 1
}

create_python_script_efi() {
    print_info "Erstelle EFI-kompatibles Python Script..."
    
    cat > /usr/local/bin/fitlet3-status-switch.py << 'EOF'
#!/usr/bin/env python3
"""
Fitlet3 Status Switch Service - Simplified
Startet ohne initiale Zustandslesung, reagiert nur auf Änderungen
"""

import smbus
import time
import signal
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bus = smbus.SMBus(3)
PCA9555_ADDR = 0x20

class StatusSwitchSimple:
    def __init__(self):
        self.running = True
        self.last_switch_state = None  # Startet mit None
        
    def init_gpio(self):
        """GPIO konfigurieren"""
        try:
            logger.info("Initialisiere GPIO...")
            
            config = bus.read_byte_data(PCA9555_ADDR, 0x07)
            config |= 0x80   # Bit 7 = Input (Schalter)
            config &= ~0x20  # Bit 5 = Output (Lampe)
            bus.write_byte_data(PCA9555_ADDR, 0x07, config)
            
            # Lampe initial ausschalten
            output = bus.read_byte_data(PCA9555_ADDR, 0x03)
            output &= ~0x20  # Lampe AUS
            bus.write_byte_data(PCA9555_ADDR, 0x03, output)
            
            logger.info("GPIO initialisiert - Lampe AUS")
            return True
            
        except Exception as e:
            logger.error(f"GPIO Initialisierung fehlgeschlagen: {e}")
            return False

    def read_switch(self):
        """NC Schalter lesen"""
        try:
            data = bus.read_byte_data(PCA9555_ADDR, 0x01)
            return bool(data & 0x80)  # NC Logik
        except Exception as e:
            logger.error(f"Schalter-Lesefehler: {e}")
            return False

    def set_lamp(self, state):
        """Lampe setzen"""
        try:
            data = bus.read_byte_data(PCA9555_ADDR, 0x03)
            if state:
                data |= 0x20
            else:
                data &= ~0x20
            bus.write_byte_data(PCA9555_ADDR, 0x03, data)
            return True
        except Exception as e:
            logger.error(f"Lampe-Setzfehler: {e}")
            return False

    def cleanup(self):
        try:
            self.set_lamp(False)
            bus.close()
            logger.info("Service beendet")
        except:
            pass

    def signal_handler(self, sig, frame):
        logger.info("Beende Service...")
        self.running = False
        self.cleanup()
        sys.exit(0)

    def run(self):
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("Fitlet3 Status-Schalter Service (Simplified) gestartet")
        
        if not self.init_gpio():
            sys.exit(1)
        
        logger.info("Service aktiv - Reagiert auf Schalter-Änderungen")
        logger.info("NC Schalter: Nicht gedrückt = EIN, Gedrückt = AUS")
        
        try:
            while self.running:
                current_switch_state = self.read_switch()
                
                # Bei erster Lesung oder Änderung reagieren
                if current_switch_state != self.last_switch_state:
                    if self.last_switch_state is None:
                        # Erste Lesung - Lampe synchronisieren
                        logger.info(f"Erste Schalter-Lesung: {'EIN' if current_switch_state else 'AUS'}")
                    else:
                        # Änderung erkannt
                        logger.info(f"Schalter geändert: {'EIN' if current_switch_state else 'AUS'}")
                    
                    self.set_lamp(current_switch_state)
                    self.last_switch_state = current_switch_state
                
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Fehler: {e}")
            self.cleanup()
            sys.exit(1)

if __name__ == "__main__":
    switch_service = StatusSwitchSimple()
    switch_service.run()
EOF

    chmod +x /usr/local/bin/fitlet3-status-switch.py
}

create_service_efi() {
    print_info "Erstelle EFI-kompatiblen Systemd Service..."
    
    cat > /etc/systemd/system/fitlet3-status-switch.service << 'EOF'
[Unit]
Description=Fitlet3 Status Switch Service (EFI)
After=multi-user.target fitlet3-i2c-init.service
Wants=fitlet3-i2c-init.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/fitlet3-status-switch.py
Restart=always
RestartSec=10
User=root

# EFI-spezifische Einstellungen
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
}

enable_service_efi() {
    print_info "Aktiviere EFI Services..."
    
    systemctl daemon-reload
    systemctl enable fitlet3-i2c-init.service
    systemctl enable fitlet3-status-switch.service
    
    # Starte I2C Init Service
    systemctl start fitlet3-i2c-init.service
    sleep 2
    
    # Starte Main Service
    systemctl start fitlet3-status-switch.service
    sleep 2
    
    if systemctl is-active --quiet fitlet3-status-switch.service; then
        print_success "EFI Services erfolgreich gestartet!"
    else
        print_error "Service konnte nicht gestartet werden"
        systemctl status fitlet3-status-switch.service
    fi
}

show_efi_info() {
    print_success "EFI Installation abgeschlossen!"
    echo ""
    print_info "EFI Boot System erkannt:"
    echo "  Boot-Typ: $BOOT_TYPE"
    echo "  Boot-Config: ${BOOT_CONFIG:-'Nicht gefunden'}"
    echo "  Cmdline: ${CMDLINE_FILE:-'Nicht gefunden'}"
    echo ""
    print_info "Services:"
    echo "  fitlet3-i2c-init.service     - I2C Initialisierung"
    echo "  fitlet3-status-switch.service - Hauptservice"
    echo ""
    print_info "Befehle:"
    echo "  systemctl status fitlet3-status-switch.service"
    echo "  journalctl -u fitlet3-status-switch.service -f"
    echo ""
    
    if [ -n "$BOOT_CONFIG" ] || [ -n "$CMDLINE_FILE" ]; then
        print_warning "Neustart empfohlen für vollständige I2C Aktivierung"
    fi
}

main() {
    echo "Fitlet3 Status Switch Installation - EFI Boot Version"
    echo "===================================================="
    
    check_root
    detect_boot_system
    install_dependencies
    enable_i2c_efi
    enable_i2c_systemd
    
    if test_i2c_efi; then
        create_python_script_efi
        create_service_efi
        enable_service_efi
        show_efi_info
    else
        print_error "I2C Test fehlgeschlagen - Installation abgebrochen"
        print_info "Versuchen Sie einen Neustart und führen Sie das Script erneut aus"
        exit 1
    fi
}

main "$@"

