"""Windows companion that receives safe URL-opening requests from the cloud relay."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"


def request(url, key, timeout=25):
    req = urllib.request.Request(url, headers={"X-Agent-Key": key, "User-Agent": "Atajos-PC/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def open_target(target):
    if os.name == "nt":
        os.startfile(target)
    else:
        webbrowser.open(target, new=2)


def main():
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        base_url = config["relay_url"].strip().rstrip("/")
        key = config["agent_key"].strip()
        if urllib.parse.urlsplit(base_url).scheme != "https" or len(key) < 32:
            raise ValueError("config.json debe tener una URL https y la clave privada de Render.")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Configuración incompleta: {exc}")
        input("Ejecuta Configurar-Atajos.bat y vuelve a intentarlo. Enter para cerrar...")
        return 1

    webbrowser.open(base_url, new=2)
    print("Atajos está activo. Deja esta ventana abierta para controlar la PC.")
    print(f"Relay: {base_url}")
    print("Abre la app en el celular y usa el código 102030. Ctrl+C detiene el agente.\n")
    endpoint = base_url + "/api/agent/next"
    while True:
        try:
            result = request(endpoint, key, timeout=24)
            command = result.get("command")
            if command and command.get("target"):
                try:
                    open_target(command["target"])
                    print("Acceso abierto en esta PC: " + command["target"][:140], flush=True)
                except OSError as exc:
                    print(f"Windows no pudo abrir el acceso: {exc}", flush=True)
        except urllib.error.HTTPError as exc:
            print(f"Relay respondió HTTP {exc.code}; reintentando en 5 segundos.", flush=True)
            time.sleep(5)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"Sin conexión con el relay ({exc}); reintentando en 5 segundos.", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAgente de Atajos detenido.")
