import subprocess
import sys
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

while True:

    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "5000"
        ],
        cwd=BASE_DIR
    )

    p.wait()

    restart_flag = os.path.join(BASE_DIR, ".restart")

    if os.path.exists(restart_flag):
        os.remove(restart_flag)

        print("Restarting Gooseman...")
        time.sleep(1)

        continue

    break