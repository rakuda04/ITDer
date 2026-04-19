import xml.etree.ElementTree as ET
from datetime import datetime
import json
import re

import win32evtlog

# ==========================================
# 1. CORE ENGINE (The "How")
# ==========================================
def run_evt_query(path, event_id, days_back=1):
    # Calculate time for XPath (last X days)
    # 86400000 ms = 24 hours
    ms_limit = days_back * 86400000
    xpath = f"*[System[(EventID={event_id}) and TimeCreated[timediff(@SystemTime) <= {ms_limit}]]]"
    
    try:
        query_handle = win32evtlog.EvtQuery(
            path, 
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection,
            xpath
        )
        return win32evtlog.EvtNext(query_handle, 1000) # Get up to 1000 events
    except Exception as e:
        print(f"Query Error in {path}: {e}")
        return []

# ==========================================
# 2. LOG WRAPPERS (The "What")
# ==========================================
def get_umdf_events(event_id, days=1):
    path = "Microsoft-Windows-DriverFrameworks-UserMode/Operational"
    raw_events = run_evt_query(path, event_id, days)
    
    parsed_results = []
    ns = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}

    for event in raw_events:
        xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
        root = ET.fromstring(xml_str)
        
        # Extract and Normalize Time
        utc_str = root.find('.//ns:TimeCreated', ns).get('SystemTime')
        dt_obj = datetime.fromisoformat(utc_str.replace('Z', '+00:00')).astimezone()

        # Extract UMDF-specific data
        instance_node = root.find('.//{*}InstanceId')
        
        # Build the dictionary for this row
        log_entry = {
            "timestamp": dt_obj, # Keep as object for sorting
            "time_display": dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
            "event_id": event_id,
            "source": "UMDF",
            "device": instance_node.text if instance_node is not None else "N/A",
            "user": "SYSTEM" # UMDF usually runs as system
        }
        parsed_results.append(log_entry)
        
    return parsed_results #list of dictionaries

#print(json.dumps(get_umdf_events(2102), indent=2, default=str))

def get_security_events(event_id, days=1):
    # focus on longon type TYPE 2 PHYSICAL LOGON
    path = "Security"
    raw_events = run_evt_query(path, event_id, days)
    
    parsed_results = []
    # Note: EventData tags often ignore the 'ns' namespace, so we use {*} to match any namespace
    
    for event in raw_events:
        xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
        root = ET.fromstring(xml_str)
        
        # 1. Standard System Data
        utc_str = root.find('.//ns:TimeCreated', {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}).get('SystemTime')
        dt_obj = datetime.fromisoformat(utc_str.replace('Z', '+00:00')).astimezone()

        # 2. Extract Security Specific Data
        user_node = root.find('.//{*}Data[@Name="TargetUserName"]')
        user_name = user_node.text if user_node is not None else "N/A"
        
        # --- NEW: Extract Logon ID ---
        logon_id_node = root.find('.//{*}Data[@Name="TargetLogonId"]')
        logon_id = logon_id_node.text if logon_id_node is not None else "0x0"

        # 3. Build the dictionary
        log_entry = {
            "timestamp": dt_obj,
            "time_display": dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
            "event_id": event_id,
            "source": "Security",
            "device": "N/A",
            "user": user_name,
            "logon_id": logon_id # Added this field
        }
        parsed_results.append(log_entry)
        
    return parsed_results
print(json.dumps(get_security_events(4624), indent=2, default=str)) #test
    
# ==========================================
# 3. REFINERS / FILTERS (The "Cleaning")
# ==========================================
def refine_usb_only(log_list):
    # Regex for USBSTOR or common USB patterns
    # Case-insensitive to be safe
    usb_pattern = re.compile(r"USBSTOR|VID_|PID_", re.IGNORECASE) # be informed it also includes none usb too ie android (but it makes sense somewhat)
    
    # We use a list comprehension to keep it fast
    filtered_list = [
        entry for entry in log_list 
        if usb_pattern.search(entry['device'])
    ]
    
    return filtered_list

#  print(json.dumps(refine_usb_only(get_umdf_events(2102)), indent=2, default=str))

# ==========================================
# 4. AGGREGATOR & EXPORT (The "Output")
# ==========================================
def save_to_massive_csv(combined_data, filename):
    pass

if __name__ == "__main__":
    # This is your "Workflow Orchestrator"
    # Step 1: Get
    # Step 2: Filter
    # Step 3: Combine
    # Step 4: Save
    pass