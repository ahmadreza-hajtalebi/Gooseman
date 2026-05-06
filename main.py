from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess
import threading
import re
import os

app = FastAPI()

process = None
logs = []
latest_stats = {}

QUOTA_PER_ACCOUNT = 20000


# -------------------------
# PARSING
# -------------------------

stats_pattern = re.compile(
    r"active=(\d+).*sessions=(\d+)/(\d+).*bytes=([\d\.A-Z]+)/([\d\.A-Z]+)"
)


def parse_accounts(line):
    if "accounts=[" not in line:
        return None

    start = line.find("accounts=[") + len("accounts=[")
    end = line.find("]", start)
    raw = line[start:end]

    accounts = []
    for part in raw.split("|"):
        part = part.strip()
        if "today=" in part and "script=" in part:
            accounts.append(part)

    return accounts


# -------------------------
# READER
# -------------------------

def reader():
    global latest_stats, logs, process

    accounts = []

    for line in process.stdout:
        line = line.strip()
        logs.append(line)

        # basic stats
        m = stats_pattern.search(line)
        if m:
            latest_stats["active"] = int(m.group(1))
            latest_stats["sessions"] = f"{m.group(2)}/{m.group(3)}"
            latest_stats["upload"] = m.group(4)
            latest_stats["download"] = m.group(5)

        # accounts + quota calc
        acc = parse_accounts(line)
        if acc:
            accounts = acc
            latest_stats["accounts"] = len(accounts)

            today_total = 0
            session_total = 0

            for a in accounts:
                try:
                    today_total += int(a.split("today=")[1].split()[0])
                except:
                    pass

                try:
                    session_total += int(a.split("script=")[1].split()[0])
                except:
                    pass

            total_quota = len(accounts) * QUOTA_PER_ACCOUNT

            latest_stats["today_used"] = today_total
            latest_stats["session_used"] = session_total
            latest_stats["quota_total"] = total_quota


# -------------------------
# CONTROL
# -------------------------

@app.get("/start")
def start():
    global process

    if not process or process.poll() is not None:

        base_dir = os.path.dirname(os.path.abspath(__file__))

        process = subprocess.Popen(
            ["./goose-client", "-config", "client_config.json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=base_dir
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
body { background:#0b0f19; }
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
    <div id="status" class="px-3 py-1 bg-gray-800 rounded-full text-sm">Loading...</div>
</div>

<!-- BUTTONS -->
<div class="flex gap-3 mb-6">
    <button onclick="start()" class="bg-green-600 px-4 py-2 rounded-xl">Start</button>
    <button onclick="stop()" class="bg-red-600 px-4 py-2 rounded-xl">Stop</button>
</div>

<!-- STATS -->
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">

    <div class="glass p-4 rounded-xl">
        <div class="text-gray-400 text-sm">Active</div>
        <div id="active" class="text-xl">-</div>
    </div>

    <div class="glass p-4 rounded-xl">
        <div class="text-gray-400 text-sm">Sessions</div>
        <div id="sessions" class="text-xl">-</div>
    </div>

    <div class="glass p-4 rounded-xl">
        <div class="text-gray-400 text-sm">Download</div>
        <div id="download" class="text-xl">-</div>
    </div>

    <div class="glass p-4 rounded-xl">
        <div class="text-gray-400 text-sm">Upload</div>
        <div id="upload" class="text-xl">-</div>
    </div>

</div>

<!-- QUOTA -->
<div class="grid grid-cols-2 gap-4 mb-6">

    <div class="glass p-4 rounded-xl">
        <div class="text-gray-400 text-sm">Today's Quota</div>
        <div id="today" class="text-xl">-</div>
    </div>

    <div class="glass p-4 rounded-xl">
        <div class="text-gray-400 text-sm">Session Quota</div>
        <div id="session" class="text-xl">-</div>
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

        document.getElementById("sessions").innerText =
            s.stats.sessions ?? "-";

        document.getElementById("download").innerText = s.stats.download ?? "-";
        document.getElementById("upload").innerText = s.stats.upload ?? "-";

        const total = s.stats.quota_total ?? 0;

        const today = s.stats.today_used ?? 0;
        const session = s.stats.session_used ?? 0;

        document.getElementById("today").innerText =
            `${today} / ${total}`;

        document.getElementById("session").innerText =
            `${session} / ${total}`;
    }

    const l = await fetch('/logs').then(r => r.json());
    document.getElementById("logs").innerHTML =
        l.logs.map(x => `<div>${x}</div>`).join("");
}

function start(){ fetch('/start'); }
function stop(){ fetch('/stop'); }

setInterval(update, 1000);
update();

</script>

</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=HTML_PAGE)