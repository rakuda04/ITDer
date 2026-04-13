import os
import win32evtlog
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "live_cert_device.csv")

def track_all_security_events():
    server = 'localhost'
    log_type = 'Security'
    today = date.today()
    
    try:
        hand = win32evtlog.OpenEventLog(server, log_type)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        
        print(f"Scanning Security log for CERT events on: {today}")
        
        with open(CSV_FILE, 'w', encoding="utf-8") as f:
            f.write("id,date,user,pc,activity\n")
            
            id_counter = 1
            
            while True:
                events = win32evtlog.ReadEventLog(hand, flags, 0)
                if not events:
                    break
                
                for event in events:
                    if event.TimeGenerated.date() < today:
                        break # Stop if we pass today's logs
                        
                    event_id = event.EventID & 0xFFFF
                    data = event.StringInserts
                    
                    activity = ""
                    user = "Unknown"
                    
                    # 1. Look for Logons
                    if event_id == 4624:
                        logon_type = data[8] if (data and len(data) > 8) else "N/A"
                        if logon_type in ['2', '7', '10', '11']:
                            activity = "Logon"
                            user = data[5] if (data and len(data) > 5) else "N/A"
                            
                    # 2. Look for Logoffs
                    elif event_id == 4634:
                        activity = "Logoff"
                        user = data[1] if (data and len(data) > 1) else "N/A"
                        
                    # 3. Look for YOUR USB EVENT (6416)
                    elif event_id == 6416:
                        # Safely get the Device ID (usually at data[4] or data[5] depending on OS)
                        # Let's search the whole data payload for the keyword 'USBSTOR'
                        data_string = "".join(data).upper() if data else ""
                        
                        if "USBSTOR" in data_string:
                            activity = "Connect"
                            user = data[1] if (data and len(data) > 1) else "SYSTEM"
                            
                            # Optional: You can extract the brand/serial if you want!
                            # Example: USBSTOR\DISK&VEN_SANDISK&PROD_CRUZER...
                        else:
                            # It's a mouse, keyboard, or headset. Skip it!
                            continue
                    
                    # If we found an activity we care about, write it!
                    if activity:
                        date_str = event.TimeGenerated.strftime("%m/%d/%Y %H:%M:%S")
                        pc_name = event.ComputerName
                        fake_id = f"{{LIVE-EVT-{id_counter}}}"
                        id_counter += 1
                        
                        f.write(f"{fake_id},{date_str},{user},{pc_name},{activity}\n")
                        print(f"Mapped: {user} performed {activity} at {date_str}")
                        
                if events[-1].TimeGenerated.date() < today:
                    break
                    
        print(f"Complete! Check your folder for {CSV_FILE}")

    except Exception as e:
        print(f"Error: {e}. Are you running VS Code as Admin?")

if __name__ == "__main__":
    track_all_security_events()