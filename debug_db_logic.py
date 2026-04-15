import sqlite3, xml.etree.ElementTree as ET
import traceback

DB_PATH = r"c:\Proyectos\KimballInvertario\realdata\mock_snapshot.db"

def get_xml(reels, juki=False):
    root = ET.Element("v2_reellist", count=str(len(reels)), err="0")
    for r in reels:
        try:
            ri = ET.SubElement(root, "v2_reelinfo")
            code_val = r.get("code")
            ET.SubElement(ri, "code").text = str(code_val) if code_val is not None else ""
            ic_val = r.get("itemcode")
            ET.SubElement(ri, "itemcode").text = str(ic_val) if ic_val is not None else ""
            qty_raw = r.get("qty")
            try:
                qty_val = int(float(qty_raw)) if qty_raw is not None else 0
            except:
                qty_val = 0
            ET.SubElement(ri, "quantity").text = str(qty_val)
            
            if juki:
                cid = r.get("container_id")
                cid_str = str(cid) if cid is not None else "1"
                ET.SubElement(ri, "containerid").text = cid_str
                ET.SubElement(ri, "container").text = cid_str
            else:
                sc = r.get("stockcell")
                sc_str = str(sc) if sc is not None else ""
                try:
                    if " " in sc_str:
                        side = "1" if "left" in sc_str.lower() else "2"
                        pos = sc_str.split()[-1] 
                        if "/" in pos:
                            l, c = pos.split("/")
                            row = ord(l.upper()) - 64
                            sc_str = f"{side}{row:02d}{int(c):02d}"
                except Exception:
                    pass
                ET.SubElement(ri, "stockcell").text = sc_str
        except Exception as e:
            print(f"ERROR processing reel: {r} -> {e}")
            raise
    return ET.tostring(root, encoding="utf-8")

def debug_query():
    print(f"Conectando a {DB_PATH}...")
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Simular consulta SmartRack Rack 1
        print("Querying Rack 1...")
        rows = conn.execute("SELECT * FROM reels WHERE rack=?", ("1",)).fetchall()
        print(f"Retrieved {len(rows)} rows.")
        
        # Simular XML generation
        print("Buidling XML...")
        xml_data = get_xml([dict(r) for r in rows], juki=False)
        print(f"XML built: {len(xml_data)} bytes.")
        
        # Simular JUKI
        print("\nQuerying JUKI Container 1...")
        rows_juki = conn.execute("SELECT * FROM juki_reels WHERE container_id=?", ("1",)).fetchall()
        print(f"Retrieved {len(rows_juki)} rows.")
        xml_juki = get_xml([dict(r) for r in rows_juki], juki=True)
        print(f"JUKI XML built: {len(xml_juki)} bytes.")
        
        conn.close()
        print("\nSUCCESS: Database and logic are fine.")
        
    except Exception:
        print("\nFAILURE:")
        traceback.print_exc()

if __name__ == "__main__":
    debug_query()
