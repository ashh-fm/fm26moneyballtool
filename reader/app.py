"""FM26 Moneyball desktop app: runs the reader and shows the tool in its own window.

The window is Microsoft Edge in app mode (no tabs or address bar) with a private profile,
so it behaves like a standalone program; closing it stops the reader. Without Edge it
falls back to a small control window plus the default browser.
"""
import os
import subprocess
import sys
import threading
import webbrowser

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FM26 Moneyball")
os.makedirs(DATA_DIR, exist_ok=True)
# A windowed exe has no console: send log output to a file instead of crashing on print
if sys.stderr is None or sys.stdout is None:
    _log = open(os.path.join(DATA_DIR, "reader.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log

import server

URL = f"http://127.0.0.1:{server.PORT}/"
PROFILE = os.path.join(DATA_DIR, "window")
EDGE_PATHS = [
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
]


def find_edge() -> str | None:
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                    p = winreg.QueryValue(k, None)
                    if p and os.path.exists(p):
                        return p
            except OSError:
                pass
    except ImportError:
        pass
    return next((p for p in EDGE_PATHS if os.path.exists(p)), None)


def open_window(edge: str) -> subprocess.Popen:
    """Edge app window with its own profile: the process lives exactly as long as the window."""
    return subprocess.Popen([
        edge, f"--app={URL}", f"--user-data-dir={PROFILE}", "--window-size=1600,1000",
        "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
    ])


def control_window(srv):
    """Fallback when Edge is missing: a small status window, tool opens in the default browser."""
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("FM26 Moneyball")
    root.resizable(False, False)

    def quit_():
        threading.Thread(target=srv.shutdown, daemon=True).start()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", quit_)
    f = ttk.Frame(root, padding=16)
    f.grid()
    ttk.Label(f, text="FM26 Moneyball Scout", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(f, text=f"Reader running at {URL}").grid(row=1, column=0, sticky="w", pady=(8, 0))
    b = ttk.Frame(f)
    b.grid(row=2, column=0, sticky="we", pady=(12, 0))
    ttk.Button(b, text="Open tool", command=lambda: webbrowser.open(URL)).pack(side="left")
    ttk.Button(b, text="Quit", command=quit_).pack(side="right")
    root.after(400, lambda: webbrowser.open(URL))
    root.mainloop()


def main():
    edge = find_edge()
    try:
        srv = server.Server(("127.0.0.1", server.PORT), server.Handler)
    except OSError:
        # already running: just show the tool again
        open_window(edge) if edge else webbrowser.open(URL)
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not edge:
        control_window(srv)
        return
    open_window(edge).wait()   # until the user closes the window
    srv.shutdown()


if __name__ == "__main__":
    main()
