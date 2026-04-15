import sqlite3, uuid, time, threading, traceback, xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

DB_PATH = r"c:\Proyectos\KimballInvertario\realdata\mock_snapshot.db"
_tokens = {}

def get_xml(reels, juki=False):
    root = ET.Element("v2_reellist", count=str(len(reels)), err="0")
    for r in reels:
        ri = ET.SubElement(root, "v2_reelinfo")
        ET.SubElement(ri, "code").text = str(r.get("code", ""))
        ET.SubElement(ri, "itemcode").text = str(r.get("itemcode", ""))
        qty = r.get("qty")
        ET.SubElement(ri, "quantity").text = str(int(qty) if qty is not None else 0)
        if juki:
            cid = str(r.get("container_id") or "1")
            ET.SubElement(ri, "containerid").text = cid
        else:
            sc = str(r.get("stockcell") or "")
            try:
                if " " in sc:
                    side = "1" if "left" in sc.lower() else "2"
                    pos = sc.split()[-1]
                    if "/" in pos:
                        l, c = pos.split("/")
                        sc = f"{side}{ord(l.upper())-64:02d}{int(c):02d}"
            except: pass
            ET.SubElement(ri, "stockcell").text = sc
    return ET.tostring(root, encoding="utf-8")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            f = q.get("f", [""])[0]
            print(f">> Server Handling: {f}", flush=True)
            
            body = b""
            if f == "login":
                tk = uuid.uuid4().hex.upper()
                _tokens[tk] = time.time() + 3600
                root = ET.Element("loginresult", err="0")
                ET.SubElement(root, "token").text = tk
                body = ET.tostring(root, encoding="utf-8")
            elif f == "V2_reel_getlist":
                tk = q.get("tkn", [""])[0]
                if tk not in _tokens: body = b"<err>2</err>"
                else:
                    conn = sqlite3.connect(DB_PATH)
                    conn.row_factory = sqlite3.Row
                    rf = q.get("filter_smartrackidlist", [""])[0]
                    if rf:
                        rows = conn.execute("SELECT * FROM reels WHERE rack=?", (rf,)).fetchall()
                        body = get_xml([dict(r) for r in rows])
                    else: body = b"<v2_reellist count=\"0\" err=\"0\"/>"
                    conn.close()
            else: body = b"<err>99</err>"

            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            print(f"   Server Finished: {len(body)} bytes", flush=True)

        except Exception:
            err = traceback.format_exc()
            print(f"!! Server Error:\n{err}", flush=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(err.encode("utf-8"))

def run_server():
    server = HTTPServer(("127.0.0.1", 8081), H)
    server.serve_forever()

if __name__ == "__main__":
    print("Starting server thread...", flush=True)
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(1)

    print("--- Starting Client Test ---", flush=True)
    try:
        base = "http://127.0.0.1:8081/"
        # 1. Login
        print("1. Testing Login...", flush=True)
        r = requests.get(base, params={"f": "login", "username": "admin", "password": "admin"})
        print(f"   Status: {r.status_code}")
        tk = ET.fromstring(r.text).find("token").text
        print(f"   Token: {tk[:8]}...")

        # 2. GetList
        print("2. Testing GetList (Rack 1)...", flush=True)
        r2 = requests.get(base, params={"f": "V2_reel_getlist", "filter_smartrackidlist": "1", "tkn": tk})
        print(f"   Status: {r2.status_code}")
        if r2.status_code != 200:
            print(f"   Body: {r2.text}")
        else:
            print(f"   Bytes: {len(r2.content)}")
            root = ET.fromstring(r2.content)
            print(f"   Count: {root.get('count')}")
            
        print("--- All finished ---", flush=True)
    except Exception:
        traceback.print_exc()
