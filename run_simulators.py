import subprocess
import sys
import random
import time

BROKER = "localhost:1883"

locations = [
    ("Beograd", "SIM_BG_01", "beograd"),
    ("Nis", "SIM_NI_01", "nis"),
    ("Novi Sad", "SIM_NS_01", "novi_sad"),
    ("Kragujevac", "SIM_KG_01", "kragujevac"),
    ("Subotica", "SIM_SU_01", "subotica"),
    ("Cacak", "SIM_CA_01", "cacak"),
    ("Pristina", "SIM_PR_01", "pristina"),
    ("Novi Pazar", "SIM_NP_01", "novi_pazar"),
    ("Leskovac", "SIM_LE_01", "leskovac"),
    ("Zajecar", "SIM_ZA_01", "zajecar"),
]

processes = []

try:
    for i, (city, sensor_id, topic_city) in enumerate(locations):
        topic = f"radijacija/srbija/{topic_city}"

        print(f"Pokrecem simulator za {city} ({sensor_id})...")

        process = subprocess.Popen([
            sys.executable,
            "simulator.py",
            BROKER,
            sensor_id,
            topic
        ])

        processes.append(process)

        # Ako nije poslednji simulator, cekamo 1-5 sekundi
        if i < len(locations) - 1:
            delay = random.randint(1, 5)
            print(f"Cekam {delay} sekundi pre sledeceg simulatora...\n")
            time.sleep(delay)

    print("\n=== Svi simulatori su pokrenuti ===")
    print("Pritisni Ctrl+C za zaustavljanje svih simulatora.\n")

    # Cekamo da procesi zavrse
    for process in processes:
        process.wait()

except KeyboardInterrupt:
    print("\nZaustavljanje svih simulatora...")

    for process in processes:
        process.terminate()

    for process in processes:
        process.wait()

    print("Svi simulatori su zaustavljeni.")