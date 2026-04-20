import xml.etree.ElementTree as ET
from datetime import datetime
import json
import re

import win32evtlog

# ==========================================
# 1. CORE ENGINE (The "How")
# ==========================================
def run_evt_query(path, criteria, days_back=1):
    ms_limit = days_back * 86400000
    xpath = f"*[System[({criteria}) and TimeCreated[timediff(@SystemTime) <= {ms_limit}]]]"
    
    events = []
    try:
        query_handle = win32evtlog.EvtQuery(
            path, 
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection,
            xpath
        )
        
        while True:
            batch = win32evtlog.EvtNext(query_handle, 50)
            if not batch:
                break
            events.extend(batch)
            
    except Exception as e:
        pass
        
    return events

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

#print(json.dumps(get_umdf_events(2102), indent=2, default=str)) # NEEDS FIXING ##################################################

##temp placement ##
def is_system_account(username):
    system_patterns = ["SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE", "ANONYMOUS LOGON", "DWM-", "UMDF-", "UMFD-"]
    return any(pattern in username.upper() for pattern in system_patterns)

def get_security_events(criteria="EventID=4624 or EventID=4634", days=1):
    path = "Security"
    raw_events = run_evt_query(path, criteria, days) # Assuming your existing function
    
    parsed_results = []
    ns = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}
    
    for event in raw_events:
        xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
        root = ET.fromstring(xml_str)
        
        user_node = root.find('.//{*}Data[@Name="TargetUserName"]')
        user_name = user_node.text if user_node is not None else "N/A"
        
        if is_system_account(user_name): continue
            
        eid = int(root.find('.//ns:EventID', ns).text)
        
        # Filter for Interactive/Network Logons only
        if eid == 4624:
            logon_type = root.find('.//{*}Data[@Name="LogonType"]').text
            if logon_type not in ['2', '3', '7', '10', '11']: continue
                
        parsed_results.append({
            "event_id": eid,
            "user": user_name,
            "timestamp": root.find('.//ns:TimeCreated', ns).get('SystemTime'),
            "logon_id": root.find('.//{*}Data[@Name="TargetLogonId"]').text
        })
    
    return sorted(parsed_results, key=lambda x: x['timestamp'])
print(json.dumps(get_security_events(), indent=2, default=str)) #test
    
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

