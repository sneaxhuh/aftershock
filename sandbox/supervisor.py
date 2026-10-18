"""Bounded process supervisor. No shell commands or Docker socket required."""

import base64
import hashlib
import io
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.request

ROOT = Path(os.environ.get("SANDBOX_DIR", "/data"))
BASE = int(os.environ.get("SERVICE_BASE_PORT", "9000"))
ROLES = ["data", "inventory", "recommendations", "billing", "checkout"]
PORTS = {
    "checkout": BASE + 1,
    "recommendations": BASE + 2,
    "inventory": BASE + 3,
    "billing": BASE + 4,
    "data": BASE + 5,
}
PROCESSES = {}
LOCK = threading.RLock()


def read_config():
    return json.loads((ROOT / "config.json").read_text())


def write_config(cfg):
    temp = ROOT / "config.tmp"
    temp.write_text(json.dumps(cfg, sort_keys=True))
    temp.replace(ROOT / "config.json")


def stop(role):
    proc = PROCESSES.pop(role, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def start(role):
    env = {**os.environ, "SERVICE_ROLE": role}
    module = (
        f"sandbox.checkout_v{read_config()['checkout_version']}"
        if role == "checkout"
        else "sandbox.service"
    )
    PROCESSES[role] = subprocess.Popen([sys.executable, "-m", module], env=env)
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORTS[role]}/health", timeout=0.2
            ):
                return
        except Exception:
            time.sleep(0.025)
    raise RuntimeError(f"{role} did not become ready")


def reset():
    for role in ROLES:
        stop(role)
    ROOT.mkdir(parents=True, exist_ok=True)
    write_config(
        {"fault": False, "fallback": False, "required": False, "checkout_version": 2}
    )
    (ROOT / "company.sqlite").unlink(missing_ok=True)
    with sqlite3.connect(ROOT / "company.sqlite") as db:
        db.executescript(
            "CREATE TABLE schema_version(version INTEGER); INSERT INTO schema_version VALUES(2); CREATE TABLE orders(id INTEGER PRIMARY KEY,item TEXT); CREATE TABLE invoices(id INTEGER PRIMARY KEY,amount INTEGER);"
        )
    for role in ROLES:
        start(role)


def snapshot():
    target = ROOT / "snapshot.sqlite"
    with (
        sqlite3.connect(ROOT / "company.sqlite") as src,
        sqlite3.connect(target) as dst,
    ):
        src.backup(dst)
    data = target.read_bytes()
    cfg = read_config()
    checksum = hashlib.sha256(
        data + json.dumps(cfg, sort_keys=True).encode()
    ).hexdigest()
    return {
        "database": base64.b64encode(data).decode(),
        "config": cfg,
        "checksum": checksum,
    }


def restore(bundle):
    raw = base64.b64decode(bundle["database"], validate=True)
    expected = hashlib.sha256(
        raw + json.dumps(bundle["config"], sort_keys=True).encode()
    ).hexdigest()
    if expected != bundle["checksum"]:
        raise ValueError("Snapshot checksum mismatch")
    for role in ROLES:
        stop(role)
    (ROOT / "company.sqlite").write_bytes(raw)
    write_config(bundle["config"])
    for role in ROLES:
        start(role)


def probe(role):
    path = "/checkout" if role == "checkout" else "/invoice"
    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORTS[role]}{path}", timeout=0.7
        ) as response:
            body, status = json.load(response), response.status
    except urllib.error.HTTPError as error:
        status, body = error.code, json.loads(error.read())
    except Exception as error:
        status, body = 503, {"error": type(error).__name__}
    return {
        "ok": status == 200,
        "status": status,
        "body": body,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, data, status=200):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/health":
            healthy = len(PROCESSES) == len(ROLES) and all(
                p.poll() is None for p in PROCESSES.values()
            )
            return self.respond({"ok": healthy}, 200 if healthy else 503)
        if self.path == "/status":
            return self.respond(
                {
                    "config": read_config(),
                    "processes": {
                        role: {"pid": p.pid, "running": p.poll() is None}
                        for role, p in PROCESSES.items()
                    },
                }
            )
        if self.path == "/observe":
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = dict(
                    zip(
                        ["checkout", "billing"],
                        pool.map(probe, ["checkout", "billing"]),
                    )
                )
            return self.respond({"at": time.time(), **results})
        self.respond({"error": "not_found"}, 404)

    def do_POST(self):
        try:
            data = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}"
            )
            with LOCK:
                if self.path == "/reset":
                    reset()
                elif self.path == "/snapshot":
                    return self.respond(snapshot())
                elif self.path == "/restore":
                    restore(data)
                elif self.path == "/fault":
                    cfg = read_config()
                    cfg["fault"] = bool(data.get("enabled", True))
                    cfg["fallback"] = False
                    write_config(cfg)
                elif self.path == "/policy":
                    cfg = read_config()
                    cfg["required"] = bool(data["required"])
                    cfg["fallback"] = False
                    write_config(cfg)
                elif self.path == "/action":
                    action = data["action"]
                    cfg = read_config()
                    if action == "rollback_checkout":
                        stop("checkout")
                        cfg["checkout_version"] = 1
                        write_config(cfg)
                        start("checkout")
                    elif action == "restart_data":
                        old_pid = PROCESSES["data"].pid
                        stop("data")
                        time.sleep(1.2)
                        start("data")
                        return self.respond(
                            {
                                "ok": True,
                                "old_pid": old_pid,
                                "new_pid": PROCESSES["data"].pid,
                            }
                        )
                    elif action == "enable_fallback":
                        if cfg["required"]:
                            return self.respond(
                                {
                                    "error": "Mandatory recommendations cannot be bypassed"
                                },
                                422,
                            )
                        cfg["fallback"] = True
                        write_config(cfg)
                    else:
                        return self.respond({"error": "Unknown action"}, 400)
                else:
                    return self.respond({"error": "not_found"}, 404)
            self.respond({"ok": True, "config": read_config()})
        except (ValueError, KeyError) as error:
            self.respond({"error": str(error)}, 400)
        except Exception as error:
            self.respond({"error": str(error)}, 500)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "config.json").exists():
        reset()
    else:
        for role in ROLES:
            start(role)

    def shutdown(*_):
        for role in ROLES:
            stop(role)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    server = ThreadingHTTPServer(("0.0.0.0", BASE), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
