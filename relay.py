"""Hosted relay for Atajos. Uses only Python's standard library."""
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import hmac
import json
import os
import secrets
import threading
import time

ROOT = Path(__file__).resolve().parent
PIN = "102030"
AGENT_KEY = os.environ.get("RELAY_AGENT_KEY", "")
APP_SCHEMES = {"spotify", "twitch", "steam", "discord", "vlc", "epicgames", "xbox", "roblox"}
commands = deque(maxlen=20)
tokens = set()
lock = threading.Condition()
agent_seen = 0.0
bad_attempts = {}
blocked_until = {}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def json_response(self, status, payload):
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                return None
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def agent_authorized(self):
        return bool(AGENT_KEY) and hmac.compare_digest(
            self.headers.get("X-Agent-Key", ""), AGENT_KEY
        )

    def do_GET(self):
        global agent_seen
        if self.path == "/api/status":
            with lock:
                online = time.time() - agent_seen < 75
            self.json_response(200, {"pcOnline": online})
            return
        if self.path == "/api/agent/next":
            if not self.agent_authorized():
                self.json_response(401, {"error": "Agente no autorizado"})
                return
            with lock:
                agent_seen = time.time()
                if not commands:
                    lock.wait(timeout=18)
                agent_seen = time.time()
                item = commands.popleft() if commands else None
            self.json_response(200, {"command": item})
            return
        if self.path.startswith("/api/"):
            self.json_response(404, {"error": "Ruta no encontrada"})
            return
        super().do_GET()

    def do_POST(self):
        global agent_seen
        data = self.body_json()
        if self.path == "/api/pair":
            ip = self.client_address[0]
            now = time.time()
            if blocked_until.get(ip, 0) > now:
                self.json_response(429, {"error": "Demasiados intentos. Espera cinco minutos."})
                return
            with lock:
                pc_online = now - agent_seen < 75
            if not pc_online:
                self.json_response(503, {"error": "La app de Atajos no está abierta en la PC."})
                return
            pin = str((data or {}).get("pin", ""))
            if not hmac.compare_digest(pin, PIN):
                bad_attempts[ip] = bad_attempts.get(ip, 0) + 1
                if bad_attempts[ip] >= 5:
                    blocked_until[ip] = now + 300
                    bad_attempts[ip] = 0
                self.json_response(401, {"error": "Código incorrecto."})
                return
            bad_attempts.pop(ip, None)
            token = secrets.token_urlsafe(32)
            with lock:
                tokens.clear()
                tokens.add(token)
            self.json_response(200, {"token": token})
            return
        if self.path == "/api/open":
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if not token or token not in tokens:
                self.json_response(401, {"error": "Vuelve a conectar con el código 102030."})
                return
            target = str((data or {}).get("target", "")).strip()
            scheme = urlsplit(target).scheme.lower()
            if scheme not in ({"http", "https"} | APP_SCHEMES) or len(target) > 2048:
                self.json_response(400, {"error": "Este tipo de enlace no se puede abrir."})
                return
            with lock:
                if time.time() - agent_seen >= 75:
                    self.json_response(503, {"error": "La PC se desconectó. Abre Atajos en Windows."})
                    return
                commands.append({"target": target})
                lock.notify()
            self.json_response(202, {"message": "Enlace enviado a la PC"})
            return
        if self.path == "/api/agent/result":
            if not self.agent_authorized():
                self.json_response(401, {"error": "Agente no autorizado"})
                return
            with lock:
                agent_seen = time.time()
            self.json_response(200, {"ok": True})
            return
        self.json_response(404, {"error": "Ruta no encontrada"})


if __name__ == "__main__":
    if not AGENT_KEY or len(AGENT_KEY) < 32:
        raise SystemExit("Configura RELAY_AGENT_KEY (al menos 32 caracteres) en Render.")
    port = int(os.environ.get("PORT", "8765"))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Atajos relay escuchando en el puerto {port}", flush=True)
    httpd.serve_forever()
