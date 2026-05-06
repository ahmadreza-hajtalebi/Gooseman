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
    start = line.find("accounts=[") + 10
    end = line.find("]", start)
    raw = line[start:end]

    accounts = []
    for part in raw.split("|"):
        part = part.strip()
        if "today=" in part:
            accounts.append(part)
    return accounts

def reader():
    global latest_stats, logs, process

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
            today_total = 0
            session_total = 0

            for a in acc:
                try:
                    today_total += int(a.split("today=")[1].split()[0])
                except:
                    pass
                try:
                    session_total += int(a.split("script=")[1].split()[0])
                except:
                    pass

            latest_stats["today_used"] = today_total
            latest_stats["session_used"] = session_total
            latest_stats["quota_total"] = len(acc) * QUOTA_PER_ACCOUNT

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

    cfg["socks_host"] = request.get("socks_host", "127.0.0.1")
    cfg["socks_port"] = int(request.get("socks_port", 1080))

    if request.get("socks_user") is not None:
        cfg["socks_user"] = request["socks_user"]
    if request.get("socks_pass") is not None:
        cfg["socks_pass"] = request["socks_pass"]

    save_config(cfg)
    return {"status": "saved"}

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gooseman</title>

<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body { background:#0b0f19 }
.glass {
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.08);
}
.toggle-btn { transition: all 0.35s ease; }
</style>
</head>

<body class="text-white font-sans">

<div class="max-w-6xl mx-auto p-3 sm:p-6">

<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-5">
<h1 class="text-xl sm:text-2xl font-bold">🦢 Gooseman</h1>
<div id="status" class="px-3 py-1 bg-gray-800 rounded-full text-xs sm:text-sm">Loading...</div>
</div>

<button id="toggleBtn"
onclick="toggle()"
class="toggle-btn w-full mb-5 py-3 rounded-xl font-semibold text-base sm:text-lg bg-green-600">
Start Goose
</button>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">

<div class="glass p-3 sm:p-4 rounded-xl"><div class="text-gray-400 text-xs">Active</div><div id="active" class="text-lg">-</div></div>
<div class="glass p-3 sm:p-4 rounded-xl"><div class="text-gray-400 text-xs">Sessions</div><div id="sessions" class="text-lg">-</div></div>
<div class="glass p-3 sm:p-4 rounded-xl"><div class="text-gray-400 text-xs">Download</div><div id="download" class="text-lg">-</div></div>
<div class="glass p-3 sm:p-4 rounded-xl"><div class="text-gray-400 text-xs">Upload</div><div id="upload" class="text-lg">-</div></div>

</div>

<div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs">Today's Quota</div>
<div id="today" class="text-lg">-</div>
</div>

<div class="glass p-3 sm:p-4 rounded-xl">
<div class="text-gray-400 text-xs">Session Quota</div>
<div id="session" class="text-lg">-</div>
</div>

</div>

<!-- GRAPHS -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-5">

<div class="glass p-4 rounded-xl">
<h2 class="text-base font-semibold mb-3">📊 Global Usage</h2>
<div class="h-[220px]">
<canvas id="globalChart"></canvas>
</div>
</div>

<div class="glass p-4 rounded-xl">
<h2 class="text-base font-semibold mb-3">👥 Per Account</h2>
<div class="h-[220px]">
<canvas id="accountChart"></canvas>
</div>
</div>

</div>

<div class="glass p-3 sm:p-4 rounded-xl h-[45vh] sm:h-[420px] overflow-y-scroll font-mono text-[10px] sm:text-xs">
<div id="logs"></div>
</div>

</div>

<script>

let running = false

const MAX_POINTS = 25

let globalChart
let accountChart

let globalData = {
labels: [],
upload: [],
download: [],
quota: []
}

let accountSeries = {}

function clamp(v){
v = parseFloat(v)
if(isNaN(v)) return 0
return Math.max(0, v)
}

function initCharts(){

globalChart = new Chart(document.getElementById("globalChart"),{
type:"line",
data:{
labels:globalData.labels,
datasets:[
{label:"Upload",borderColor:"#22c55e",data:globalData.upload,tension:0.3},
{label:"Download",borderColor:"#3b82f6",data:globalData.download,tension:0.3},
{label:"Quota",borderColor:"#f59e0b",data:globalData.quota,tension:0.3}
]
},
options:{
responsive:true,
maintainAspectRatio:false,
scales:{x:{display:false}}
}
})

accountChart = new Chart(document.getElementById("accountChart"),{
type:"line",
data:{
labels:[],
datasets:[]
},
options:{
responsive:true,
maintainAspectRatio:false,
scales:{x:{display:false}}
}
})

}

function updateAccountChart(accounts){

let labels = accountChart.data.labels
labels.push("")

if(labels.length > MAX_POINTS) labels.shift()

let datasets = []

accounts.forEach((acc,i)=>{

let name = acc.name

if(!accountSeries[name]){
accountSeries[name] = Array(MAX_POINTS).fill(0)
}

accountSeries[name].push(acc.today)
if(accountSeries[name].length > MAX_POINTS)
accountSeries[name].shift()

datasets.push({
label:name,
data:accountSeries[name],
tension:0.3,
borderColor:`hsl(${i*80},70%,60%)`
})

})

accountChart.data.labels = labels
accountChart.data.datasets = datasets
accountChart.update()

}

async function toggle(){
document.getElementById("logs").innerHTML=""
const r=await fetch("/toggle").then(r=>r.json())
running=r.running
apply()
}

function apply(){
const b=document.getElementById("toggleBtn")
if(running){
b.innerText="Stop Goose"
b.classList.replace("bg-green-600","bg-red-600")
}else{
b.innerText="Start Goose"
b.classList.replace("bg-red-600","bg-green-600")
}
}

async function update(){

const s = await fetch("/status").then(r=>r.json())
running = s.running
apply()

document.getElementById("status").innerText = running ? "🟢 Running" : "🔴 Stopped"

if(s.stats){

let u = clamp(s.stats.upload)
let d = clamp(s.stats.download)
let q = clamp(s.stats.today_used)

document.getElementById("active").innerText = s.stats.active ?? "-"
document.getElementById("sessions").innerText = s.stats.sessions ?? "-"
document.getElementById("upload").innerText = u
document.getElementById("download").innerText = d

const t = s.stats.quota_total ?? 0
document.getElementById("today").innerText = `${q} / ~${t}`
document.getElementById("session").innerText = `${s.stats.session_used ?? 0} / ~${t}`

globalData.labels.push("")
globalData.upload.push(u)
globalData.download.push(d)
globalData.quota.push(q)

if(globalData.labels.length > MAX_POINTS){
globalData.labels.shift()
globalData.upload.shift()
globalData.download.shift()
globalData.quota.shift()
}

globalChart.update()

if(s.stats.accounts){
let accounts = []

for(let a of s.stats.accounts){
accounts.push({
name: a.name || "acc",
today: clamp(a.today)
})
}

updateAccountChart(accounts)
}

}

const l = await fetch("/logs").then(r=>r.json())
document.getElementById("logs").innerHTML =
l.logs.map(x=>`<div>${x}</div>`).join("")

}

setInterval(update,1000)

initCharts()
update()

</script>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=HTML_PAGE)