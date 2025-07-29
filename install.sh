#!/bin/bash

# Fitlet3 Status Switch Installation Script
# Usage: bash -c "$(wget -qLO - https://raw.githubusercontent.com/yourusername/fitlet3-status-switch/main/install.sh)"

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "Bitte nicht als root ausführen. Das Script wird sudo verwenden wenn nötig."
        exit 1
    fi
}

# Check system requirements
check_requirements() {
    print_info "Überprüfe Systemanforderungen..."
    
    # Check if we're on a Debian/Ubuntu system
    if ! command -v apt &> /dev/null; then
        print_error "Dieses Script ist für Debian/Ubuntu Systeme gedacht."
        exit 1
    fi
    
    # Check if I2C is available
    if ! ls /dev/i2c* &> /dev/null; then
        print_warning "I2C Interface nicht gefunden. Wird aktiviert..."
        enable_i2c
    fi
    
    print_success "Systemanforderungen erfüllt"
}

# Enable I2C
enable_i2c() {
    print_info "Aktiviere I2C Interface..."
    
    # Add I2C to modules
    if ! grep -q "i2c-dev" /etc/modules; then
        echo "i2c-dev" | sudo tee -a /etc/modules > /dev/null
    fi
    
    # Enable I2C in config
    if [ -f /boot/config.txt ]; then
        if ! grep -q "dtparam=i2c_arm=on" /boot/config.txt; then
            echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt > /dev/null
        fi
    fi
    
    # Load I2C module
    sudo modprobe i2c-dev 2>/dev/null || true
    
    print_success "I2C Interface aktiviert"
}

# Install dependencies
install_dependencies() {
    print_info "Installiere Abhängigkeiten..."
    
    sudo apt update
    sudo apt install -y python3 python3-smbus i2c-tools
    
    print_success "Abhängigkeiten installiert"
}

# Create Python script
create_python_script() {
    print_info "Erstelle Python Script..."
    
    sudo tee /usr/local/bin/fitlet3-status-switch.py > /dev/null << 'EOF'
#!/usr/bin/env python3
"""
Fitlet3 Status Switch Service
Überwacht einen Schalter an GPI0 und steuert eine Lampe an GPO0
"""

import smbus
import time
import signal
import sys
import logging
from datetime import datetime

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# I2C Setup
bus = smbus.SMBus(1)
PCA9555_ADDR = 0x20

INPUT_PORT_1 = 0x01
OUTPUT_PORT_1 = 0x03
CONFIG_PORT_1 = 0x07

class StatusSwitch:
    def __init__(self):
        self.running = True
        self.last_switch_state = None
        
    def init_gpio(self):
        """GPIO konfigurieren"""
        try:
            config = bus.read_byte_data(PCA9555_ADDR, CONFIG_PORT_1)
            config |= 0x80   # Bit 7 = Input (Schalter)
            config &= ~0x20  # Bit 5 = Output (Lampe)
            bus.write_byte_data(PCA9555_ADDR, CONFIG_PORT_1, config)
            logger.info("GPIO erfolgreich initialisiert")
            return True
        except Exception as e:
            logger.error(f"GPIO Initialisierung fehlgeschlagen: {e}")
            return False

    def read_switch(self):
        """Schalter-Status lesen"""
        try:
            data = bus.read_byte_data(PCA9555_ADDR, INPUT_PORT_1)
            return not bool(data & 0x80)  # Invertiert (Pull-up)
        except Exception as e:
            logger.error(f"Fehler beim Lesen des Schalters: {e}")
            return False

    def set_lamp(self, state):
        """Lampe ein/aus"""
        try:
            data = bus.read_byte_data(PCA9555_ADDR, OUTPUT_PORT_1)
            if state:
                data |= 0x20   # Lampe EIN
            else:
                data &= ~0x20  # Lampe AUS
            bus.write_byte_data(PCA9555_ADDR, OUTPUT_PORT_1, data)
            return True
        except Exception as e:
            logger.error(f"Fehler beim Setzen der Lampe: {e}")
            return False

    def cleanup(self):
        """Aufräumen beim Beenden"""
        try:
            self.set_lamp(False)  # Lampe ausschalten
            logger.info("Lampe ausgeschaltet - Service beendet")
        except:
            pass

    def signal_handler(self, sig, frame):
        """Signal Handler für sauberes Beenden"""
        logger.info("Beende Service...")
        self.running = False
        self.cleanup()
        sys.exit(0)

    def run(self):
        """Hauptschleife"""
        # Signal Handler registrieren
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("Fitlet3 Status-Schalter Service gestartet")
        
        # GPIO initialisieren
        if not self.init_gpio():
            logger.error("GPIO konnte nicht initialisiert werden")
            sys.exit(1)
        
        # Lampe initial ausschalten
        self.set_lamp(False)
        logger.info("Service aktiv - Schalter EIN = Lampe EIN")
        
        try:
            while self.running:
                switch_state = self.read_switch()
                
                # Nur bei Statusänderung reagieren und loggen
                if switch_state != self.last_switch_state:
                    status_text = "EIN" if switch_state else "AUS"
                    logger.info(f"Schalter: {status_text} -> Lampe: {status_text}")
                    self.set_lamp(switch_state)
                    self.last_switch_state = switch_state
                
                time.sleep(0.1)  # 100ms Polling
                
        except Exception as e:
            logger.error(f"Unerwarteter Fehler: {e}")
            self.cleanup()
            sys.exit(1)

if __name__ == "__main__":
    switch_service = StatusSwitch()
    switch_service.run()
EOF

    # Make script executable
    sudo chmod +x /usr/local/bin/fitlet3-status-switch.py
    
    print_success "Python Script erstellt"
}

# Create systemd service
create_service() {
    print_info "Erstelle Systemd Service..."
    
    sudo tee /etc/systemd/system/fitlet3-status-switch.service > /dev/null << 'EOF'
[Unit]
Description=Fitlet3 Status Switch Service
Documentation=https://github.com/yourusername/fitlet3-status-switch
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/fitlet3-status-switch.py
Restart=always
RestartSec=5
User=root
Group=root

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=fitlet3-status-switch

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/dev/i2c-1

[Install]
WantedBy=multi-user.target
EOF

    print_success "Systemd Service erstellt"
}

# Enable and start service
enable_service() {
    print_info "Aktiviere und starte Service..."
    
    sudo systemctl daemon-reload
    sudo systemctl enable fitlet3-status-switch.service
    sudo systemctl start fitlet3-status-switch.service
    
    # Wait a moment and check status
    sleep 2
    
    if sudo systemctl is-active --quiet fitlet3-status-switch.service; then
        print_success "Service erfolgreich gestartet"
    else
        print_error "Service konnte nicht gestartet werden"
        print_info "Status prüfen mit: sudo systemctl status fitlet3-status-switch.service"
        return 1
    fi
}

# Create management script
create_management_script() {
    print_info "Erstelle Management Script..."
    
    sudo tee /usr/local/bin/fitlet3-switch > /dev/null << 'EOF'
#!/bin/bash

# Fitlet3 Status Switch Management Script

case "$1" in
    start)
        echo "Starte Fitlet3 Status Switch Service..."
        sudo systemctl start fitlet3-status-switch.service
        ;;
    stop)
        echo "Stoppe Fitlet3 Status Switch Service..."
        sudo systemctl stop fitlet3-status-switch.service
        ;;
    restart)
        echo "Starte Fitlet3 Status Switch Service neu..."
        sudo systemctl restart fitlet3-status-switch.service
        ;;
    status)
        sudo systemctl status fitlet3-status-switch.service
        ;;
    logs)
        sudo journalctl -u fitlet3-status-switch.service -f
        ;;
    enable)
        echo "Aktiviere Autostart..."
        sudo systemctl enable fitlet3-status-switch.service
        ;;
    disable)
        echo "Deaktiviere Autostart..."
        sudo systemctl disable fitlet3-status-switch.service
        ;;
    test)
        echo "Teste I2C Verbindung..."
        i2cdetect -y 1
        ;;
    uninstall)
        echo "Deinstalliere Fitlet3 Status Switch..."
        sudo systemctl stop fitlet3-status-switch.service 2>/dev/null || true
        sudo systemctl disable fitlet3-status-switch.service 2>/dev/null || true
        sudo rm -f /etc/systemd/system/fitlet3-status-switch.service
        sudo rm -f /usr/local/bin/fitlet3-status-switch.py
        sudo rm -f /usr/local/bin/fitlet3-switch
        sudo systemctl daemon-reload
        echo "Deinstallation abgeschlossen"
        ;;
    *)
        echo "Fitlet3 Status Switch Management"
        echo "Verwendung: $0 {start|stop|restart|status|logs|enable|disable|test|uninstall}"
        echo ""
        echo "Befehle:"
        echo "  start     - Service starten"
        echo "  stop      - Service stoppen"
        echo "  restart   - Service neu starten"
        echo "  status    - Service Status anzeigen"
        echo "  logs      - Live Logs anzeigen"
        echo "  enable    - Autostart aktivieren"
        echo "  disable   - Autostart deaktivieren"
        echo "  test      - I2C Verbindung testen"
        echo "  uninstall - Komplett deinstallieren"
        exit 1
        ;;
esac
EOF

    sudo chmod +x /usr/local/bin/fitlet3-switch
    
    print_success "Management Script erstellt"
}

# Show final information
show_info() {
    print_success "Installation abgeschlossen!"
    echo ""
    print_info "Hardware-Anschluss:"
    echo "  Pin 1 (VCC)  - Externe Spannungsversorgung (12V/24V)"
    echo "  Pin 2 (GPO0) - Lampe (über Relais/Transistor)"
    echo "  Pin 4 (GPI0) - Schalter"
    echo "  Pin 10 (GND) - Masse"
    echo ""
    print_info "Verfügbare Befehle:"
    echo "  fitlet3-switch status   - Service Status"
    echo "  fitlet3-switch logs     - Live Logs"
    echo "  fitlet3-switch restart  - Service neu starten"
    echo "  fitlet3-switch test     - I2C testen"
    echo "  fitlet3-switch uninstall - Deinstallieren"
    echo ""
    print_info "Service Status:"
    sudo systemctl --no-pager status fitlet3-status-switch.service
    echo ""
    
    if [ -f /boot/config.txt ] && ! grep -q "dtparam=i2c_arm=on" /boot/config.txt; then
        print_warning "Möglicherweise ist ein Neustart erforderlich um I2C zu aktivieren"
    fi
}

# Main installation function
main() {
    echo "=================================="
    echo "Fitlet3 Status Switch Installation"
    echo "=================================="
    echo ""
    
    check_root
    check_requirements
    install_dependencies
    create_python_script
    create_service
    enable_service
    create_management_script
    show_info
}

# Run main function
main "$@"
