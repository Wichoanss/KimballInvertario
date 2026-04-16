import threading
import requests
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

# Configuración del test
BASE_URL = "http://localhost:4500"
API_KEY = "tu_api_key_aqui"  # Reemplazar por una válida de la DB
CONCURRENT_REQUESTS = 55

def send_extract_request(i):
    payload = {
        "line_name": "L1",
        "item_codes": [f"STRESS_PART_{i}"],
        "reel_codes": [f"STRESS_REEL_{i}"],
        "type": "smartrack",
        "idempotency_key": str(uuid.uuid4())
    }
    headers = {"X-API-Key": API_KEY}
    
    try:
        start = time.perf_counter()
        r = requests.post(f"{BASE_URL}/api/extract", json=payload, headers=headers, timeout=10)
        end = time.perf_counter()
        status = r.status_code
        msg = r.json().get("message", "")[:30]
        print(f"[{i:02d}] Status: {status} | Time: {end-start:.3f}s | {msg}")
        return status
    except Exception as e:
        print(f"[{i:02d}] ERROR: {e}")
        return 500

def run_stress_test():
    print(f"--- INICIANDO PRUEBA DE CARGA: {CONCURRENT_REQUESTS} REQUESTS ---")
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(send_extract_request, i) for i in range(CONCURRENT_REQUESTS)]
        for f in futures:
            results.append(f.result())
    
    total = len(results)
    success = results.count(200)
    errors = total - success
    print(f"\n--- RESUMEN ---")
    print(f"Total: {total} | Exitosos: {success} | Fallidos: {errors}")
    print(f"Factor de éxito: {(success/total)*100:.1f}%")

if __name__ == "__main__":
    # Nota: Asegúrate de que el servidor esté corriendo y API_KEY sea válida
    # run_stress_test()
    pass
