import requests
import time

# Lista de sitios a comprobar
sites = {
    "HARO": "https://haro.sedipualba.es/tablondeanuncios/",
    "Unirioja": "https://www.unirioja.es/administracion-y-servicios/servicio-de-personal/lista-de-espera/",
    "Logroño-1": "https://example.com/logrono1",
    "Calahorra": "https://example.com/calahorra",
    "Najera": "https://example.com/najera",
    "Logroño-2": "https://example.com/logrono2",
    "SEC-INT": "https://www.larioja.org/larioja-client/cm/portal-ayuntamientos/tkContent?idContent=871400&locale=es_ES",
    "AGE": "https://sede.inap.gob.es/es/procedimientos-y-servicios/seleccion/procesos-selectivos-de-cuerpos-y-escalas-generales/cuerpo-general-administrativo-de-la-administracion-del-estado-ingreso-libre-convocatoria-2025"
}

def check_site(name, url, retries=3, backoff_factor=2):
    """Comprueba un sitio con reintentos y manejo de errores."""
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                print(f"[OK] {name}: sin cambios")
                return True
            elif response.status_code == 429:
                wait = backoff_factor ** attempt
                print(f"[WARN] {name}: demasiadas peticiones (429). Esperando {wait}s antes de reintentar...")
                time.sleep(wait)
            else:
                print(f"[ERROR] {name}: código {response.status_code}")
                return False
        except requests.exceptions.Timeout:
            print(f"[ERROR] {name}: tiempo de espera agotado (timeout). Intento {attempt + 1}/{retries}")
            time.sleep(backoff_factor ** attempt)
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] {name}: {e}")
            return False
    print(f"[FAIL] {name}: no se pudo acceder tras {retries} intentos.")
    return False

def main():
    print("▶ Iniciando revisión de sitios...\n")
    for name, url in sites.items():
        print(f"[check] {name}")
        check_site(name, url)
    print("\nRevisión completa.")

if __name__ == "__main__":
    main()
