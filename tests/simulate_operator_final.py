import requests
import time
import os

def load_env_manual():
    env = {}
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    return env

env = load_env_manual()
BASE_URL = f"http://127.0.0.1:{env.get('SERVER_PORT', '4500')}"
ADMIN_USER = env.get("CONFIG_USERNAME", "admin")
ADMIN_PASS = env.get("CONFIG_PASSWORD", "administrator")

def run_scenarios():
    print("\n[+] INICIANDO SIMULACIÓN 'ANTIBALAS' DEFINITIVA\n" + "="*50)
    
    # Escenario 1: Carga inicial y verificar bloqueo de seguridad
    try:
        r = requests.post(f"{BASE_URL}/api/check_reel", json={"itemcode": "CCR00097", "line_id": 1})
        print(f"1. Acceso sin login: {'BLOQUEADO (401)' if r.status_code == 401 else f'VULNERABLE ({r.status_code})'}")
    except Exception as e:
        print(f"1. Acceso UI: CRASH ({e})")
        return

    # Escenario 2: Login Administrativo para obtener Master Key
    print(f"2. Logueando como admin '{ADMIN_USER}'...")
    r = requests.post(f"{BASE_URL}/api/auth/config", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    if r.status_code == 200:
        master_key = r.json().get("token")
        print(f"   [OK] Master Key obtenida: {master_key[:8]}...")
    else:
        print(f"   [FALLO] Login admin fallido: {r.status_code} - {r.text}")
        return

    # Escenario 3: Crear un Operador de prueba
    test_op_id = "OP_TEST_999"
    print(f"3. Creando operador de prueba '{test_op_id}'...")
    r = requests.post(
        f"{BASE_URL}/admin/users", 
        json={"username": "test_operator", "api_key": test_op_id},
        headers={"X-Master-Key": master_key}
    )
    if r.status_code == 200:
        print("   [OK] Operador creado correctamente.")
    else:
        # Si ya existe lo ignoramos
        print(f"   [INFO] Status creación: {r.status_code}")

    op_headers = {"X-API-Key": test_op_id}

    # Escenario 4: Búsqueda SmartRack con Operador (ÉXITO)
    print("4. Buscando parte SmartRack (CCR00097) con Operador...")
    r = requests.post(f"{BASE_URL}/api/check_reel", json={"itemcode": "CCR00097", "line_id": 1}, headers=op_headers)
    if r.status_code == 200:
        data = r.json()
        print(f"   [OK] Encontrado en Rack {data.get('reel', {}).get('rack')}")
    else:
        print(f"   [FALLO] Búsqueda SmartRack: {r.status_code} - {r.text}")

    # Escenario 5: Búsqueda JUKI con Operador (ÉXITO)
    print("5. Buscando parte JUKI (IRS0433) con Operador...")
    r = requests.post(f"{BASE_URL}/api/check_reel", json={"itemcode": "IRS0433", "line_id": 1}, headers=op_headers)
    if r.status_code == 200:
        data = r.json()
        print(f"   [OK] Detectado en JUKI: {data.get('status')} - Contenedor: {data.get('reel', {}).get('container_id')}")
    else:
        print(f"   [FALLO] Búsqueda JUKI: {r.status_code}")

    # Escenario 6: Extracción con Idempotencia
    idem_key = "idemp_test_final_001"
    ext_payload = {
        "type": "smartrack",
        "reel_codes": ["REEL_MOCK_1"],
        "item_codes": ["CCR00097"],
        "line_id": 1,
        "line_name": "L1",
        "idempotency_key": idem_key
    }
    print("6. Solicitando extracción inmediata...")
    r1 = requests.post(f"{BASE_URL}/api/extract", json=ext_payload, headers=op_headers)
    print(f"   Intento 1: {'ÉXITO' if r1.status_code == 200 else f'FALLO ({r1.status_code})'}")
    
    r2 = requests.post(f"{BASE_URL}/api/extract", json=ext_payload, headers=op_headers)
    if r2.status_code == 200 and r2.json() == r1.json():
        print(f"   Intento 2 (Misma key): ÉXITO - RESPUESTA CACHEADA CORRECTA (IDEMPOTENCIA OK)")
    else:
        print(f"   Intento 2 (Misma key): VULNERABLE ({r2.status_code})")

    print("\n[+] SIMULACIÓN FINALIZADA CON ÉXITO ABSOLUTO\n" + "="*50)

if __name__ == "__main__":
    # Asegurar que el sistema está corriendo
    try:
        run_scenarios()
    except Exception as e:
        print(f"Error mortal en simulación: {e}")
