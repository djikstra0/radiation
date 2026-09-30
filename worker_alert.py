import paho.mqtt.client as mqtt
import psycopg2
import json
import requests
from datetime import datetime, timezone, timedelta
from paho.mqtt.enums import CallbackAPIVersion

#########################################################
# HEARTBEAT
#########################################################

import threading
import time

HEARTBEAT_INTERVAL = 10


def heartbeat_loop(client):
    while True:
        message = {
            "worker": "worker_alert",
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        client.publish(
            "radijacija/system/heartbeat/alert",
            json.dumps(message),
            qos=1
        )

        time.sleep(HEARTBEAT_INTERVAL)


#########################################################
# DATABASE
#########################################################

DB_CONFIG = {
    "host": "localhost",
    "database": "postgres",
    "user": "postgres",
    "password": ""
}


#########################################################
# TELEGRAM
#########################################################

TELEGRAM_TOKEN = ""


def send_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text
        }
    )


#########################################################
# HELPERS
#########################################################

def extract_city(topic):
    return topic.split("/")[-1]


def should_alert(cur, user_id, city):
    """
    Proverava da li je korisniku dozvoljeno da se posalje
    novo upozorenje za datu lokaciju.

    Cooldown je 10 minuta po korisniku i lokaciji.
    """

    cur.execute(
        """
        SELECT last_alert
        FROM alerts
        WHERE user_id = %s AND city = %s
        """,
        (user_id, city)
    )

    row = cur.fetchone()

    now = datetime.now(timezone.utc)

    # Prvo upozorenje za ovog korisnika i ovu lokaciju
    if row is None:
        cur.execute(
            """
            INSERT INTO alerts (user_id, city, last_alert)
            VALUES (%s, %s, %s)
            """,
            (user_id, city, now)
        )

        return True

    last_alert = row[0]

    # Nikada nije poslato upozorenje
    if last_alert is None:
        cur.execute(
            """
            UPDATE alerts
            SET last_alert = %s
            WHERE user_id = %s AND city = %s
            """,
            (now, user_id, city)
        )

        return True

    # Proslo je vise od 10 minuta
    if now - last_alert > timedelta(minutes=10):
        cur.execute(
            """
            UPDATE alerts
            SET last_alert = %s
            WHERE user_id = %s AND city = %s
            """,
            (now, user_id, city)
        )

        return True

    return False


#########################################################
# MQTT MESSAGE
#########################################################

def on_message(client, userdata, message):

    # Ignorisi sistemske heartbeat poruke
    if message.topic.startswith("radijacija/system/"):
        return

    payload = json.loads(
        message.payload.decode("utf-8")
    )

    radiation_value = payload.get("value")

    if radiation_value is None:
        return

    # CPM -> uSv/h
    radiation_usv = float(radiation_value) / 154

    # npr. radijacija/srbija/nis -> nis
    city = extract_city(message.topic)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    #####################################################
    # PRONADJI KORISNIKE KOJI PRATE LOKACIJU
    # I PROVERI THRESHOLD ZA TU LOKACIJU
    #####################################################

    cur.execute(
        """
        SELECT
            u.id,
            u.chat_id,
            l.location_name,
            l.threshold
        FROM users u
        JOIN subscriptions s
            ON u.id = s.user_id
        JOIN locations l
            ON s.city = l.location_code
        WHERE s.city = %s
          AND l.threshold < %s
        """,
        (city, radiation_usv)
    )

    users = cur.fetchall()

    #####################################################
    # SLANJE OBAVESTENJA
    #####################################################

    for user_id, chat_id, location_name, threshold in users:

        if should_alert(cur, user_id, city):

            send_telegram(
                chat_id,
                f"OPASNOST! {radiation_usv:.4f} uSv/h "
                f"u {location_name.upper()}"
            )

    #####################################################
    # SACUVAJ PROMENE
    #####################################################

    conn.commit()

    cur.close()
    conn.close()


#########################################################
# MQTT CLIENT
#########################################################

client = mqtt.Client(
    CallbackAPIVersion.VERSION2
)

client.on_message = on_message


#########################################################
# HEARTBEAT THREAD
#########################################################

heartbeat_thread = threading.Thread(
    target=heartbeat_loop,
    args=(client,),
    daemon=True
)

heartbeat_thread.start()


#########################################################
# START
#########################################################

print("Alert worker pokrenut...")

try:

    # Paho ce koristiti isti interval izmedju reconnect pokusaja
    client.reconnect_delay_set(
        min_delay=5,
        max_delay=5
    )

    while True:

        try:
            print("Pokusaj povezivanja sa MQTT Brokerom...")

            client.connect("localhost", 1883)

            client.subscribe(
                "radijacija/srbija/#"
            )

            print("Povezan na MQTT Broker!")
            print("Pretplacen na temu: radijacija/srbija/#")

            client.loop_forever()

            # Ako loop_forever zavrsi bez izuzetka,
            # pokusaj ponovo nakon 5 sekundi.
            print(
                "MQTT petlja zavrsena. "
                "Ponovni pokusaj za 5 sekundi..."
            )

            time.sleep(5)

        except (ConnectionRefusedError, OSError) as e:

            print(
                f"MQTT Broker nije dostupan: {e}"
            )

            print(
                "Ponovni pokusaj povezivanja za 5 sekundi..."
            )

            time.sleep(5)

except KeyboardInterrupt:

    print("\nZaustavljanje alert workera...")