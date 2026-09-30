import subprocess
import time
import json
import os
import signal
from datetime import datetime

import paho.mqtt.client as mqtt


BROKER = "localhost"
PORT = 1883

HEARTBEAT_TIMEOUT = 30
CHECK_INTERVAL = 5

WORKERS = {
    "worker": {
        "script": "worker.py",
        "topic": "radijacija/system/heartbeat/worker"
    },
    "worker_alert": {
        "script": "worker_alert.py",
        "topic": "radijacija/system/heartbeat/alert"
    }
}

processes = {}
last_heartbeat = {}


def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def start_worker(name):
    script = WORKERS[name]["script"]

    process = subprocess.Popen(
        ["python", script]
    )

    processes[name] = process
    last_heartbeat[name] = time.time()

    print(
        f"[WATCHDOG] [{current_time()}] "
        f"Process {name} pokrenut"
    )


def stop_worker(name):
    process = processes.get(name)

    if process is not None and process.poll() is None:

        print(
            f"[WATCHDOG] [{current_time()}] "
            f"Stopping process {name}"
        )

        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def restart_worker(name):

    print(
        f"[WATCHDOG] [{current_time()}] "
        f"Restarting process {name}"
    )

    stop_worker(name)

    time.sleep(2)

    start_worker(name)


def on_connect(client, userdata, flags, rc):
    print(
        f"[WATCHDOG] [{current_time()}] "
        f"Connected to MQTT"
    )

    for worker in WORKERS.values():
        client.subscribe(worker["topic"], qos=1)


def on_message(client, userdata, msg):

    try:
        data = json.loads(msg.payload.decode())

        worker_name = data["worker"]

        if worker_name in WORKERS:

            last_heartbeat[worker_name] = time.time()

            print(
                f"[WATCHDOG] [{current_time()}] "
                f"Heartbeat received from {worker_name}"
            )

    except Exception as e:

        print(
            f"[WATCHDOG] [{current_time()}] "
            f"Invalid heartbeat: {e}"
        )


def monitor_workers():

    while True:

        now = time.time()

        for name in WORKERS:

            process = processes.get(name)

            # 1. Provera da li je proces pao
            if process is not None and process.poll() is not None:

                print(
                    f"[WATCHDOG] [{current_time()}] "
                    f"{name} process exited "
                    f"with code {process.returncode}"
                )

                restart_worker(name)

                continue

            # 2. Provera heartbeat-a
            last = last_heartbeat.get(name, 0)

            if now - last > HEARTBEAT_TIMEOUT:

                print(
                    f"[WATCHDOG] [{current_time()}] "
                    f"No heartbeat from {name} "
                    f"for {now - last:.1f}s"
                )

                restart_worker(name)

        time.sleep(CHECK_INTERVAL)


def main():

    client = mqtt.Client(
        client_id="radiation_watchdog"
    )

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT)

    client.loop_start()

    # Pokreni workere
    for name in WORKERS:
        start_worker(name)

    try:

        monitor_workers()

    except KeyboardInterrupt:

        print(
            f"[WATCHDOG] [{current_time()}] "
            f"Shutting down..."
        )

        for name in WORKERS:
            stop_worker(name)

        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
