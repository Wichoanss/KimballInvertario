import requests
import time

BASE_URL = "http://127.0.0.1:4500"

def run_scenarios():
    print("\n[+] INICIANDO SIMULACIÓN INTEGRAL DEL OPERADOR\n" + "="*50)
    
    # Escenario 1: Carga inicial
    try:
        r = requests.get(BASE_URL)
        print(f"1. Acceso a UI: {'OK (200)' if r.status_code == 200 else f'FALLO ({r.status_code})'}")
    except Exception as e:
        print(f"1. Acceso a UI: CRASH ({e})")
        return

    # Escenario 2: Intento de búsqueda SIN login
    r = requests.post(f"{BASE_URL}/api/check-code", json={"item_code": "CCR00097", "line_id": 1})
    print(f"2. Búsqueda sin login: {'BLOQUEADO (401)' if r.status_code == 401 else f'VULNERABLE ({r.status_code})'}")

    # Escenario 3: Obtener una Key válida (simulamos login exitoso)
    # Primero listamos usuarios para obtener la clave de 'admin'
    r = requests.get(f"{BASE_URL}/admin/users", headers={"X-Master-Key": "testmaster"})
    if r.status_code == 200:
        users = r.json()
        api_key = next((u['api_key'] for u in users if u['username'] == 'admin'), None)
        print(f"3. Login obtenido (Key admin): {api_key[:5]}...")
    else:
        print(f"3. Login FALLIDO: {r.status_code}")
        return

    headers = {"X-API-Key": api_key}

    # Escenario 4: Búsqueda exitosa en SmartRack
    r = requests.post(f"{BASE_URL}/api/check-code", json={"item_code": "CCR00097", "line_id": 1}, headers=headers)
    if r.status_code == 200:
        data = r.json()
        print(f"4. Búsqueda SmartRack: ENCONTRADO en Rack {data.get('reel', {}).get('rack')}")
    else:
        print(f"4. Búsqueda SmartRack: FALLO ({r.status_code})")

    # Escenario 5: Búsqueda en JUKI
    r = requests.post(f"{BASE_URL}/api/check-code", json={"item_code": "IRS0433", "line_id": 1}, headers=headers)
    if r.status_code == 200:
        data = r.json()
        print(f"5. Búsqueda JUKI: DETECTADO en JUKI ({data.get('status')})")
    else:
        print(f"5. Búsqueda JUKI: FALLO ({r.status_code})")

    # Escenario 6: Parte inexistente
    r = requests.post(f"{BASE_URL}/api/check-code", json={"item_code": "NOTFOUND55", "line_id": 1}, headers=headers)
    if r.status_code == 200:
        data = r.json()
        print(f"6. Parte inexistente: {data.get('status')} (Correcto)")
    else:
        print(f"6. Parte inexistente: FALLO ({r.status_code})")

    # Escenario 7: Solicitar Extracción (Idempotencia)
    ext_data = {
        "type": "smartrack",
        "reel_codes": ["REEL_TEST_01"],
        "line_id": 1,
        "line_name": "L1",
        "idempotency_key": "test_idemp_001"
    }
    r1 = requests.post(f"{BASE_URL}/api/extract", json=ext_data, headers=headers)
    print(f"7. Extracción (1er intento): {'OK' if r1.status_code == 200 else f'FALLO ({r1.status_code})'}")
    
    r2 = requests.post(f"{BASE_URL}/api/extract", json=ext_data, headers=headers)
    print(f"7. Extracción (2do intento - Idempotencia): {'DUPLICADO DETECTADO (409)' if r2.status_code == 409 else f'FALLO ({r2.status_code})'}")

    print("\n[+] SIMULACIÓN FINALIZADA CON ÉXITO\n" + "="*50)

if __name__ == "__main__":
    time.sleep(1) # Pequeña espera para startup
    run_scenarios()
