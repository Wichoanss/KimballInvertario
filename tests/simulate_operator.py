import requests
import time

BASE_URL = "http://127.0.0.1:8000"

def test_operator_journey():
    print("--- INICIANDO VIAJE DEL OPERADOR ---")
    
    # 1. Intento de entrada a la raíz (debe cargar el HTML)
    print("1. Cargando Index...")
    res = requests.get(f"{BASE_URL}/")
    if res.status_code == 200 and "SmartRack" in res.text:
        print("   [OK] HTML cargado correctamente.")
    else:
        print(f"   [FALLO] Status: {res.status_code}")

    # 2. Simular búsqueda de parte SmartRack (CCR00097)
    # Primero necesitamos una API KEY. Vamos a crear una rápida.
    # (Asumiendo que tenemos acceso de admin para bootstrap)
    print("2. Buscando parte SmartRack (CCR00097)...")
    payload = {"item_code": "CCR00097", "line_id": 1}
    # Simulamos lo que haría el JS (llamada a /api/check-code)
    # Nota: No enviamos API Key para ver si falla (Escenario: Operador sin loguear)
    res = requests.post(f"{BASE_URL}/api/check-code", json=payload)
    if res.status_code == 401:
        print("   [OK] El sistema bloqueó la búsqueda sin API Key.")
    
    # 3. Loguear (Simulado con una key válida)
    # En este entorno de prueba, buscaremos una key en la DB o usaremos la de admin
    # Para el test, vamos a crear un usuario 'tester'
    print("3. Creando usuario tester...")
    # ... (esto lo haremos con la lógica interna si el endpoint admin es complejo)
    
    # 4. Escenario JUKI (IRS0433)
    print("4. Probando detección JUKI (IRS0433)...")
    # Si el poller ya corrió, debería estar en la DB local.
    
    print("--- VIAJE FINALIZADO ---")

if __name__ == "__main__":
    # Esperar un poco a que uvicorn esté listo
    time.sleep(2)
    try:
        test_operator_journey()
    except Exception as e:
        print(f"Error en el test: {e}")
