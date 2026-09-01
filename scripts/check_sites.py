import requests
import time
import hashlib
from datetime import datetime

sites = {
    "HARO": "https://haro.sedipualba.es/tablondeanuncios/",
    "Unirioja": "https://www.unirioja.es/administracion-y-servicios/servicio-de-personal/lista-de-espera/",
    "SEC-INT": "https://www.larioja.org/larioja-client/cm/portal-ayuntamientos/tkContent?idContent=871400&locale=es_ES",
    "AGE": "https://sede.inap.gob.es/es/procedimientos-y-servicios/seleccion/procesos-selectivos-de-cuerpos-y-escalas-generales/cuerpo-general-administrativo-de-la-administracion-del-estado-ingreso-libre-convocatoria-2025"
}

LOG_FILE = "check_sites.log"
HASH_FILE = "site_hashes.txt"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
})

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} - {msg}\n")
    print(msg)

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

def check_site(name, url, retries=3, backoff_factor=2):
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
                return None
        except requests.exceptions.Timeout:
            log(f"[ERROR] {name}: timeout. Intento {attempt+1}/{retries}")
            time.sleep(backoff_factor ** attempt)
        except requests.exceptions.RequestException as e:
            log(f"[ERROR] {name}: {e}")
            return None
    log(f"[FAIL] {name}: no accesible tras {retries} intentos.")
    return None

def main():
    log("▶ Iniciando revisión de sitios...")
    hashes = load_hashes()

    for name, url in sites.items():
        log(f"[check] {name}")
        content = check_site(name, url)

        if content:
            new_hash = hashlib.sha256(content.encode()).hexdigest()
            old_hash = hashes.get(name)

            if old_hash != new_hash:
                log(f"[CHANGE] {name}: ¡Contenido cambiado!")
                hashes[name] = new_hash
            else:
                log(f"[OK] {name}: sin cambios")

    save_hashes(hashes)
    log("✔ Revisión completa.\n")

if __name__ == "__main__":
    main()
