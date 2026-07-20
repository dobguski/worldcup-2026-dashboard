#!/usr/bin/env python3
"""Launcher: hardened sync server with auto-restart on crash."""
import subprocess, time, sys, os

MAX_RESTARTS = 10
RESTART_WINDOW = 300  # 5 minutes

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Auto-push disabled for public release — uncomment and set your own repo to enable
# subprocess.run(["git", "remote", "set-url", "https-push",
#     "https://github.com/YOUR_USERNAME/YOUR_REPO.git"], capture_output=True)

restarts = []
while True:
    print(f"\n[LAUNCH] Starting sync server... ({len(restarts)} restarts in {RESTART_WINDOW}s window)")
    proc = subprocess.Popen([sys.executable, "sync_worldcup.py", "--serve"])

    try:
        proc.wait()
        code = proc.returncode
        print(f"[LAUNCH] Server exited with code {code}")
    except KeyboardInterrupt:
        proc.terminate()
        print("\n[LAUNCH] Stopped.")
        break

    # Rate-limit restarts
    now = time.time()
    restarts = [t for t in restarts if now - t < RESTART_WINDOW]
    restarts.append(now)
    if len(restarts) > MAX_RESTARTS:
        print(f"[LAUNCH] Too many restarts ({len(restarts)} in {RESTART_WINDOW}s) — stopping.")
        break

    time.sleep(3)
