import requests
import time
import hashlib
import json
from datetime import datetime

# ============================================================
#   CONFIGURACIÓN TELEGRAM
# ============================================================
TELEGRAM_TOKEN = "AQUI_TU_TOKEN"
TELEGRAM_CHAT_ID = "AQUI_TU_CHAT_ID"

def send_telegram(message):
    """Envía un mensaje a Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[ERROR] Telegram: {e}")

# ============================================================
#   LOGS
# ============================================================
LOG_FILE = "check_sites.log"
HASH_FILE = "site_hashes.txt"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} - {msg}\n")
    print(msg)

# ============================================================
#   CARGA AUTOMÁTICA DEL JSON DE GITHUB
# ============================================================
def load_sites_from_json():
    url = "https://raw.githubusercontent.com/alber112es-collab/WEB2/main/urls.json"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return json.loads(response.text)
    except Exception as e:
        log(f"[ERROR] No se pudo cargar el JSON de URLs: {e}")
        send_telegram(f"❌ ERROR cargando JSON de URLs\n{e}")
        return {}

# ============================================================
#   HASHES
# ============================================================
def load_hashes():
    hashes = {}
    try:
        with open(HASH_FILE, "r") as f:
            for line in f:
                name, h = line.strip().split("=", 1)
                hashes[name] = h
    except FileNotFoundError:
        pass
    return hashes

def save_hashes(hashes):
    with open(HASH_FILE, "w") as f:
        for name, h in hashes.items():
            f.write(f"{name}={h}\n")

# ============================================================
#   CHECK DE SITIOS
# ============================================================
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def check_site(name, url, retries=3, backoff_factor=2):
    """Comprueba un sitio con reintentos y manejo de errores."""
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=20)

            if response.status_code == 200:
                return response.text

            elif response.status_code == 429:
                wait = backoff_factor ** attempt
                log(f"[WARN] {name}: 429 Too Many Requests. Esperando {wait}s...")
                time.sleep(wait)

            else:
                log(f"[ERROR] {name}: código {response.status_code}")
                send_telegram(f"❌ ERROR en {name}\nCódigo HTTP: {response.status_code}\nURL: {url}")
                return None

        except requests.exceptions.Timeout:
            log(f"[ERROR] {name}: timeout. Intento {attempt+1}/{retries}")
            time.sleep(backoff_factor ** attempt)

        except requests.exceptions.RequestException as e:
            log(f"[ERROR] {name}: {e}")
            send_telegram(f"❌ ERROR en {name}\n{e}\nURL: {url}")
            return None

    log(f"[FAIL] {name}: no accesible tras {retries} intentos.")
    send_telegram(f"❌ FALLÓ {name} tras {retries} intentos.\nURL: {url}")
    return None

# ============================================================
#   MAIN
# ============================================================
def main():
    log("▶ Iniciando revisión de sitios...")

    sites = load_sites_from_json()
    hashes = load_hashes()

    for name, url in sites.items():
        log(f"[check] {name}")
        content = check_site(name, url)

        if content:
            new_hash = hashlib.sha256(content.encode()).hexdigest()
            old_hash = hashes.get(name)

            if old_hash != new_hash:
                log(f"[CHANGE] {name}: ¡Contenido cambiado!")
                send_telegram(f"🔔 CAMBIO DETECTADO en {name}\nURL: {url}")
                hashes[name] = new_hash
            else:
                log(f"[OK] {name}: sin cambios")

    save_hashes(hashes)
    log("✔ Revisión completa.\n")

if __name__ == "__main__":
    main()
