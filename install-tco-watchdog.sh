#!/bin/bash
# Intel TCO Watchdog Installation für Fitlet3

echo "=== Intel TCO Watchdog Installation ==="

# 1. iTCO_wdt Modul laden
echo "Lade iTCO_wdt Modul..."
modprobe iTCO_wdt
if [ $? -eq 0 ]; then
    echo "✓ iTCO_wdt Modul geladen"
else
    echo "✗ Fehler beim Laden des iTCO_wdt Moduls"
fi

# 2. Modul beim Boot laden
echo "Konfiguriere Modul für automatisches Laden..."
echo "iTCO_wdt" >> /etc/modules
echo "✓ iTCO_wdt zu /etc/modules hinzugefügt"

# 3. Watchdog-Device prüfen
if [ -e "/dev/watchdog" ]; then
    echo "✓ /dev/watchdog verfügbar"
    ls -l /dev/watchdog
else
    echo "✗ /dev/watchdog nicht verfügbar"
fi

# 4. Script installieren
echo "Installiere TCO Watchdog Script..."
cp tco-watchdog.py /usr/local/bin/
chmod +x /usr/local/bin/tco-watchdog.py
echo "✓ Script nach /usr/local/bin/ kopiert"

# 5. Service installieren
echo "Installiere Systemd Service..."
cp tco-watchdog.service /etc/systemd/system/
systemctl daemon-reload
echo "✓ Service installiert"

# 6. Service aktivieren (optional)
read -p "Service automatisch starten? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl enable tco-watchdog.service
    systemctl start tco-watchdog.service
    echo "✓ Service aktiviert und gestartet"
else
    echo "Service nicht aktiviert (manuell mit 'systemctl start tco-watchdog.service')"
fi

echo ""
echo "=== Installation abgeschlossen ==="
echo "Test: python3 /usr/local/bin/tco-watchdog.py info"
echo "Start: systemctl start tco-watchdog.service"
echo "Status: systemctl status tco-watchdog.service"
