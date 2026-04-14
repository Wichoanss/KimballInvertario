import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import config
from database import upsert_reels
from logger_setup import setup_logger

logger = setup_logger("SmartRackPoller")
auth_token = None

import re

def parse_stockcell(val: str) -> str:
    """Decode stockcell code. Format: XRRCC
    X  = side  (1=Left, 2=Right)
    RR = row   (01-12 -> A-L)
    CC = cell  (numeric, kept as-is)
    Example: 10135 -> Left A/35
    """
    if not val:
        return ""
    clean = re.sub(r'[^0-9]', '', val)
    if len(clean) < 5:
        return val  # can't parse, return original
    clean = clean[:5]  # take first 5 digits only

    side_digit = clean[0]
    side_char = "L" if side_digit == "1" else ("R" if side_digit == "2" else side_digit)

    try:
        row_num = int(clean[1:3])  # 01-12
        # chr(64+1) = 'A'
        letter  = chr(64 + row_num) if 1 <= row_num <= 26 else str(row_num).zfill(2)
    except ValueError:
        letter = clean[1:3]

    cell = clean[3:5]
    return f"{side_char}{letter}{cell}"

def login():
    """Authenticates against the API and returns the token."""
    global auth_token
    try:
        url = f"{config.API_BASE_URL}/"
        params = {
            "f": "login",
            "username": config.API_USERNAME,
            "password": config.API_PASSWORD
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        if root.get("err", "1") != "0":
            logger.error(f"Login failed: {root.get('errdesc', 'Unknown Error')}")
            return None
        
        token_el = root.find(".//token")
        if token_el is not None and token_el.text:
            auth_token = token_el.text.strip()
            logger.info("Successfully fetched auth token.")
            return auth_token
        else:
            logger.error("Token element not found in response.")
            return None
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        return None

def fetch_and_update_reels():
    """Polls the API for reels and updates the database."""
    global auth_token
    if not auth_token:
        # Try to login first if we don't have a token
        if not login():
            logger.warning("Skipping poll cycle because login failed.")
            return

    # In a real scenario, you can fetch the available SmartRacks IDs 
    # via V2_container_getlist, but we will iterate over hardcoded or typical IDs based on the lines config.
    # We will poll racks 1, 2, 3 as an example, but we could make it dynamic based on what's in the DB.
    # Since we need to know what racks exist, let's just query 1, 2, 3, 4, 5 for now.
    target_racks = ["1", "2", "3", "4", "5"]
    
    for rack_id in target_racks:
        try:
            url = f"{config.API_BASE_URL}/"
            params = {
                "f": "V2_reel_getlist",
                "filter_smartrackidlist": rack_id,
                "tkn": auth_token
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            # Token expiration check
            if root.get("err") != "0":
                errdesc = root.get("errdesc", "").lower()
                if "token" in errdesc or "auth" in errdesc:
                    logger.warning(f"Token seems expired/invalid: {errdesc}. Refreshing...")
                    if login():
                        # Retry once with new token
                        params["tkn"] = auth_token
                        response = requests.get(url, params=params, timeout=10)
                        response.raise_for_status()
                        root = ET.fromstring(response.content)
                    else:
                        continue
                else:
                    logger.error(f"API returned error for rack {rack_id}: {errdesc}")
                    continue
            
            reels_data = []
            for reel_info in root.findall(".//v2_reelinfo"):
                code_el = reel_info.find("code")
                itemcode_el = reel_info.find("itemcode")
                qty_el = reel_info.find("quantity")
                stockcell_el = reel_info.find("stockcell")
                
                if code_el is not None and code_el.text:
                    qty_val = 0.0
                    if qty_el is not None and qty_el.text:
                        try:
                            qty_val = float(qty_el.text)
                        except ValueError:
                            pass
                            
                    stockcell_val = stockcell_el.text.strip() if stockcell_el is not None and stockcell_el.text else ""
                            
                    reels_data.append({
                        "code": code_el.text.strip(),
                        "itemcode": itemcode_el.text.strip() if itemcode_el is not None and itemcode_el.text else "",
                        "qty": qty_val,
                        "stockcell": parse_stockcell(stockcell_val)
                    })
            
            # Upsert reels for this rack
            upsert_reels(reels_data, rack_id)
            # logger.info(f"Updated {len(reels_data)} reels for Rack ID {rack_id}")
            
        except Exception as e:
            logger.error(f"Error fetching reels for rack {rack_id}: {str(e)}")

def execute_extraction(name, reel_codes):
    """Executes V3_extractreels via API"""
    global auth_token
    if not auth_token:
        # Try to login first if we don't have a token
        if not login():
            return False, "Auth error"

    try:
        url = f"{config.API_BASE_URL}/"
        params = {
            "f": "V3_extractreels",
            "name": name,
            "reelrequestlist": ",".join(reel_codes),
            "autostart": "Y",
            "force_start": "Y",
            "tkn": auth_token
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        err = root.get("err", "1")
        if err != "0":
            return False, root.get("errdesc", "Unknown Error")
            
        return True, "Success"
    except Exception as e:
        logger.error(f"Error during extraction: {str(e)}")
        return False, str(e)
