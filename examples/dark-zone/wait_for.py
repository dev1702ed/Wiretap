"""Wait until Postgres, Kafka and the Marquez API answer. No DCP code."""

import os
import socket
import sys
import time
import urllib.request

DEADLINE_S = 300


def wait(name, check):
    deadline = time.monotonic() + DEADLINE_S
    while True:
        try:
            check()
            print(f"{name} is up", flush=True)
            return
        except OSError as exc:
            if time.monotonic() > deadline:
                sys.exit(f"{name} did not come up within {DEADLINE_S} s: {exc}")
            time.sleep(2)


def tcp(host, port):
    return lambda: socket.create_connection((host, int(port)), timeout=3).close()


def http(url):
    def check():
        with urllib.request.urlopen(url, timeout=5):
            return

    return check


kafka_host, kafka_port = os.environ["KAFKA_BOOTSTRAP"].split(":")
wait("Postgres", tcp(os.environ["PGHOST"], os.environ.get("PGPORT", "5432")))
wait("Kafka", tcp(kafka_host, kafka_port))
wait("Marquez API", http(os.environ["MARQUEZ_URL"] + "/api/v1/namespaces"))
