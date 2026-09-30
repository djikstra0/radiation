import sys
import time
import random
import json
from datetime import datetime
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

def generate_radiation_value():
    chance = random.random()

    # 80% vrednosti: normalan opseg
    if chance < 0.80:
        return random.randint(15, 60)

    # 17% vrednosti: umereno povisena radijacija
    elif chance < 0.97:
        return random.randint(61, 150)

    # 3% vrednosti: visoka radijacija
    else:
        return random.randint(151, 250)

class RadiationSimulator:
    def __init__(self, broker_url, client_id, topic):
        self.broker_url = broker_url.replace("tcp://", "") # Čistimo URL ako se prosledi sa tcp://
        if ":" in self.broker_url:
            self.host, self.port = self.broker_url.split(":")
            self.port = int(self.port)
        else:
            self.host = self.broker_url
            self.port = 1883

        self.client_id = client_id
        self.topic = topic
        
        # Inicijalizacija MQTT klijenta
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id)

    def run(self):
        try:
            print(f"[{self.client_id}] Povezivanje na: {self.host}:{self.port}...")
            self.client.connect(self.host, self.port, keepalive=20)
            
            # Pokrećemo pozadinsku petlju za MQTT mrežu
            self.client.loop_start()
            print(f"[{self.client_id}] Povezano! Saljem na temu: {self.topic}")

            while True:
                # Generišemo nasumičnu vrednost radijacije u CPM
                cpm_value = generate_radiation_value()
                
                # Format vremena: YYYY-MM-DD HH:MM:SS
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                payload = {
                    "sensor_id": self.client_id,
                    "value": cpm_value,
                    "timestamp": timestamp
                }

                # Pretvaramo u JSON string
                json_payload = json.dumps(payload, indent=2)

                # Slanje sa QoS 1 (Garantovana isporuka)
                self.client.publish(self.topic, json_payload, qos=1)

                print(f"\n[{self.client_id}] Poslat paket na temu [{self.topic}]:\n{json_payload}")
                
                # Pauza od 60 sekundi
                time.sleep(60)

        except KeyboardInterrupt:
            print(f"\n[{self.client_id}] Zaustavljanje simulatora...")
        except Exception as e:
            print(f"Kriticna greska kod simulatora {self.client_id}: {e}")
        finally:
            self.client.loop_stop()
            self.client.disconnect()

if __name__ == "__main__":
    # Upotreba: python simulator.py <broker_url> <client_id> <topic>
    if len(sys.argv) == 4:
        addr = sys.argv[1]
        s_id = sys.argv[2]
        top  = sys.argv[3]
        
        sim = RadiationSimulator(addr, s_id, top)
        sim.run()
    else:
        print("=== Koriscenje simulatora ===")
        print("Format: python simulator.py <broker_url> <client_id> <topic>")
        print("Primer za Niš:      python simulator.py localhost:1883 SIM_NI_01 radijacija/srbija/nis")
        print("Primer za Novi Sad: python simulator.py localhost:1883 SIM_NS_01 radijacija/srbija/novi_sad\n")
        
        print("Pokrecem podrazumevanu instancu (Beograd)...")
        sim = RadiationSimulator("localhost:1883", "SIM_BG_01", "radijacija/srbija/beograd")
        sim.run()