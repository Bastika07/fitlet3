#!/usr/bin/env python3
"""
Intel TCO Watchdog Controller für Fitlet3
Nutzt den eingebauten Hardware-Watchdog des Intel Chipsets
"""

import os
import time
import signal
import sys
import logging
import subprocess
import threading
import smbus
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntelTCOWatchdog:
    """
    Intel TCO (Total Cost of Ownership) Watchdog Controller
    Nutzt den eingebauten Hardware-Watchdog des Intel Chipsets
    """
    
    def __init__(self, bus_num=2, pca_address=0x20):
        self.watchdog_device = "/dev/watchdog"
        self.watchdog_fd = None
        self.running = True
        
        # PCA9555 für Schalter-Integration
        self.bus = smbus.SMBus(bus_num)
        self.pca_addr = pca_address
        
        # Pin-Konfiguration für PCA9555
        self.SWITCH_PORT = 1
        self.SWITCH_PIN = 7           # Pin 1.7 - Reset-Schalter
        self.STATUS_LED_PORT = 1
        self.STATUS_LED_PIN = 2       # Pin 1.2 - Status-LED
        self.HEARTBEAT_PORT = 1
        self.HEARTBEAT_PIN = 3        # Pin 1.3 - Heartbeat-LED
        
        # Watchdog-Einstellungen
        self.timeout = 30             # 30 Sekunden Timeout
        self.heartbeat_interval = 10  # Alle 10 Sekunden füttern
        self.last_feed = time.time()
        
        # Schalter-Reset Einstellungen
        self.reset_hold_time = 5      # 5 Sekunden für manuellen Reset
        self.last_switch_state = None
        self.switch_press_start = None
        
        self.setup_hardware()
        self.setup_tco_watchdog()
    
    def setup_hardware(self):
        """PCA9555 Hardware-Pins konfigurieren"""
        try:
            logger.info("Konfiguriere PCA9555 für TCO Watchdog...")
            
            # Pin-Konfiguration
            config = self.bus.read_byte_data(self.pca_addr, 0x07)
            config |= (1 << self.SWITCH_PIN)      # Switch als Input
            config &= ~(1 << self.STATUS_LED_PIN) # Status-LED als Output
            config &= ~(1 << self.HEARTBEAT_PIN)  # Heartbeat-LED als Output
            self.bus.write_byte_data(self.pca_addr, 0x07, config)
            
            # Initial-Werte
            output = self.bus.read_byte_data(self.pca_addr, 0x03)
            output |= (1 << self.STATUS_LED_PIN)   # Status-LED EIN
            output &= ~(1 << self.HEARTBEAT_PIN)   # Heartbeat-LED AUS
            self.bus.write_byte_data(self.pca_addr, 0x03, output)
            
            logger.info("PCA9555 Hardware-Setup abgeschlossen")
            
        except Exception as e:
            logger.error(f"PCA9555 Setup fehlgeschlagen: {e}")
            # Weiter ohne PCA9555
    
    def setup_tco_watchdog(self):
        """Intel TCO Watchdog initialisieren"""
        try:
            logger.info("Initialisiere Intel TCO Watchdog...")
            
            # Prüfen ob iTCO_wdt Modul geladen ist
            self.check_tco_module()
            
            # Watchdog-Device öffnen
            if not os.path.exists(self.watchdog_device):
                logger.error(f"Watchdog-Device {self.watchdog_device} nicht gefunden!")
                raise FileNotFoundError(f"Watchdog-Device nicht verfügbar")
            
            # Watchdog öffnen (startet automatisch den Timer!)
            self.watchdog_fd = os.open(self.watchdog_device, os.O_WRONLY)
            logger.info(f"TCO Watchdog geöffnet: {self.watchdog_device}")
            
            # Timeout setzen
            self.set_timeout(self.timeout)
            
            # Initial füttern
            self.feed_watchdog()
            
            logger.info(f"Intel TCO Watchdog aktiv (Timeout: {self.timeout}s)")
            
        except Exception as e:
            logger.error(f"TCO Watchdog Setup fehlgeschlagen: {e}")
            raise
    
    def check_tco_module(self):
        """Prüfen und laden des iTCO_wdt Moduls"""
        try:
            # Prüfen ob Modul geladen ist
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            if 'iTCO_wdt' not in result.stdout:
                logger.info("iTCO_wdt Modul nicht geladen - versuche zu laden...")
                
                # Modul laden
                subprocess.run(['modprobe', 'iTCO_wdt'], check=True)
                logger.info("iTCO_wdt Modul erfolgreich geladen")
            else:
                logger.info("iTCO_wdt Modul bereits geladen")
            
            # Modul-Informationen anzeigen
            result = subprocess.run(['modinfo', 'iTCO_wdt'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'description:' in line.lower():
                        logger.info(f"TCO Modul: {line.strip()}")
                        break
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Konnte iTCO_wdt Modul nicht laden: {e}")
        except Exception as e:
            logger.warning(f"Modul-Check Fehler: {e}")
    
    def set_timeout(self, timeout_seconds):
        """Watchdog-Timeout setzen"""
        try:
            if self.watchdog_fd:
                # WDIOC_SETTIMEOUT ioctl verwenden
                import fcntl
                import struct
                
                # ioctl Konstanten
                WDIOC_SETTIMEOUT = 0xC0045706
                
                # Timeout setzen
                timeout_bytes = struct.pack('I', timeout_seconds)
                fcntl.ioctl(self.watchdog_fd, WDIOC_SETTIMEOUT, timeout_bytes)
                
                logger.info(f"Watchdog-Timeout auf {timeout_seconds}s gesetzt")
                
        except Exception as e:
            logger.warning(f"Konnte Timeout nicht setzen: {e}")
    
    def feed_watchdog(self):
        """Watchdog füttern (Keep-Alive)"""
        try:
            if self.watchdog_fd:
                # Beliebiges Byte schreiben = Watchdog füttern
                os.write(self.watchdog_fd, b'1')
                self.last_feed = time.time()
                logger.debug("TCO Watchdog gefüttert")
                return True
        except Exception as e:
            logger.error(f"Watchdog-Feed Fehler: {e}")
            return False
    
    def trigger_immediate_reset(self):
        """Sofortigen Reset über Watchdog auslösen"""
        logger.critical("=== SOFORTIGER TCO WATCHDOG RESET ===")
        
        try:
            if self.watchdog_fd:
                # Watchdog schließen ohne Magic Close
                # Das löst einen sofortigen Reset aus!
                logger.critical("Schließe Watchdog ohne Magic Close...")
                os.close(self.watchdog_fd)
                self.watchdog_fd = None
                
                # Warten auf Reset (sollte in wenigen Sekunden erfolgen)
                logger.critical("Warte auf Hardware-Reset...")
                time.sleep(10)
                
                # Falls wir hier ankommen, hat der Reset nicht funktioniert
                logger.error("TCO Watchdog Reset fehlgeschlagen!")
                
        except Exception as e:
            logger.error(f"TCO Reset Fehler: {e}")
    
    def stop_watchdog_safely(self):
        """Watchdog sicher stoppen (Magic Close)"""
        try:
            if self.watchdog_fd:
                # Magic Close: 'V' schreiben stoppt den Watchdog
                logger.info("Stoppe TCO Watchdog sicher...")
                os.write(self.watchdog_fd, b'V')
                os.close(self.watchdog_fd)
                self.watchdog_fd = None
                logger.info("TCO Watchdog sicher gestoppt")
                
        except Exception as e:
            logger.error(f"Watchdog-Stop Fehler: {e}")
    
    def read_switch(self):
        """Reset-Schalter lesen"""
        try:
            data = self.bus.read_byte_data(self.pca_addr, 0x01)
            return not bool(data & (1 << self.SWITCH_PIN))  # NC-Schalter invertiert
        except:
            return False
    
    def set_pin(self, port, pin, value):
        """PCA9555 Pin setzen"""
        try:
            reg = 0x02 if port == 0 else 0x03
            output = self.bus.read_byte_data(self.pca_addr, reg)
            
            if value:
                output |= (1 << pin)
            else:
                output &= ~(1 << pin)
            
            self.bus.write_byte_data(self.pca_addr, reg, output)
            
        except:
            pass  # Ignoriere PCA9555 Fehler
    
    def heartbeat_thread(self):
        """Heartbeat-Thread für LED und Watchdog-Feed"""
        heartbeat_state = False
        last_feed = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Heartbeat-LED blinken
                self.set_pin(self.HEARTBEAT_PORT, self.HEARTBEAT_PIN, heartbeat_state)
                heartbeat_state = not heartbeat_state
                
                # Watchdog regelmäßig füttern
                if current_time - last_feed >= self.heartbeat_interval:
                    if self.feed_watchdog():
                        last_feed = current_time
                        logger.debug(f"Watchdog gefüttert (nächstes Feed in {self.heartbeat_interval}s)")
                    else:
                        logger.error("Watchdog-Feed fehlgeschlagen!")
                
                time.sleep(1)  # 1 Sekunde Heartbeat
                
            except Exception as e:
                logger.error(f"Heartbeat-Thread Fehler: {e}")
                time.sleep(1)
    
    def switch_monitor_thread(self):
        """Schalter-Monitor für manuellen Reset"""
        logger.info("Schalter-Monitor gestartet")
        logger.info(f"Reset-Schalter {self.reset_hold_time}s halten für sofortigen Reset")
        
        while self.running:
            try:
                current_switch_state = self.read_switch()
                current_time = time.time()
                
                # Schalter-Zustandsänderung
                if current_switch_state != self.last_switch_state:
                    if current_switch_state:  # Schalter geschlossen
                        logger.warning("RESET-SCHALTER GEDRÜCKT!")
                        logger.warning(f"Halte {self.reset_hold_time}s für sofortigen TCO Reset...")
                        self.switch_press_start = current_time
                        
                        # Status-LED schnell blinken (Warnung)
                        for i in range(10):
                            self.set_pin(self.STATUS_LED_PORT, self.STATUS_LED_PIN, i % 2)
                            time.sleep(0.1)
                        
                    else:  # Schalter geöffnet
                        if self.switch_press_start:
                            hold_duration = current_time - self.switch_press_start
                            logger.info(f"Reset-Schalter losgelassen nach {hold_duration:.1f}s")
                            
                            if hold_duration < self.reset_hold_time:
                                logger.info("Reset abgebrochen (zu kurz gehalten)")
                                # Status-LED wieder normal
                                self.set_pin(self.STATUS_LED_PORT, self.STATUS_LED_PIN, True)
                        
                        self.switch_press_start = None
                    
                    self.last_switch_state = current_switch_state
                
                # Prüfen ob Schalter lange genug gehalten
                if (current_switch_state and 
                    self.switch_press_start and 
                    current_time - self.switch_press_start >= self.reset_hold_time):
                    
                    logger.critical(f"RESET-SCHALTER {self.reset_hold_time}s GEHALTEN!")
                    logger.critical("LÖSE SOFORTIGEN TCO WATCHDOG RESET AUS!")
                    
                    # Sofortigen Reset auslösen
                    self.trigger_immediate_reset()
                    
                    # Nach Reset sollten wir hier nicht mehr ankommen
                    break
                
                time.sleep(0.1)  # 100ms Polling
                
            except Exception as e:
                logger.error(f"Schalter-Monitor Fehler: {e}")
                time.sleep(1)
    
    def get_watchdog_info(self):
        """Watchdog-Informationen anzeigen"""
        try:
            info = {}
            
            # Kernel-Modul Info
            result = subprocess.run(['modinfo', 'iTCO_wdt'], capture_output=True, text=True)
            if result.returncode == 0:
                info['module'] = 'iTCO_wdt geladen'
            
            # Watchdog-Device Info
            if os.path.exists(self.watchdog_device):
                info['device'] = f"{self.watchdog_device} verfügbar"
            
            # Timeout Info (falls verfügbar)
            try:
                with open('/sys/class/watchdog/watchdog0/timeout', 'r') as f:
                    info['current_timeout'] = f"Aktueller Timeout: {f.read().strip()}s"
            except:
                pass
            
            # Timeleft Info (falls verfügbar)
            try:
                with open('/sys/class/watchdog/watchdog0/timeleft', 'r') as f:
                    info['timeleft'] = f"Verbleibende Zeit: {f.read().strip()}s"
            except:
                pass
            
            return info
            
        except Exception as e:
            logger.error(f"Watchdog-Info Fehler: {e}")
            return {}
    
    def cleanup(self):
        """Cleanup beim Beenden"""
        try:
            self.running = False
            
            # Watchdog sicher stoppen
            self.stop_watchdog_safely()
            
            # LEDs ausschalten
            self.set_pin(self.STATUS_LED_PORT, self.STATUS_LED_PIN, False)
            self.set_pin(self.HEARTBEAT_PORT, self.HEARTBEAT_PIN, False)
            
            # PCA9555 Bus schließen
            self.bus.close()
            
            logger.info("TCO Watchdog Cleanup abgeschlossen")
            
        except Exception as e:
            logger.error(f"Cleanup Fehler: {e}")
    
    def signal_handler(self, sig, frame):
        """Signal Handler für sauberes Beenden"""
        logger.info("Signal empfangen - beende TCO Watchdog...")
        self.cleanup()
        sys.exit(0)
    
    def run(self):
        """Hauptfunktion"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("=== INTEL TCO WATCHDOG CONTROLLER ===")
        
        # Watchdog-Informationen anzeigen
        info = self.get_watchdog_info()
        for key, value in info.items():
            logger.info(f"{key}: {value}")
        
        logger.info(f"Watchdog-Timeout: {self.timeout}s")
        logger.info(f"Feed-Intervall: {self.heartbeat_interval}s")
        logger.info("Heartbeat-LED sollte blinken")
        logger.info("Status-LED sollte leuchten")
        logger.info(f"Reset-Schalter {self.reset_hold_time}s halten für sofortigen Reset")
        
        try:
            # Threads starten
            heartbeat_thread = threading.Thread(target=self.heartbeat_thread)
            heartbeat_thread.daemon = True
            heartbeat_thread.start()
            
            switch_thread = threading.Thread(target=self.switch_monitor_thread)
            switch_thread.daemon = True
            switch_thread.start()
            
            logger.info("Intel TCO Watchdog aktiv")
            logger.info("System wird überwacht...")
            
            # Haupt-Loop
            while self.running:
                time.sleep(5)
                
                # Watchdog-Status prüfen
                time_since_feed = time.time() - self.last_feed
                if time_since_feed > self.heartbeat_interval * 2:
                    logger.warning(f"Watchdog nicht gefüttert seit {time_since_feed:.1f}s!")
                
        except Exception as e:
            logger.error(f"Hauptschleife Fehler: {e}")
        finally:
            self.cleanup()

def main():
    """Hauptfunktion"""
    print("Intel TCO Watchdog Controller für Fitlet3")
    print("=========================================")
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "info":
            # Nur Informationen anzeigen
            print("\n=== WATCHDOG INFORMATIONEN ===")
            
            # Modul-Status
            result = subprocess.run(['lsmod'], capture_output=True, text=True)
            if 'iTCO_wdt' in result.stdout:
                print("✓ iTCO_wdt Modul geladen")
            else:
                print("✗ iTCO_wdt Modul nicht geladen")
            
            # Device-Status
            if os.path.exists("/dev/watchdog"):
                print("✓ /dev/watchdog verfügbar")
            else:
                print("✗ /dev/watchdog nicht verfügbar")
            
            # Kernel-Logs
            try:
                result = subprocess.run(['dmesg', '|', 'grep', '-i', 'tco'], 
                                      shell=True, capture_output=True, text=True)
                if result.stdout:
                    print("\nKernel-Logs (TCO):")
                    for line in result.stdout.split('\n')[-5:]:
                        if line.strip():
                            print(f"  {line}")
            except:
                pass
            
            return
        
        elif sys.argv[1] == "reset":
            # Sofortiger Reset
            print("SOFORTIGER TCO WATCHDOG RESET!")
            input("Enter drücken zum Fortfahren...")
            
            controller = IntelTCOWatchdog()
            controller.trigger_immediate_reset()
            return
    
    try:
        controller = IntelTCOWatchdog()
        controller.run()
        
    except KeyboardInterrupt:
        print("\nBeendet durch Benutzer")
    except Exception as e:
        print(f"Fehler: {e}")
        print("\nTipp: 'python3 tco-watchdog.py info' für Diagnose")

if __name__ == "__main__":
    main()
