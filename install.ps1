# ============================================================
# install.ps1  —  ITDer Local Pipeline Installer
#
# Run once on each Windows device as Administrator.
# Does the following:
#   1. Checks prerequisites (Python, pip)
#   2. Enables required Windows audit policies + event log
#   3. Downloads pipeline files from GitHub
#   4. Installs Python dependencies
#   5. Sets ITDER_API_URL as a system environment variable
#   6. Registers a Task Scheduler job to run on startup
#
# Usage:
#   Right-click PowerShell -> Run as Administrator
#   .\install.ps1
# ============================================================

# ── config ───────────────────────────────────────────────────
$REPO_BASE   = "https://raw.githubusercontent.com/rakuda04/ITDer/main/local_pipeline"
$INSTALL_DIR = "C:\ProgramData\itder"
$TASK_NAME   = "ITDer Pipeline"
$PYTHON      = "python"
# ─────────────────────────────────────────────────────────────

# ── prompt for API URL ────────────────────────────────────────
Add-Type -AssemblyName Microsoft.VisualBasic
$API_URL = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Enter the ITDer API URL (e.g. https://your-tunnel.yourdomain.com)",
    "ITDer Installer",
    "https://"
)
if ([string]::IsNullOrWhiteSpace($API_URL)) {
    Fail "No API URL entered. Installation cancelled."
}

$ErrorActionPreference = "Stop"

function Log($msg) {
    Write-Host "[itder] $msg" -ForegroundColor Cyan
}

function Fail($msg) {
    Write-Host "[itder] ERROR: $msg" -ForegroundColor Red
    exit 1
}

# ── 0. must run as admin ─────────────────────────────────────
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Fail "Please run this script as Administrator."
}

# ── 1. check Python ──────────────────────────────────────────
Log "Checking Python..."
try {
    $pyver = & $PYTHON --version 2>&1
    Log "Found $pyver"
} catch {
    Fail "Python not found. Install Python 3.9+ from https://python.org and try again."
}

# ── 2. enable Windows audit policies ────────────────────────
Log "Enabling Windows audit policies..."

# Logon events (Event IDs 4624, 4800, 4801)
auditpol /set /subcategory:"Logon" /success:enable /failure:enable | Out-Null

# Other logon/logoff events
auditpol /set /subcategory:"Other Logon/Logoff Events" /success:enable | Out-Null

# Enable UMDF operational log (USB events 2003, 2100, 2102)
Log "Enabling UMDF event log (USB tracking)..."
wevtutil sl "Microsoft-Windows-DriverFrameworks-UserMode/Operational" /e:true | Out-Null

Log "Audit policies enabled."

# ── 3. create install directory ──────────────────────────────
Log "Creating $INSTALL_DIR..."
$dirs = @(
    $INSTALL_DIR,
    "$INSTALL_DIR\output",
    "$INSTALL_DIR\collectors",
    "$INSTALL_DIR\processors"
)
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# ── 4. download pipeline files ───────────────────────────────
Log "Downloading pipeline files from GitHub..."

$files = @(
    "config.py",
    "data_collector.py",
    "local_preprocessor.py",
    "inference.py",
    "synthetic_generator.py",
    "send_to_server.py",
    "collectors/browser_history.py",
    "collectors/windows_events.py",
    "processors/filters.py"
)

foreach ($file in $files) {
    $url     = "$REPO_BASE/$file"
    $dest    = "$INSTALL_DIR\$($file -replace '/', '\')"
    Log "  $file"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    } catch {
        Fail "Failed to download $file. Check your internet connection and that the repo is public."
    }
}

# create __init__.py files so Python treats subdirs as packages
"" | Out-File "$INSTALL_DIR\collectors\__init__.py" -Encoding utf8
"" | Out-File "$INSTALL_DIR\processors\__init__.py" -Encoding utf8

Log "Files downloaded."

# ── 5. install Python dependencies ───────────────────────────
Log "Installing Python dependencies..."
$deps = @("pandas", "requests", "pywin32", "scikit-learn", "numpy")
foreach ($dep in $deps) {
    Log "  pip install $dep"
    & $PYTHON -m pip install $dep --quiet
    if ($LASTEXITCODE -ne 0) {
        Fail "Failed to install $dep."
    }
}
Log "Dependencies installed."

# ── 6. set system environment variable ───────────────────────
Log "Setting ITDER_API_URL system environment variable..."
[System.Environment]::SetEnvironmentVariable("ITDER_API_URL", $API_URL, "Machine")
Log "ITDER_API_URL = $API_URL"

# ── 7. create the runner script ──────────────────────────────
Log "Creating pipeline runner..."
$runner = @"
import subprocess
import sys
import os

os.chdir(r"$INSTALL_DIR")
scripts = [
    "data_collector.py",
    "local_preprocessor.py",
    "inference.py",
    "send_to_server.py",
]
for script in scripts:
    print(f"[itder] Running {script}...")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"[itder] {script} failed: {result.stderr}")
        sys.exit(1)

print("[itder] Pipeline complete.")
"@
$runner | Out-File "$INSTALL_DIR\run_pipeline.py" -Encoding utf8

# ── 8. register Task Scheduler job ───────────────────────────
Log "Registering startup task in Task Scheduler..."

$pythonPath = & $PYTHON -c "import sys; print(sys.executable)"
$action     = New-ScheduledTaskAction -Execute $pythonPath -Argument "$INSTALL_DIR\run_pipeline.py" -WorkingDirectory $INSTALL_DIR
$trigger    = New-ScheduledTaskTrigger -AtStartup
$settings   = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
$principal  = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# remove existing task if present
if (Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

Register-ScheduledTask -TaskName $TASK_NAME -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null

Log "Task '$TASK_NAME' registered — runs at every startup as SYSTEM."

# ── done ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host "  ITDer installed successfully." -ForegroundColor Green
Write-Host "  Pipeline will run on next startup." -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Log "To test now without rebooting, run:"
Write-Host "  python $INSTALL_DIR\run_pipeline.py" -ForegroundColor Yellow
