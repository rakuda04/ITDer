"""
installer.py  —  ITDer Local Pipeline Installer
Compile to exe with: pyinstaller --onefile --uac-admin --noconsole installer.py
"""

import os
import sys
import subprocess
import shutil
import urllib.request
import winreg
import ctypes
import tkinter as tk
from tkinter import messagebox, simpledialog

# ── config ───────────────────────────────────────────────────
REPO_BASE    = "https://raw.githubusercontent.com/rakuda04/ITDer/main/dist/local"
INSTALL_DIR  = r"C:\ProgramData\itder"

FILES = [
    "config.py",
    "data_collector.py",
    "local_preprocessor.py",
    "send_to_server.py",
    "collectors/browser_history.py",
    "collectors/windows_events.py",
    "processors/filters.py",
]

# install order matters — numpy must be pinned before shap
DEPS = [
    ["pandas", "requests", "pywin32", "scikit-learn"],
    ["numpy", "shap"],
]
# ─────────────────────────────────────────────────────────────

RUNNER_SCRIPT = """\
import subprocess, sys, os
from datetime import datetime
import urllib.request
import json

os.chdir(r"{install_dir}")
log_file = r"{install_dir}\\pipeline.log"

# Read api_url.txt if it exists, otherwise fall back to default
api_url_file = r"{install_dir}\\api_url.txt"
if os.path.exists(api_url_file):
    try:
        with open(api_url_file, "r") as f:
            api_url = f.read().strip()
    except Exception:
        api_url = "https://your-tunnel.yourdomain.com"
else:
    api_url = "https://your-tunnel.yourdomain.com"

api_url = api_url.rstrip("/") + "/api/telemetry"

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"[{{datetime.now()}}] {{msg}}\\n")
    print(msg)
    try:
        req = urllib.request.Request(
            api_url,
            data=json.dumps({{"source": "agent", "message": msg}}).encode("utf-8"),
            headers={{"Content-Type": "application/json"}},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2):
            pass
    except Exception:
        pass

log("Pipeline started")
scripts = [
    "data_collector.py",
    "local_preprocessor.py",
    "send_to_server.py",
]
for script in scripts:
    log(f"Running {{script}}...")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True, errors="replace")
    log(result.stdout)
    if result.returncode != 0:
        log(f"FAILED: {{script}}\\n{{result.stderr}}")
        sys.exit(1)

log("Pipeline complete.")
""".format(install_dir=INSTALL_DIR)


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def log(msg):
    print(f"[itder] {msg}")
    try:
        os.makedirs(r"C:\ProgramData", exist_ok=True)
        with open(r"C:\ProgramData\itder_install_log.txt", "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass



def fail(msg):
    log(f"ERROR: {msg}")
    messagebox.showerror("ITDer Installer", f"Installation failed:\n\n{msg}")
    sys.exit(1)



def check_python():
    log("Checking Python...")
    paths = []
    try:
        result = subprocess.run(["where", "python"], capture_output=True, text=True, errors="replace")
        if result.returncode == 0:
            paths = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
    except Exception:
        pass

    if not paths:
        py = shutil.which("python") or shutil.which("python3")
        if py:
            paths = [py]

    # Filter out Windows Store app execution aliases containing 'WindowsApps'
    real_py = None
    for p in paths:
        if "windowsapps" not in p.lower():
            real_py = p
            break

    if not real_py and paths:
        real_py = paths[0]

    # Fallback to sys.executable if it is running in Python (and not compiled EXE)
    if not real_py or "windowsapps" in real_py.lower():
        if "python" in os.path.basename(sys.executable).lower():
            real_py = sys.executable

    if not real_py:
        fail("Python not found. Install Python 3.9+ from https://python.org and try again.")

    result = subprocess.run([real_py, "--version"], capture_output=True, text=True, errors="replace")
    log(f"Found Python: {real_py} ({result.stdout.strip()})")
    return real_py



def enable_audit_policies():
    log("Enabling Windows audit policies...")
    cmds = [
        ["auditpol", "/set", "/subcategory:Logon", "/success:enable", "/failure:enable"],
        ["auditpol", "/set", "/subcategory:Other Logon/Logoff Events", "/success:enable"],
        ["wevtutil", "sl", "Microsoft-Windows-DriverFrameworks-UserMode/Operational", "/e:true"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if result.returncode != 0:
            log(f"Warning: {' '.join(cmd)} returned {result.returncode}: {result.stderr.strip()}")
    log("Audit policies enabled.")


def create_directories():
    log(f"Creating install directories...")
    dirs = [
        INSTALL_DIR,
        os.path.join(INSTALL_DIR, "output"),
        os.path.join(INSTALL_DIR, "collectors"),
        os.path.join(INSTALL_DIR, "processors"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def download_files():
    # 1. Try copying from public temp directory first (avoids UAC OneDrive access issues)
    local_src_dir = r"C:\Users\Public\Documents\itder_temp"
    if not os.path.exists(local_src_dir):
        # Fallback to local repository directory
        local_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "local_pipeline")
        if not os.path.exists(local_src_dir):
            local_src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_pipeline")

    if os.path.exists(local_src_dir):

        log("Found local pipeline source files. Copying locally instead of downloading...")
        for file in FILES:
            src = os.path.join(local_src_dir, file.replace("/", os.sep))
            dest = os.path.join(INSTALL_DIR, file.replace("/", os.sep))
            log(f"  Copying {file} -> {dest}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                shutil.copy2(src, dest)
                with open(dest, "r", encoding="utf-8") as f:
                    content = f.read()
                if "dist.local." in content:
                    content = content.replace("dist.local.", "")
                    with open(dest, "w", encoding="utf-8") as f:
                        f.write(content)
            except Exception as e:
                fail(f"Failed to copy local file {file}:\n{e}")
        
        for subdir in ["collectors", "processors"]:
            init = os.path.join(INSTALL_DIR, subdir, "__init__.py")
            open(init, "w").close()
            
        log("All local files copied and imports patched.")
        return

    log("Downloading pipeline files from GitHub...")
    for file in FILES:
        url  = f"{REPO_BASE}/{file}"
        dest = os.path.join(INSTALL_DIR, file.replace("/", os.sep))
        log(f"  {file}")
        try:
            urllib.request.urlretrieve(url, dest)
            
            # --- AUTO-FIX IMPORTS ---
            # Read the newly downloaded file
            with open(dest, "r", encoding="utf-8") as f:
                content = f.read()
            
            # If the file contains the GitHub folder path in its imports, strip it out
            if "dist.local." in content:
                content = content.replace("dist.local.", "")
                
                # Write the corrected content back to the file
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(content)
                    
        except Exception as e:
            fail(f"Failed to download {file}:\n{e}\n\nCheck your internet connection.")

    for subdir in ["collectors", "processors"]:
        init = os.path.join(INSTALL_DIR, subdir, "__init__.py")
        open(init, "w").close()

    log("All files downloaded and imports patched.")



def install_dependencies(python_exe):
    log("Installing Python dependencies...")
    for batch in DEPS:
        log(f"  pip install {' '.join(batch)}")
        result = subprocess.run(
            [python_exe, "-m", "pip", "install"] + batch + ["--quiet"],
            capture_output=True, text=True, errors="replace"
        )
        if result.returncode != 0:
            fail(f"Failed to install {batch}:\n{result.stderr}")

    # pywin32 requires a post-install step to register its DLLs
    log("Running pywin32 post-install...")
    scripts_dir = os.path.join(os.path.dirname(python_exe), "Scripts")
    post_install = os.path.join(scripts_dir, "pywin32_postinstall.py")
    result = subprocess.run(
        [python_exe, post_install, "-install"],
        capture_output=True, text=True, errors="replace"
    )
    if result.returncode != 0:
        log(f"Warning: pywin32 post-install failed: {result.stderr.strip()}")
    else:
        log("pywin32 post-install complete.")

    log("Dependencies installed.")


def set_env_variables():
    log("Setting system environment variables...")
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, "PYTHONUTF8",    0, winreg.REG_SZ, "1")
    winreg.CloseKey(key)
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None)
    log("PYTHONUTF8 = 1")


def create_runner():
    log("Creating pipeline runner...")
    runner_path = os.path.join(INSTALL_DIR, "run_pipeline.py")
    with open(runner_path, "w") as f:
        f.write(RUNNER_SCRIPT)


def register_startup(python_exe):
    log("Registering startup entry in Windows Task Scheduler...")
    runner = os.path.join(INSTALL_DIR, "run_pipeline.py")
    
    # Use pythonw.exe (windowless) to run without flashing a terminal window
    pythonw_exe = python_exe.lower().replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        pythonw_exe = python_exe
    
    # 1. Clean up legacy registry key if it exists to avoid running twice
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        try:
            winreg.DeleteValue(key, "ITDerPipeline")
            log("Removed legacy registry startup entry.")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass

    # 2. Register startup task in Task Scheduler using schtasks
    # We run it under the INTERACTIVE principal with highest privileges (administrator) on logon.
    cmd = [
        "schtasks", "/create", "/tn", "ITDerPipeline",
        "/tr", f'"{pythonw_exe}" "{runner}"',
        "/sc", "onlogon", "/ru", "INTERACTIVE", "/rl", "highest", "/f"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        fail(f"Failed to register startup task in Task Scheduler:\n{result.stderr.strip()}")
        
    # 3. Configure Task Settings (Allow running on batteries) using PowerShell
    try:
        ps_cmd = [
            "powershell", "-NoProfile", "-Command",
            'Set-ScheduledTask -TaskName "ITDerPipeline" -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)'
        ]
        ps_result = subprocess.run(ps_cmd, capture_output=True, text=True, errors="replace")
        if ps_result.returncode != 0:
            log(f"Warning: Failed to configure battery settings for task: {ps_result.stderr.strip()}")
        else:
            log("Configured task settings to allow battery operation.")
    except Exception as e:
        log(f"Warning: Exception configuring task settings: {e}")
        
    log("Startup entry registered in Task Scheduler successfully.")




def save_api_url_file(api_url):
    log("Saving API URL to api_url.txt...")
    config_path = os.path.join(INSTALL_DIR, "api_url.txt")
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(api_url.strip())
        log(f"Saved API URL to {config_path}")
    except Exception as e:
        log(f"Warning: Could not save API URL file: {e}")


def main():
    # auto-elevate — triggers UAC prompt on double-click
    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = [script] + sys.argv[1:]
        params_str = " ".join(f'"{p}"' for p in params)
        cwd = os.getcwd()
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params_str, cwd, 1
        )
        sys.exit(0)

    #  Clear/reset the install log
    try:
        if os.path.exists(r"C:\ProgramData\itder_install_log.txt"):
            os.remove(r"C:\ProgramData\itder_install_log.txt")
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()

    api_url = simpledialog.askstring(
        "ITDer Installer",
        "Enter the ITDer API URL:",
        initialvalue="http://localhost:8000",
        parent=root
    )
    if not api_url or api_url.strip() in ["http://", "https://"]:
        messagebox.showwarning("ITDer Installer", "No API URL entered. Installation cancelled.")
        sys.exit(0)
    api_url = api_url.strip()

    try:
        python_exe = check_python()
        enable_audit_policies()
        create_directories()
        save_api_url_file(api_url)
        download_files()
        install_dependencies(python_exe)
        set_env_variables()
        create_runner()
        register_startup(python_exe)
    except SystemExit:
        raise
    except Exception as e:
        fail(str(e))

    messagebox.showinfo(
        "ITDer Installer",
        "Installation complete!\n\nThe pipeline will run automatically on next startup.\n\n"
        f"To test now, run:\npython {INSTALL_DIR}\\run_pipeline.py"
    )



if __name__ == "__main__":
    main()