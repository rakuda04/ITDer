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
REPO_BASE    = "https://raw.githubusercontent.com/rakuda04/ITDer/installation-script/dist"
INSTALL_DIR  = r"C:\ProgramData\itder"
MODELS_DIR   = r"C:\ProgramData\itder\models"
REF_DIR      = r"C:\ProgramData\itder\reference"

FILES = [
    "config.py",
    "data_collector.py",
    "local_preprocessor.py",
    "inference.py",
    "synthetic_generator.py",
    "send_to_server.py",
    "collectors/browser_history.py",
    "collectors/windows_events.py",
    "processors/filters.py",
]

MODEL_FILES = [
    "models/elliptic_env.pkl",
    "models/iso_forest.pkl",
    "models/lof_scaler.pkl",
    "models/rf_supervised.pkl",
    "models/rf_supervised.pkl.cert_original",
]

REFERENCE_FILES = [
    "reference/cert_baseline_stats.json",
    "reference/model_intake_final.csv",
    "reference/cert_thresholds.json",
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

os.chdir(r"{install_dir}")
log_file = r"{install_dir}\\pipeline.log"

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"[{{datetime.now()}}] {{msg}}\\n")
    print(msg)

log("Pipeline started")
scripts = [
    "data_collector.py",
    "local_preprocessor.py",
    "synthetic_generator.py",
    "inference.py",
    "send_to_server.py",
]
for script in scripts:
    log(f"Running {{script}}...")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
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


def fail(msg):
    messagebox.showerror("ITDer Installer", f"Installation failed:\n\n{msg}")
    sys.exit(1)


def check_python():
    log("Checking Python...")
    py = shutil.which("python") or shutil.which("python3")
    if not py:
        fail("Python not found. Install Python 3.9+ from https://python.org and try again.")
    result = subprocess.run([py, "--version"], capture_output=True, text=True)
    log(f"Found {result.stdout.strip()}")
    return py


def enable_audit_policies():
    log("Enabling Windows audit policies...")
    cmds = [
        ["auditpol", "/set", "/subcategory:Logon", "/success:enable", "/failure:enable"],
        ["auditpol", "/set", "/subcategory:Other Logon/Logoff Events", "/success:enable"],
        ["wevtutil", "sl", "Microsoft-Windows-DriverFrameworks-UserMode/Operational", "/e:true"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
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
        MODELS_DIR,
        REF_DIR,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def download_files():
    log("Downloading pipeline files from GitHub...")
    for file in FILES:
        url  = f"{REPO_BASE}/{file}"
        dest = os.path.join(INSTALL_DIR, file.replace("/", os.sep))
        log(f"  {file}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            fail(f"Failed to download {file}:\n{e}\n\nCheck your internet connection.")

    for subdir in ["collectors", "processors"]:
        init = os.path.join(INSTALL_DIR, subdir, "__init__.py")
        open(init, "w").close()

    log("Downloading model files...")
    for file in MODEL_FILES:
        url  = f"{REPO_BASE}/{file}"
        dest = os.path.join(INSTALL_DIR, file.replace("/", os.sep))
        log(f"  {file}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            fail(f"Failed to download {file}:\n{e}")

    log("Downloading reference files...")
    for file in REFERENCE_FILES:
        url  = f"{REPO_BASE}/{file}"
        dest = os.path.join(INSTALL_DIR, file.replace("/", os.sep))
        log(f"  {file}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            fail(f"Failed to download {file}:\n{e}")

    log("All files downloaded.")


def install_dependencies(python_exe):
    log("Installing Python dependencies...")
    for batch in DEPS:
        log(f"  pip install {' '.join(batch)}")
        result = subprocess.run(
            [python_exe, "-m", "pip", "install"] + batch + ["--quiet"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            fail(f"Failed to install {batch}:\n{result.stderr}")
    log("Dependencies installed.")


def set_env_variables(api_url):
    log("Setting system environment variables...")
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, "ITDER_API_URL", 0, winreg.REG_SZ, api_url)
    winreg.SetValueEx(key, "PYTHONUTF8",    0, winreg.REG_SZ, "1")
    winreg.CloseKey(key)
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None)
    log(f"ITDER_API_URL = {api_url}")
    log("PYTHONUTF8 = 1")


def create_runner():
    log("Creating pipeline runner...")
    runner_path = os.path.join(INSTALL_DIR, "run_pipeline.py")
    with open(runner_path, "w") as f:
        f.write(RUNNER_SCRIPT)


def register_startup(python_exe):
    log("Registering startup entry in registry...")
    runner = os.path.join(INSTALL_DIR, "run_pipeline.py")
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, "ITDerPipeline", 0, winreg.REG_SZ, f'"{python_exe}" "{runner}"')
    winreg.CloseKey(key)
    log("Startup entry registered.")


def main():
    # auto-elevate — triggers UAC prompt on double-click
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1
        )
        sys.exit(0)

    root = tk.Tk()
    root.withdraw()

    api_url = simpledialog.askstring(
        "ITDer Installer",
        "Enter the ITDer API URL:",
        initialvalue="https://",
        parent=root
    )
    if not api_url or api_url.strip() == "https://":
        messagebox.showwarning("ITDer Installer", "No API URL entered. Installation cancelled.")
        sys.exit(0)

    api_url = api_url.strip()

    try:
        python_exe = check_python()
        enable_audit_policies()
        create_directories()
        download_files()
        install_dependencies(python_exe)
        set_env_variables(api_url)
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
