 what is the goal ? 

AI features:
USB connections
Logon time (configurable by the admin)
Email 

 get data that happened within the day works on startup 

 check log file if it exsists or not: if it does overwrite it with todays logs


 write 

 try testing automated
 end at the end of the day / send total logs of yesterday
 setup usb logs
 limiting amount sent by period

 problems:
 it prints 3 copies
 usb disconnect isnt recognized

 try to figure out how to find event 1010 as it signifies usb disconnect  

 look at log 2012
 :try to connect usbs together



reached solution
 most reliable so far is **Applications and Services Logs > Microsoft > Windows > DriverFrameworks-UserMode > Operational.** ✓

 look for USBSTOR & filter logs to take only  1 2102 log per 3 seconds 
 ---

 Component	Responsibility
fetch_win_logs(channel, event_id)	Queries Windows for a specific ID and returns raw data as a list of dicts.
fetch_external_logs(path)	(Optional) If you have logs from a text file or another tool, this reads them into the same dict format.
filter_by_date(logs, target_date)	Takes a list of logs and keeps only those where the date matches "Today."
generate_csv(combined_logs, filename)	Sorts the combined list by time descending and saves to CSV.