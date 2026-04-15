import win32evtlog
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def get_latest_umdf_logs(count=10):
    path = "Microsoft-Windows-DriverFrameworks-UserMode/Operational"
    
    try:
        # Create fresh query handle
        query_handle = win32evtlog.EvtQuery(
            path, 
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection
        )
    except Exception as e:
        print(f"Failed to connect to log: {e}")
        return

    events = win32evtlog.EvtNext(query_handle, count)
    
    print(f"--- Showing last {len(events)} UMDF events (Local Time) ---\n")

    for event in events:
        # Render the event to XML string
        xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
        root = ET.fromstring(xml_str)
        
        # Namespace for System elements
        ns = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}
        
        # 1. Parse Time and Convert to Local
        utc_time_str = root.find('.//ns:TimeCreated', ns).get('SystemTime')
        # Handle the ISO string and convert UTC to Local
        dt_utc = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
        local_time = dt_utc.astimezone().strftime('%Y-%m-%d %H:%M:%S')

        # 2. Extract Basic Info
        event_id = root.find('.//ns:EventID', ns).text
        
        # 3. Extract UMDF Specific Data (Instance ID & Status)
        # Using {*} to ignore specific UserData namespaces which vary by event
        instance_node = root.find('.//{*}InstanceId')
        status_node = root.find('.//{*}Status')
        
        instance_id = instance_node.text if instance_node is not None else "N/A"
        status_code = status_node.text if status_node is not None else "0"

        # Print the results
        print(f"[{local_time}]")
        print(f"Event ID:  {event_id}")
        print(f"Device:    {instance_id}")
        if status_code != "0":
            print(f"Status:    {status_code} (Error/Warning)")
        print("-" * 60)

if __name__ == "__main__":
    # Reminder: Run as Administrator to ensure live buffer access
    get_latest_umdf_logs(10)