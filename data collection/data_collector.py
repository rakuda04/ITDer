import xml.etree.ElementTree as ET
from datetime import datetime
import json
import re
import win32evtlog
import csv

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
# ==========================================        usb all good EventID=2003,  or EventID=2102 and 2100 (contains dupes)
def get_umdf_events(criteria="EventID=2003 or EventID=2100 or EventID=2102", days=1): # 2003 ( device connection) 2102(graceful exit) 2100(suprise removal)
    path = "Microsoft-Windows-DriverFrameworks-UserMode/Operational" #use operational but filter based on 1 log in sec
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
            "event_id": eid,
            "source": "UMDF",
            "device": instance_node.text if instance_node is not None else "N/A",
            "user": "SYSTEM" # UMDF usually runs as system
        }
        parsed_results.append(log_entry)
        
    return sorted(parsed_results, key=lambda x: x['timestamp'])

#print(json.dumps(get_umdf_events(), indent=2, default=str)) 




 # this event/s needs to be turned on manually and doesnt not account for boot login (CREATE SCRIPT) events to be turned on manually 4801,4800
 #AHHHHHHHHHHHHH BIG BRAIN MOMENT!!!! SO WHEN THE PROGRAM RUNS LOG A STARTUP LOGIN EVENT AT THE CURRENT TIME 
 
 # 1074(system) for shutdown,
#  lock unlock ,logoff is shutdown, startup is boot

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
        "timestamp": datetime.now().astimezone(),
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
                "timestamp": dt_obj,
                "logon_id": event_data.get('TargetLogonId', 'n/a')
            })
    
    return sorted(parsed_results, key=lambda x: x['timestamp'])
# print(json.dumps(get_security_events(), indent=2, default=str))
    
    
# ==========================================
# 3. REFINERS / FILTERS 
# ==========================================
def refine_usb_only(log_list):
    # Regex for USBSTOR or  USB patterns
    usb_pattern = re.compile(r"USBSTOR|VID_|PID_", re.IGNORECASE) # be informed it also includes none usb too ie android (but it makes sense somewhat)
    
    filtered_list = [
        entry for entry in log_list 
        if usb_pattern.search(entry['device'])
    ]
    
    return filtered_list

# print(json.dumps(refine_usb_only(get_umdf_events()), indent=2, default=str))

def filter_usb_duplicates(log_list):
    if not log_list:
        return []

    unique_logs = []
    # Tracks the last kept log for each specific device ID
    last_usb_state = {} 

    # 1. Sort the combined list chronologically
    sorted_logs = sorted(log_list, key=lambda x: x['timestamp'])

    for entry in sorted_logs:
        # Check if this is a UMDF/USB event
        is_usb = 'device' in entry
        
        if is_usb:
            # Assign Category
            entry['category'] = "CONNECT" if entry['event_id'] == 2003 else "DISCONNECT"
            dev_id = entry['device']
            
            # Check if we have seen this specific device before
            if dev_id in last_usb_state:
                prev = last_usb_state[dev_id]
                time_diff = (entry['timestamp'] - prev['timestamp']).total_seconds()
                
                # --- Condition A: Filter Identical Duplicates ---
                if (entry['category'] == prev['category'] and abs(time_diff) <= 1.5):
                    continue

                # --- Condition B: Filter "Phantom" Bounces ---
                if (prev['category'] == "CONNECT" and 
                    entry['category'] == "DISCONNECT" and 
                    abs(time_diff) < 0.5):
                    continue
            
            # Update the last seen state for this specific device
            last_usb_state[dev_id] = entry

        # Always keep Security events, and keep USB events that passed the filters
        unique_logs.append(entry)
        
    return unique_logs
            

# print(json.dumps(filter_usb_duplicates(refine_usb_only(get_umdf_events())), indent=2, default=str))




# ==========================================
# 4. AGGREGATOR & EXPORT 
# ==========================================

def get_all_combined_events(days=1):
    umdf_data = get_umdf_events(days=days)
    security_data = get_security_events(days=days)
    
    combined = umdf_data + security_data
    
    combined.sort(key=lambda x: x['timestamp'])
    
    return combined

# print(json.dumps(get_all_combined_events(), indent=2, default=str))




def save_to_massive_csv(combined_data, filename="combined_events.csv"):
    if not combined_data:
        print("No data to save.")
        return

    # Define the columns that will be written to the CSV file.
    fieldnames = ["timestamp", "event_id", "source", "device", "user", "activity", "logon_id", "category"]

    try:
        with open(filename, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            
            for entry in combined_data:
                # Create a row, ensuring missing keys default to an empty string
                row = {field: entry.get(field, "") for field in fieldnames}
                
                # Convert the datetime object back to a string for CSV storage
                if isinstance(row["timestamp"], datetime):
                    row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f%z")
                    
                writer.writerow(row)
                
        print(f"Successfully saved {len(combined_data)} events to {filename}")
        
    except Exception as e:
        print(f"Error saving CSV: {e}")
        
        

if __name__ == "__main__":

    # 1. Gather all events from both sources (Security + UMDF)
    print("Gathering combined logs...")
    raw_data = get_all_combined_events(days=1)
    
    # 2. Filter out duplicates and rapid connection bounces
    print("Filtering duplicates and noise...")
    clean_data = filter_usb_duplicates(raw_data)
    
    # 3. Save directly to CSV
    print("Writing to CSV...")
    save_to_massive_csv(clean_data, filename="usb_security_log_report.csv")
    

