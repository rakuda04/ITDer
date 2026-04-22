import xml.etree.ElementTree as ET
from datetime import datetime
import json
import re
import win32evtlog

# ==========================================
# 1. CORE ENGINE
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
       print(f"DEBUG: Error reading event log: {e}") 
        
    return events

# ==========================================
# 2. LOG WRAPPERS 
# ==========================================
def get_umdf_events(criteria="EventID=2102", days=1):
    path = "Microsoft-Windows-DriverFrameworks-UserMode/Operational"
    raw_events = run_evt_query(path, criteria, days)
    
    parsed_results = []
    ns = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}

    for event in raw_events:
        xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
        root = ET.fromstring(xml_str)
        eid = int(root.find('.//ns:EventID', ns).text)
        # Extract and Normalize Time
        utc_str = root.find('.//ns:TimeCreated', ns).get('SystemTime')
        dt_obj = datetime.fromisoformat(utc_str.replace('Z', '+00:00')).astimezone()

        # Extract UMDF-specific data
        instance_node = root.find('.//{*}InstanceId')
        
        # Build the dictionary for this row
        log_entry = {
            "timestamp": dt_obj, # Keep as object for sorting
            "time_display": dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
            "event_id": eid,
            "source": "UMDF",
            "device": instance_node.text if instance_node is not None else "N/A",
            "user": "SYSTEM" # UMDF usually runs as system
        }
        parsed_results.append(log_entry)
        
    return parsed_results 

#print(json.dumps(get_umdf_events(2102), indent=2, default=str)) # NEEDS FIXING ##################################################




 # this event/s needs to be turned on manually and doesnt not account for boot login (FIX THIS) events to be turned on manually 4801,4800
 #AHHHHHHHHHHHHH BIG BRAIN MOMENT!!!! SO WHEN THE PROGRAM RUNS LOG A STARTUP LOGIN EVENT AT THE CURRENT TIME 
 
 # 1074(system) for shutdown,
#  lock unlock works,logoff is shutdown, startup is boot

def get_security_events(days=1):
    parsed_results = []
    
        # Define which IDs belong to which Log Path
    EVENT_CONFIG = {
        "Security": {
            "ids": [4624, 4800, 4801],
            "labels": {4624: "LOGON", 4800: "LOCK", 4801: "UNLOCK"}
        },
        "System": {
            "ids": [1074, 42, 107],
            "labels": {1074: "LOGOFF(shutdown)", 42: "SLEEP", 107: "WAKE"}
        }
    }
    
    #  Manual the Startup Event
    parsed_results.append({
        "event_id": 4624, 
        "activity": "LOGON(manual startup)",
        "user": "current_user", 
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "logon_id": "n/a"
    })
    
    # 2. Iterate through each log type
    for log_path, config in EVENT_CONFIG.items():
        # Build criteria (e.g., "EventID=4800 or EventID=4801")
        criteria = " or ".join([f"EventID={eid}" for eid in config['ids']])
        
        # Run query specific to this log path
        raw_events = run_evt_query(log_path, criteria, days)
        
        ns = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}
        
        # Parse logs
        for event in raw_events:
            xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
            root = ET.fromstring(xml_str)
            eid = int(root.find('.//ns:EventID', ns).text)
            
            # Extract data nodes
            data_nodes = root.findall('.//ns:Data', ns)
            event_data = {node.get('Name'): node.text for node in data_nodes if node.get('Name')}
            
            # Extract time
            utc_str = root.find('.//ns:TimeCreated', ns).get('SystemTime')
            dt_obj = datetime.fromisoformat(utc_str.replace('Z', '+00:00')).astimezone()
            
            parsed_results.append({
                "event_id": eid,
                "activity": config['labels'].get(eid, "OTHER"),
                "user": event_data.get('TargetUserName', 'n/a').lower(),
                "timestamp": dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
                "logon_id": event_data.get('TargetLogonId', 'n/a')
            })
    
    return sorted(parsed_results, key=lambda x: x['timestamp'])
# print(json.dumps(get_security_events(), indent=2, default=str))
    
    
# ==========================================
# 3. REFINERS / FILTERS 
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

print(json.dumps(refine_usb_only(get_umdf_events()), indent=2, default=str))





# ==========================================
# 4. AGGREGATOR & EXPORT 
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

