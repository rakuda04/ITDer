## features to focus on 


session_duration          # Logoff timestamp - Logon timestamp
after_hours_session       # session start/end outside 8am-6pm
weekend_session           # any session on Sat/Sun
logon_count_day           # total logons per day
pc_count_day              # distinct PCs logged into same day (multistation)

usb_connect_count_day     # connects per day
usb_after_hours           # connect outside business hours
usb_on_weekend            # connect on Sat/Sun
device_diversity          # distinct device IDs per user per month
days_since_last_usb       # recency signal

file_count_day            # files touched per day
unique_extensions_day     # distinct file types accessed (.pdf, .docx, .zip)
executable_access_flag    # any .exe/.bat/.ps1 access
archive_creation_flag     # any .zip/.rar creation — staging signal
off_hours_file_access     # file activity outside business hours

domains_visited_day       # distinct domains
upload_activity_flag      # POST requests or known upload domains (dropbox, wetransfer)
job_site_visits           # visits to linkedin/indeed/glassdoor — flight risk proxy
off_hours_browsing        # web activity outside business hours

emails_sent_day           # volume
external_email_ratio      # external recipients / total sent
attachment_size_total     # total MB sent as attachments per day
after_hours_email         # sent outside business hours
personal_domain_flag      # sent to gmail/yahoo/hotmail

usb_plus_afterhours_file      # device connect AND file access same after-hours window
job_search_plus_usb_week      # job site visits in same week as USB spike
external_email_plus_archive   # archive created AND sent to external/personal email same day
multistation_plus_usb         # multiple PCs in one day AND USB connect

# Session
total_active_minutes_day
after_hours_session_count
weekend_session_flag
logon_count_zscore

# USB
usb_count_zscore
usb_after_hours_flag
usb_on_weekend_flag
device_diversity_monthly
days_since_last_usb

# HTTP
upload_activity_flag
job_site_visits_flag

# Email (CERT only)
emails_sent_zscore
external_email_ratio
personal_domain_flag

# Compound
job_search_plus_usb_week

into -----------------------------

# Session
total_active_minutes_day
after_hours_session_count
weekend_session_flag
logon_count_zscore

# USB
usb_count_zscore
usb_after_hours_flag
usb_on_weekend_flag
usb_device_diversity_monthly
days_since_last_usb

# HTTP
upload_activity_flag
job_site_visits_flag


# Compound
job_search_plus_usb_week