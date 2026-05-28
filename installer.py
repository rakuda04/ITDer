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
REPO_BASE   = "https://raw.githubusercontent.com/rakuda04/ITDer/main/local_pipeline"
INSTALL_DIR = r"C:\ProgramData\itder"
TASK_NAME   = "ITDer Pipeline"
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
DEPS = ["pandas", "requests", "pywin32", "scikit-learn", "numpy"]
# ─────────────────────────────────────────────────────────────

RUNNER_SCRIPT = """\
import subprocess, sys, os
os.chdir(r"{install_dir}")
scripts = [
    "data_collector.py",
    "local_preprocessor.py",
    "inference.py",
    "send_to_server.py",
]
for script in scripts:
    print(f"[itder] Running {{script}}...")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"[itder] {{script}} failed: {{result.stderr}}")
        sys.exit(1)
print("[itder] Pipeline complete.")
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
    log(f"Creating {INSTALL_DIR}...")
    dirs = [
        INSTALL_DIR,
        os.path.join(INSTALL_DIR, "output"),
        os.path.join(INSTALL_DIR, "collectors"),
        os.path.join(INSTALL_DIR, "processors"),
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

    # create __init__.py so Python treats subdirs as packages
    for subdir in ["collectors", "processors"]:
        init = os.path.join(INSTALL_DIR, subdir, "__init__.py")
        open(init, "w").close()

    log("Files downloaded.")


def install_dependencies(python_exe):
    log("Installing Python dependencies...")
    for dep in DEPS:
        log(f"  pip install {dep}")
        result = subprocess.run(
            [python_exe, "-m", "pip", "install", dep, "--quiet"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            fail(f"Failed to install {dep}:\n{result.stderr}")
    log("Dependencies installed.")


def set_env_variable(api_url):
    log("Setting ITDER_API_URL system environment variable...")
    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0, winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, "ITDER_API_URL", 0, winreg.REG_SZ, api_url)
    winreg.CloseKey(key)
    # notify system of env change
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None)
    log(f"ITDER_API_URL = {api_url}")


def create_runner():
    log("Creating pipeline runner...")
    runner_path = os.path.join(INSTALL_DIR, "run_pipeline.py")
    with open(runner_path, "w") as f:
        f.write(RUNNER_SCRIPT)


def register_task(python_exe):
    log("Registering startup task in Task Scheduler...")
    runner = os.path.join(INSTALL_DIR, "run_pipeline.py")

    # remove existing task if present
    subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True
    )

    result = subprocess.run([
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", f'"{python_exe}" "{runner}"',
        "/sc", "onstart",
        "/ru", "SYSTEM",
        "/rl", "HIGHEST",
        "/f"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        fail(f"Failed to register startup task:\n{result.stderr}")

    log(f"Task '{TASK_NAME}' registered.")


def main():
    # init tkinter (hidden root)
    root = tk.Tk()
    root.withdraw()

    if not is_admin():
        messagebox.showerror("ITDer Installer", "Please run this installer as Administrator.")
        sys.exit(1)

    # ask for API URL
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
        set_env_variable(api_url)
        create_runner()
        register_task(python_exe)
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
