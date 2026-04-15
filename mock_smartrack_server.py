import sqlite3, uuid, time, sys, traceback, logging, xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# UTF-8 para Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Configuración de logs detallada
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("MockServer")

PORT = 8081
DB_PATH = r"c:\Proyectos\KimballInvertario\realdata\mock_snapshot.db"
_tokens = {}

def get_xml(reels, juki=False):
    root = ET.Element("v2_reellist", count=str(len(reels)), err="0")
    for r in reels:
        try:
            ri = ET.SubElement(root, "v2_reelinfo")
            
            # code
            code_val = r.get("code")
            ET.SubElement(ri, "code").text = str(code_val) if code_val is not None else ""
            
            # itemcode
            ic_val = r.get("itemcode")
            ET.SubElement(ri, "itemcode").text = str(ic_val) if ic_val is not None else ""
            
            # quantity
            qty_raw = r.get("qty")
            try:
                qty_val = int(float(qty_raw)) if qty_raw is not None else 0
            except:
                qty_val = 0
            ET.SubElement(ri, "quantity").text = str(qty_val)
            
            if juki:
                # containerid
                cid = r.get("container_id")
                cid_str = str(cid) if cid is not None else "1"
                ET.SubElement(ri, "containerid").text = cid_str
                ET.SubElement(ri, "container").text = cid_str
            else:
                # stockcell
                sc = r.get("stockcell")
                sc_str = str(sc) if sc is not None else ""
                
                # Intentar recodificar para el poller real
                try:
                    if " " in sc_str:
                        side = "1" if "left" in sc_str.lower() else "2"
                        pos = sc_str.split()[-1] 
                        if "/" in pos:
                            l, c = pos.split("/")
                            row = ord(l.upper()) - 64
                            sc_str = f"{side}{row:02d}{int(c):02d}"
                except:
                    pass
                ET.SubElement(ri, "stockcell").text = sc_str
                
        except Exception as e:
            logger.error(f"Error processing reel row: {r} | {e}")
            continue
            
    return ET.tostring(root, encoding="utf-8")

class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.debug(f"HTTP {self.client_address[0]}: {format % args}")

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            q = parse_qs(parsed.query)
            f = q.get("f", [""])[0]
            logger.info(f"--- F={f} ---")
            
            body = b""
            if f == "login":
                tk = uuid.uuid4().hex.upper()
                _tokens[tk] = time.time() + 3600
                root = ET.Element("loginresult", err="0")
                ET.SubElement(root, "token").text = tk
                body = ET.tostring(root, encoding="utf-8")
                logger.info(f"Login OK -> {tk[:8]}...")
            
            elif f == "V2_reel_getlist":
                tk = q.get("tkn", [""])[0]
                if tk not in _tokens:
                    logger.warning(f"Unauthorized: token {tk}")
                    body = b"<v2_reellist err='2' errdesc='Invalid Token'/>"
                else:
                    conn = sqlite3.connect(DB_PATH)
                    conn.row_factory = sqlite3.Row
                    
                    # SmartRack
                    rf = q.get("filter_smartrackidlist", [""])[0]
                    if rf:
                        logger.info(f"Query SmartRack ID: {rf}")
                        rows = conn.execute("SELECT * FROM reels WHERE rack=?", (rf,)).fetchall()
                        body = get_xml([dict(r) for r in rows], juki=False)
                    else:
                        # JUKI
                        cf = q.get("filter_containeridlist", [""])[0]
                        if cf:
                            logger.info(f"Query JUKI Containers: {cf}")
                            cids = cf.split(",")
                            placeholders = ",".join("?" * len(cids))
                            rows = conn.execute(f"SELECT * FROM juki_reels WHERE container_id IN ({placeholders})", cids).fetchall()
                            body = get_xml([dict(r) for r in rows], juki=True)
                        else:
                            body = b"<v2_reellist count='0' err='0'/>"
                    conn.close()
            
            elif f == "V3_extractreels":
                job_name = q.get("name", ["EXT"])[0]
                logger.info(f"Extraction Order: {job_name}")
                root = ET.Element("v3_extractresult", err="0", name=job_name, count="1")
                body = ET.tostring(root, encoding="utf-8")
            
            else:
                logger.warning(f"Unknown F: {f}")
                body = b"<err>99</err>"

            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            logger.info(f"Response Sent: {len(body)} bytes")

        except Exception:
            err = traceback.format_exc()
            logger.critical(f"FATAL ERROR in Handler:\n{err}")
            try:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                eb = err.encode("utf-8")
                self.send_header("Content-Length", str(len(eb)))
                self.end_headers()
                self.wfile.write(eb)
            except: pass

if __name__ == "__main__":
    logger.info(f"Mock Server Starting on http://localhost:{PORT}")
    try:
        HTTPServer(("0.0.0.0", PORT), MockHandler).serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown.")
