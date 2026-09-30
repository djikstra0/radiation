import paho.mqtt.client as mqtt
import psycopg2
import json
import os
import csv
from datetime import datetime, timezone
from paho.mqtt.enums import CallbackAPIVersion
import threading
import time

# ================== Konfiguracija CSV backupa ==================
BACKUP_DIR = r"./Backup_data"
current_csv_date = None
current_csv_file = None
current_csv_writer = None
# ===============================================================

# Konfiguracija baze
DB_CONFIG = {
    "host": "localhost",
    "database": "postgres",
    "user": "postgres",
    "password": ""
}

# Globalne varijable za bazu podataka
conn = None
cur = None

#########################################################

HEARTBEAT_INTERVAL = 10


def heartbeat_loop(client):
    while True:
        message = {
            "worker": "worker",
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        client.publish(
            "radijacija/system/heartbeat/worker",
            json.dumps(message),
            qos=1
        )

        time.sleep(HEARTBEAT_INTERVAL)


#########################################################


def init_db():
    """Inicijalizacija trajne konekcije sa TimescaleDB-om"""
    global conn, cur

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("Uspesno uspostavljena trajna konekcija sa TimescaleDB.")

    except Exception as e:
        print(f"Kriticna greska: Nemoguce se povezati na bazu: {e}")
        exit(1)


# ================== CSV funkcija ==================

def write_to_csv(
    measurement_time,
    sensor_id,
    radiation_value,
    radiation_usv,
    location
):
    global current_csv_date, current_csv_file, current_csv_writer

    try:
        # Parsiranje vremena (string -> datetime)
        dt = datetime.strptime(
            measurement_time,
            "%Y-%m-%d %H:%M:%S"
        )

        file_date = dt.strftime("%d-%b-%Y")

        # Ako je novi dan -> zatvori stari fajl i napravi novi
        if current_csv_date != file_date:

            if current_csv_file:
                current_csv_file.close()

            current_csv_date = file_date

            filename = os.path.join(
                BACKUP_DIR,
                f"{file_date}.csv"
            )

            file_exists = os.path.isfile(filename)

            current_csv_file = open(
                filename,
                mode='a',
                newline='',
                encoding='utf-8'
            )

            current_csv_writer = csv.writer(current_csv_file)

            # Ako fajl ne postoji -> upisi header
            if not file_exists:
                current_csv_writer.writerow([
                    "time",
                    "sensor_id",
                    "radiation_level",
                    "radiation_usv",
                    "location"
                ])

            print(f"CSV backup aktivan: {filename}")

        # Upis reda
        current_csv_writer.writerow([
            measurement_time,
            sensor_id,
            radiation_value,
            radiation_usv,
            location
        ])

        current_csv_file.flush()

    except Exception as e:
        print(f"Greska pri upisu u CSV: {e}")


# =======================================================


def on_connect(client, userdata, flags, rc, properties=None):
    print("Povezan na MQTT Broker!")

    client.subscribe("radijacija/srbija/#")

    print("Pretplacen na temu: radijacija/srbija/#")


def on_message(client, userdata, message):
    global conn, cur

    # Ignorisi sistemske heartbeat poruke
    if message.topic.startswith("radijacija/system/"):
        return

    try:
        payload = json.loads(
            message.payload.decode("utf-8")
        )

        print(
            f"Primljeno: {payload} sa teme {message.topic}"
        )

        sensor_id = payload.get('sensor_id')
        radiation_value = payload.get('value')

        if radiation_value is not None:
            radiation_usv = round(
                float(radiation_value) / 154,
                4
            )
        else:
            radiation_usv = 0.0

        measurement_time = payload.get('timestamp')

        if not measurement_time or measurement_time == "N/A":
            measurement_time = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            print(
                "Upozorenje: ESP32 poslao nevalidno vreme. "
                "Korisceno trenutno vreme servera."
            )

        if conn.closed or cur.closed:
            print(
                "Konekcija ka bazi je prekinuta. "
                "Ponovno povezivanje..."
            )

            init_db()

        query = """
            INSERT INTO radiation_data
                (time, sensor_id, radiation_level, radiation_usv, location)
            VALUES
                (%s, %s, %s, %s, %s)
            ON CONFLICT (time, sensor_id) DO NOTHING;
        """

        city_name = message.topic.rsplit("/", 1)[-1]
        city_name = city_name.replace("_", " ").title()

        cur.execute(
            query,
            (
                measurement_time,
                sensor_id,
                radiation_value,
                radiation_usv,
                city_name
            )
        )

        conn.commit()

        # ================== CSV backup ==================

        write_to_csv(
            measurement_time,
            sensor_id,
            radiation_value,
            radiation_usv,
            city_name
        )

        # =================================================

        print(
            f"Uspesno upisano: {radiation_value} CPM "
            f"i {radiation_usv} uSv/h za senzor {sensor_id}"
        )

    except json.JSONDecodeError:
        print(
            "Greska: Primljena poruka nije u validnom "
            f"JSON formatu: {message.payload}"
        )

    except Exception as e:
        print(
            f"Greska pri obradi poruke ili upisu u bazu: {e}"
        )

        if conn:
            conn.rollback()


# ================== Pokretanje ==================

init_db()

worker = mqtt.Client(
    CallbackAPIVersion.VERSION2,
    "Python_Worker_Service"
)

worker.on_connect = on_connect
worker.on_message = on_message

# Paho ce cekati 5 sekundi izmedju pokusaja reconnect-a
worker.reconnect_delay_set(
    min_delay=5,
    max_delay=5
)

###########################

# Pokretanje heartbeat threada
heartbeat_thread = threading.Thread(
    target=heartbeat_loop,
    args=(worker,),
    daemon=True
)

heartbeat_thread.start()

###########################

print("Worker pokrenut, pokretanje petlje...")

try:
    worker.reconnect_delay_set(
        min_delay=5,
        max_delay=5
    )

    while True:
        try:
            print("Pokusaj povezivanja sa MQTT Brokerom...")

            worker.connect("localhost", 1883)

            print("Uspesno povezivanje sa MQTT Brokerom.")

            worker.loop_forever()

            # Ako loop_forever zavrsi bez izuzetka,
            # pokusaj ponovno povezivanje nakon 5 sekundi.
            print("MQTT petlja zavrsena. Ponovni pokusaj za 5 sekundi...")
            time.sleep(5)

        except (ConnectionRefusedError, OSError) as e:
            print(f"MQTT Broker nije dostupan: {e}")
            print("Ponovni pokusaj povezivanja za 5 sekundi...")
            time.sleep(5)

except KeyboardInterrupt:
    print("\nZaustavljanje workera...")

finally:
    if cur:
        cur.close()

    if conn:
        conn.close()

    if current_csv_file:
        current_csv_file.close()

    print("Konekcije ka bazi zatvorene!")