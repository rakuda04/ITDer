"""
reset.py  —  ITDer Installation Reset
Removes all traces of an ITDer installation for clean reinstall testing.

Removes:
  - C:\ProgramData\itder\  (all files)
  - Registry startup entry
  - System environment variables (ITDER_API_URL, PYTHONUTF8)

Usage:
  Run as Administrator:
  python reset.py
"""

import os
import sys
import shutil
import ctypes
import winreg

INSTALL_DIR  = r"C:\ProgramData\itder"
STARTUP_KEY  = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
ENV_KEY      = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
STARTUP_NAME = "ITDerPipeline"
ENV_VARS     = ["ITDER_API_URL", "PYTHONUTF8"]


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def log(msg):
    print(f"[reset] {msg}")


def remove_install_dir():
    if os.path.exists(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR)
        log(f"Removed {INSTALL_DIR}")
    else:
        log(f"Not found: {INSTALL_DIR} (skipping)")


def remove_startup_entry():
    import subprocess
    # 1. Delete scheduled task from Task Scheduler
    try:
        log(f"Deleting scheduled task: {STARTUP_NAME}...")
        cmd = ["schtasks", "/delete", "/tn", STARTUP_NAME, "/f"]
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if result.returncode == 0:
            log(f"Removed scheduled task: {STARTUP_NAME}")
        else:
            log(f"Scheduled task not found or already deleted: {STARTUP_NAME}")
    except Exception as e:
        log(f"Could not remove scheduled task: {e}")

    # 2. Clean up legacy registry key if present
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            STARTUP_KEY,
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        try:
            winreg.QueryValueEx(key, STARTUP_NAME)
            winreg.DeleteValue(key, STARTUP_NAME)
            log(f"Removed legacy registry startup entry: {STARTUP_NAME}")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception as e:
        log(f"Could not access startup registry key: {e}")



def remove_env_variables():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            ENV_KEY,
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        for var in ENV_VARS:
            try:
                winreg.QueryValueEx(key, var)
                winreg.DeleteValue(key, var)
                log(f"Removed env var: {var}")
            except FileNotFoundError:
                log(f"Env var not found: {var} (skipping)")
        winreg.CloseKey(key)
        # notify system
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None
        )
    except Exception as e:
        log(f"Could not access environment registry key: {e}")


def main():
    # auto-elevate — triggers UAC prompt
    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = [script] + sys.argv[1:]
        params_str = " ".join(f'"{p}"' for p in params)
        cwd = os.getcwd()
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params_str, cwd, 1
        )
        sys.exit(0)



    print("=" * 45)
    print("  ITDer Reset — removing all installation artifacts")
    print("=" * 45)

    remove_install_dir()
    remove_startup_entry()
    remove_env_variables()

    print()
    print("[reset] Done. Machine is clean for reinstall.")


if __name__ == "__main__":
    main()
