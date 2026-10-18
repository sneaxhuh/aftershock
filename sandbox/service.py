import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROLE = os.environ.get("SERVICE_ROLE", "inventory")
BASE = int(os.environ.get("SERVICE_BASE_PORT", "9000"))
ROOT = Path(os.environ.get("SANDBOX_DIR", "/data"))
PORTS = {
    "checkout": BASE + 1,
    "recommendations": BASE + 2,
    "inventory": BASE + 3,
    "billing": BASE + 4,
    "data": BASE + 5,
}


def config():
    return json.loads((ROOT / "config.json").read_text())


def call(role, path, timeout=0.5):
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORTS[role]}{path}", timeout=timeout
        ) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())
    except Exception as error:
        return 503, {"error": f"{role} unavailable", "detail": type(error).__name__}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        try:
            status, body = self.handle_request()
        except Exception as error:
            status, body = 500, {"error": str(error)}
        body = {**body, "service": ROLE, "pid": os.getpid()}
        encoded = json.dumps(body).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_request(self):
        if self.path == "/health":
            return 200, {"ok": True}
        cfg = config()
        if ROLE == "data":
            with sqlite3.connect(ROOT / "company.sqlite", timeout=2) as db:
                if self.path == "/order/v1":
                    schema = db.execute(
                        "SELECT version FROM schema_version"
                    ).fetchone()[0]
                    if schema != 1:
                        return 409, {
                            "error": "schema_incompatible",
                            "requires": 1,
                            "actual": schema,
                        }
                if self.path.startswith("/order/"):
                    db.execute(
                        "INSERT INTO orders (item) VALUES ('Northstar field jacket')"
                    )
                    return 200, {
                        "order_id": db.execute("SELECT last_insert_rowid()").fetchone()[
                            0
                        ]
                    }
                if self.path == "/invoice":
                    db.execute("INSERT INTO invoices (amount) VALUES (12900)")
                    return 200, {
                        "invoice_id": db.execute(
                            "SELECT last_insert_rowid()"
                        ).fetchone()[0]
                    }
                if self.path == "/schema":
                    return 200, {
                        "version": db.execute(
                            "SELECT version FROM schema_version"
                        ).fetchone()[0]
                    }
        if ROLE == "inventory" and self.path == "/stock":
            return 200, {"available": True, "sku": "jacket-01", "quantity": 42}
        if ROLE == "recommendations" and self.path == "/recommend":
            if cfg["fault"]:
                time.sleep(0.8)
                return 504, {"error": "injected_recommendations_timeout"}
            return 200, {"items": ["merino-socks", "trail-cap"]}
        if ROLE == "billing" and self.path == "/invoice":
            return call("data", "/invoice", timeout=0.3)
        if ROLE == "checkout" and self.path == "/checkout":
            version = int(os.environ.get("CHECKOUT_VERSION", "2"))
            stock_status, stock = call("inventory", "/stock")
            if stock_status != 200:
                return 503, {"error": "inventory_unavailable", "cause": stock}
            used_fallback = False
            if version == 2:
                rec_status, rec = call("recommendations", "/recommend", timeout=0.18)
                if rec_status != 200:
                    if not cfg["fallback"]:
                        return 504, {"error": "recommendations_timeout", "cause": rec}
                    if cfg["required"]:
                        return 422, {
                            "error": "mandatory_recommendations_policy",
                            "policy": "policy-recommendations",
                        }
                    used_fallback = True
            status, order = call("data", f"/order/v{version}")
            return status, {**order, "version": version, "fallback_used": used_fallback}
        return 404, {"error": "not_found"}


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORTS[ROLE]), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
