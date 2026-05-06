from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import subprocess
import threading
import re
import os
import json

app = FastAPI()

process = None
logs = []
latest_stats = {}

QUOTA_PER_ACCOUNT = 20000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "client_config.json")

stats_pattern = re.compile(r"active=(\d+).*sessions=(\d+)/(\d+).*bytes=([\d\.A-Z]+)/([\d\.A-Z]+)")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"socks_host": "127.0.0.1", "socks_port": 1080}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)

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

def reader():
    global latest_stats, logs, process

    accounts = []

    for line in process.stdout:
        line = line.strip()
        logs.append(line)

        m = stats_pattern.search(line)
        if m:
            latest_stats["active"] = int(m.group(1))
            latest_stats["sessions"] = f"{m.group(2)}/{m.group(3)}"
            latest_stats["upload"] = m.group(4)
            latest_stats["download"] = m.group(5)

        acc = parse_accounts(line)
        if acc:
            accounts = acc

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

@app.get("/toggle")
def toggle():
    global process, logs, latest_stats

    if process and process.poll() is None:
        process.terminate()
        return {"running": False}

    logs = []
    latest_stats = {}

    process = subprocess.Popen(
        ["./goose-client", "-config", "client_config.json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=BASE_DIR
    )

    threading.Thread(target=reader, daemon=True).start()

    return {"running": True}

@app.get("/status")
def status():
    return {
        "running": process and process.poll() is None,
        "stats": latest_stats
    }

@app.get("/logs")
def get_logs():
    return {"logs": logs[-200:]}

@app.get("/config")
def get_config():
    return load_config()

@app.post("/config/update")
async def update_config(request: dict):
    cfg = load_config()

    cfg["socks_host"] = request.get("socks_host", cfg.get("socks_host", "127.0.0.1"))
    cfg["socks_port"] = int(request.get("socks_port", cfg.get("socks_port", 1080)))

    if request.get("socks_user") is not None:
        cfg["socks_user"] = request["socks_user"]
    if request.get("socks_pass") is not None:
        cfg["socks_pass"] = request["socks_pass"]

    save_config(cfg)
    return {"status": "saved", "config": cfg}

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gooseman</title>
<script src="https://cdn.tailwindcss.com"></script>

<style>
body { background:#0b0f19 }
.glass {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.08);
}
.toggle-btn {
  transition: all 0.35s ease;
}
</style>
</head>

<body class="text-white font-sans">

<div class="max-w-6xl mx-auto p-3 sm:p-6">

<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-5">
<h1 class="text-xl sm:text-2xl font-bold">🦢 Gooseman</h1>

<div id="status" class="px-3 py-1 bg-gray-800 rounded-full text-xs sm:text-sm w-fit">
Loading...
</div>
</div>

<button id="toggleBtn"
onclick="toggle()"
class="toggle-btn w-full sm:w-full mb-5 py-3 rounded-xl font-semibold text-base sm:text-lg bg-green-600">
Start Goose
</button>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-5">

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs sm:text-sm">Active</div>
<div id="active" class="text-lg sm:text-xl">-</div>
</div>

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs sm:text-sm">Sessions</div>
<div id="sessions" class="text-lg sm:text-xl">-</div>
</div>

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs sm:text-sm">Download</div>
<div id="download" class="text-lg sm:text-xl">-</div>
</div>

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs sm:text-sm">Upload</div>
<div id="upload" class="text-lg sm:text-xl">-</div>
</div>

</div>

<div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 mb-5">

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs sm:text-sm">Today's Quota</div>
<div id="today" class="text-lg sm:text-xl">-</div>
</div>

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs sm:text-sm">Session Quota</div>
<div id="session" class="text-lg sm:text-xl">-</div>
</div>

</div>

<div class="glass p-3 sm:p-4 rounded-xl mb-5">

<h2 class="text-base sm:text-lg font-semibold mb-3">⚙️ SOCKS Config</h2>

<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">

<input id="socks_host" class="p-2 bg-gray-900 rounded text-sm">
<input id="socks_port" class="p-2 bg-gray-900 rounded text-sm">
<input id="socks_user" class="p-2 bg-gray-900 rounded text-sm">
<input id="socks_pass" class="p-2 bg-gray-900 rounded text-sm" type="password">

</div>

<button onclick="saveConfig()" class="mt-4 w-full bg-blue-600 px-4 py-2 rounded-xl text-sm sm:text-base">
Save
</button>

</div>

<div class="glass p-3 sm:p-4 rounded-xl h-[50vh] sm:h-[420px] overflow-y-scroll font-mono text-[10px] sm:text-xs">
<div id="logs"></div>
</div>

</div>

<script>

let running = false

async function toggle(){
document.getElementById("logs").innerHTML = ""

const res = await fetch('/toggle').then(r=>r.json())
running = res.running
applyState()
}

function applyState(){
const b = document.getElementById("toggleBtn")

if(running){
b.innerText = "Stop Goose"
b.classList.remove("bg-green-600")
b.classList.add("bg-red-600")
}else{
b.innerText = "Start Goose"
b.classList.remove("bg-red-600")
b.classList.add("bg-green-600")
}
}

async function update(){
const s = await fetch('/status').then(r=>r.json())
running = s.running
applyState()

document.getElementById("status").innerText =
running ? "🟢 Running" : "🔴 Stopped"

if(s.stats){
document.getElementById("active").innerText = s.stats.active ?? "-"
document.getElementById("sessions").innerText = s.stats.sessions ?? "-"
document.getElementById("download").innerText = s.stats.download ?? "-"
document.getElementById("upload").innerText = s.stats.upload ?? "-"

const t = s.stats.quota_total ?? 0
document.getElementById("today").innerHTML =
`${s.stats.today_used ?? 0} / ~${t}`

document.getElementById("session").innerHTML =
`${s.stats.session_used ?? 0} / ~${t}`
}

const l = await fetch('/logs').then(r=>r.json())
document.getElementById("logs").innerHTML =
l.logs.map(x=>`<div>${x}</div>`).join("")
}

async function loadConfig(){
const c = await fetch('/config').then(r=>r.json())

document.getElementById("socks_host").value = c.socks_host ?? ""
document.getElementById("socks_port").value = c.socks_port ?? ""
document.getElementById("socks_user").value = c.socks_user ?? ""
document.getElementById("socks_pass").value = c.socks_pass ?? ""
}

async function saveConfig(){
await fetch('/config/update',{
method:"POST",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({
socks_host:document.getElementById("socks_host").value,
socks_port:document.getElementById("socks_port").value,
socks_user:document.getElementById("socks_user").value || null,
socks_pass:document.getElementById("socks_pass").value || null
})
})

alert("Saved")
}

setInterval(update,1000)
update()
loadConfig()

</script>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=HTML_PAGE)