"""The OpenLineage baseline, measured: what reaches a lineage server with no code changes. P5.

Adversarial cases 1 and 2 claim that OpenLineage sees nothing of a plain
script or notebook using psycopg and confluent-kafka, because no integration
exists for them (BASELINE.md audits the integrations at OpenLineage 1.53.0).
This checks it empirically:

1. a stub HTTP server counts every request it receives, on any path;
2. dark_zone's generated scripts and the notebook workload's notebook (the same
   programs the live harness runs) run WITHOUT dcp-instrument, with
   openlineage-python installed and OPENLINEAGE_URL pointing at the stub;
3. positive control: manual_emission.py, the declared-lineage path, runs with
   the same OPENLINEAGE_URL and must deliver its two events. Without it, a
   count of 0 could just mean a broken stub.

The count is reported as measured, whatever it is.
"""

import importlib.metadata
import json
import pathlib
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from harness import load
from live import generate, run_live

ADVERSARIAL = pathlib.Path(__file__).resolve().parent
MANUAL = ADVERSARIAL / "manual_emission.py"
WORKLOADS = ("dark_zone", "notebook")
SETTLE_S = 2.0  # an async transport would still be sending after exit; wait for it


class Stub:
    """Counts requests. Answers 200 to anything, as a lineage API would."""

    def __init__(self):
        self.requests: list[dict] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _record(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                try:
                    event_type = json.loads(body).get("eventType")
                except (ValueError, AttributeError):
                    event_type = None
                stub.requests.append(
                    {"method": self.command, "path": self.path, "eventType": event_type}
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_PUT = do_GET = _record

            def log_message(self, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _env(url: str) -> dict:
    env = run_live.clean_env()
    env["OPENLINEAGE_URL"] = url
    return env


def run(out_dir: pathlib.Path) -> dict:
    """Run the check. Raises run_live.LiveUnavailable without the services."""
    reason = run_live.unavailable()
    if reason:
        raise run_live.LiveUnavailable(reason)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    stub = Stub()
    try:
        programs = []
        for name in WORKLOADS:
            key = load(name)
            run_dir = out_dir / name
            run_dir.mkdir(parents=True, exist_ok=True)
            run_live.seed()
            for index, process in enumerate(key["processes"]):
                group = generate.group_id(run_id, name, index)
                record = run_live.run_process(
                    name, process, group, run_dir, _env(stub.url), instrument=False
                )
                record.update(workload=name, job=process["job"], instrumented=False)
                programs.append(record)
        time.sleep(SETTLE_S)
        uninstrumented = list(stub.requests)

        control = subprocess.run(
            [sys.executable, str(MANUAL)],
            env=_env(stub.url),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        time.sleep(SETTLE_S)
        control_requests = stub.requests[len(uninstrumented) :]
    finally:
        stub.close()
    return {
        "openlineage_python_version": importlib.metadata.version("openlineage-python"),
        "programs": programs,
        "events_received_uninstrumented": len(uninstrumented),
        "requests_uninstrumented": uninstrumented,
        "control": {
            "program": MANUAL.name,
            "exit_code": control.returncode,
            "stderr_tail": control.stderr[-2000:],
            "events_received": len(control_requests),
            "event_types": [r["eventType"] for r in control_requests],
        },
    }
