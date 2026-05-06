from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess
import threading
import re

app = FastAPI()

process = None
logs = []
latest_stats = {}

stats_pattern = re.compile(
    r"active=(\d+).*sessions=(\d+)/(\d+).*bytes=([\d\.A-Z]+)/([\d\.A-Z]+).*rst=(\d+)"
)

# -------------------------
# PROCESS HANDLING
# -------------------------

def reader():
    global latest_stats, logs, process

    for line in process.stdout:
        line = line.strip()
        logs.append(line)

        m = stats_pattern.search(line)
        if m:
            latest_stats = {
                "active": m.group(1),
                "sessions": f"{m.group(2)}/{m.group(3)}",
                "upload": m.group(4),
                "download": m.group(5),
                "rst": m.group(6),
            }

@app.get("/start")
def start():
    global process

    if not process or process.poll() is not None:
        process = subprocess.Popen(
            ["./goose-client", "-config", "config.json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        threading.Thread(target=reader, daemon=True).start()

    return {"status": "started"}

@app.get("/stop")
def stop():
    global process
    if process:
        process.terminate()
    return {"status": "stopped"}

@app.get("/status")
def status():
    return {
        "running": process and process.poll() is None,
        "stats": latest_stats
    }

@app.get("/logs")
def get_logs():
    return {"logs": logs[-80:]}


# -------------------------
# DASHBOARD
# -------------------------

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Goosean</title>
    <script src="https://cdn.tailwindcss.com"></script>

    <style>
        body {
            background: #0b0f19;
        }
        .glass {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.08);
        }
    </style>
</head>

<body class="text-white font-sans">

<div class="max-w-6xl mx-auto p-6">

    <!-- HEADER -->
    <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold">🦢 Goosean</h1>

        <div id="status" class="px-4 py-1 rounded-full bg-gray-800 text-sm">
            Loading...
        </div>
    </div>

    <!-- BUTTONS -->
    <div class="flex gap-3 mb-6">
        <button onclick="start()"
            class="bg-green-600 px-4 py-2 rounded-xl hover:bg-green-700">
            Start
        </button>

        <button onclick="stop()"
            class="bg-red-600 px-4 py-2 rounded-xl hover:bg-red-700">
            Stop
        </button>
    </div>

    <!-- STATS -->
    <div class="grid grid-cols-4 gap-4 mb-6">

        <div class="glass p-4 rounded-xl">
            <div class="text-gray-400 text-sm">Active</div>
            <div id="active" class="text-xl">-</div>
        </div>

        <div class="glass p-4 rounded-xl">
            <div class="text-gray-400 text-sm">Sessions</div>
            <div id="sessions" class="text-xl">-</div>
        </div>

        <div class="glass p-4 rounded-xl">
            <div class="text-gray-400 text-sm">Upload</div>
            <div id="upload" class="text-xl">-</div>
        </div>

        <div class="glass p-4 rounded-xl">
            <div class="text-gray-400 text-sm">RST</div>
            <div id="rst" class="text-xl">-</div>
        </div>

    </div>

    <!-- LOGS -->
    <div class="glass p-4 rounded-xl h-[420px] overflow-y-scroll font-mono text-xs">
        <div id="logs"></div>
    </div>

</div>

<script>

async function update() {
    const s = await fetch('/status').then(r => r.json());

    document.getElementById("status").innerText =
        s.running ? "🟢 Running" : "🔴 Stopped";

    if (s.stats) {
        document.getElementById("active").innerText = s.stats.active ?? "-";
        document.getElementById("sessions").innerText = s.stats.sessions ?? "-";
        document.getElementById("upload").innerText = s.stats.upload ?? "-";
        document.getElementById("rst").innerText = s.stats.rst ?? "-";
    }

    const l = await fetch('/logs').then(r => r.json());

    document.getElementById("logs").innerHTML =
        l.logs.map(x => `<div>${x}</div>`).join("");
}

function start() { fetch('/start'); }
function stop() { fetch('/stop'); }

setInterval(update, 1000);
update();

</script>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=HTML_PAGE)