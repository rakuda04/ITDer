import os
import win32evtlog
from datetime import datetime, date

# --- PATH LOGIC ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "today_audit.txt")

def track_today_only():
    server = 'localhost'
    log_type = 'Security'
    today = date.today() # Get current date (Year, Month, Day)
    
    # Check if file exists and overwrite it ('w' mode clears the file)
    # If it doesn't exist, 'w' will create it.
    mode = 'w' 
    
    try:
        hand = win32evtlog.OpenEventLog(server, log_type)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        
        print(f"Filtering logs for: {today}")
        
        with open(LOG_FILE, mode, encoding="utf-8") as f:
            f.write(f"--- ACTIVITY LOG FOR {today} ---\n\n")
            
            # Read in chunks to avoid memory issues
            while True:
                events = win32evtlog.ReadEventLog(hand, flags, 0)
                if not events:
                    break
                
                for event in events:
                    # Check the date of the event
                    event_date = event.TimeGenerated.date()
                    
                    # If the event is older than today, stop looking (since we read backwards)
                    if event_date < today:
                        break
                    
                    # Only process if it happened TODAY
                    if event_date == today:
                        event_id = event.EventID & 0xFFFF
                        if event_id == 4624: # Logon
                            data = event.StringInserts
                            if data and len(data) > 8:
                                user = data[5]
                                logon_type = data[8]
                                
                                # Filter for Human Activity
                                if logon_type in ['2', '7', '10', '11',"5"]:
                                    time_str = event.TimeGenerated.strftime("%H:%M:%S")
                                    f.write(f"[{time_str}] USER: {user} | TYPE: {logon_type}\n")

                # Double check to break the 'while' loop if we've passed today's dates
                if events[-1].TimeGenerated.date() < today:
                    break
                    
        print(f"Successfully overwritten {LOG_FILE} with today's logs.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    track_today_only()