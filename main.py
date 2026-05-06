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

startup_error = None
runtime_error = None

stats_pattern = re.compile(
    r"active=(\d+).*sessions=(\d+)/(\d+).*bytes=([\d\.A-Z]+)/([\d\.A-Z]+)"
)

def check_integrity():
    global startup_error

    if not os.path.exists(CONFIG_PATH):
        startup_error = "Missing client_config.json"
        return False

    if not os.path.exists(os.path.join(BASE_DIR, "goose-client")):
        startup_error = "Missing goose-client binary"
        return False

    startup_error = None
    return True


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"socks_host": "127.0.0.1", "socks_port": 1080}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)


def to_kb(val):
    if not val:
        return 0.0
    val = str(val).upper().strip()
    try:
        if val.endswith("KB"):
            return float(val[:-2])
        if val.endswith("MB"):
            return float(val[:-2]) * 1024
        if val.endswith("GB"):
            return float(val[:-2]) * 1024 * 1024
        if val.endswith("B"):
            return float(val[:-1]) / 1024
        return float(val)
    except:
        return 0.0


def parse_accounts(line):
    if "accounts=[" not in line:
        return None

    start = line.find("accounts=[") + 10
    end = line.find("]", start)
    raw = line[start:end]

    accounts = []

    for part in raw.split("|"):
        part = part.strip()
        if not part:
            continue

        try:
            name = part.split("@")[-1].split()[0]

            today = 0
            script = 0

            if "today=" in part:
                today = int(part.split("today=")[1].split()[0])

            if "script=" in part:
                script = int(part.split("script=")[1].split()[0])

            accounts.append({
                "name": name,
                "today": today,
                "script": script
            })

        except:
            continue

    return accounts


def reader():
    global latest_stats, logs, process, runtime_error

    for line in process.stdout:
        line = line.strip()
        logs.append(line)

        if "ERROR" in line:
            runtime_error = line

        m = stats_pattern.search(line)
        if m:
            latest_stats["active"] = int(m.group(1))
            latest_stats["sessions"] = f"{m.group(2)}/{m.group(3)}"
            latest_stats["upload_kb"] = to_kb(m.group(4))
            latest_stats["download_kb"] = to_kb(m.group(5))

        acc = parse_accounts(line)
        if acc:
            latest_stats["accounts"] = acc

            latest_stats["today_used"] = sum(a["today"] for a in acc)
            latest_stats["session_used"] = sum(a["script"] for a in acc)
            latest_stats["quota_total"] = len(acc) * QUOTA_PER_ACCOUNT


@app.get("/toggle")
def toggle():
    global process, logs, latest_stats

    if not check_integrity():
        return {"running": False, "error": startup_error}

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
        "stats": latest_stats,
        "startup_error": startup_error,
        "runtime_error": runtime_error
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

    if "socks_user" in request:
        cfg["socks_user"] = request["socks_user"]
    if "socks_pass" in request:
        cfg["socks_pass"] = request["socks_pass"]

    save_config(cfg)
    return {"status": "saved"}


HTML_PAGE = """<!DOCTYPE html>
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

<div id="errorBox" class="hidden fixed top-0 left-0 right-0 z-50 p-3">
  <div class="glass p-4 rounded-xl flex justify-between items-center">
    <div id="errorText" class="text-red-400 font-semibold"></div>
    <div class="flex gap-2">
      <button onclick="restart()" class="bg-red-600 px-3 py-1 rounded">Restart</button>
      <button onclick="ignoreError()" class="bg-gray-600 px-3 py-1 rounded">Ignore</button>
    </div>
  </div>
</div>

<div class="max-w-6xl mx-auto p-4">

<div class="flex justify-between mb-4">
<h1 class="font-bold text-xl">🦢 Gooseman</h1>
<div id="status" class="bg-gray-800 px-3 py-1 rounded">Loading...</div>
</div>

<button id="toggleBtn" onclick="toggle()"
class="w-full py-3 rounded-xl bg-green-600 font-semibold">
Start Goose
</button>

<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">

<div class="glass p-3 rounded-xl"><div class="text-xs text-gray-400">Active</div><div id="active">-</div></div>
<div class="glass p-3 rounded-xl"><div class="text-xs text-gray-400">Sessions</div><div id="sessions">-</div></div>
<div class="glass p-3 rounded-xl"><div class="text-xs text-gray-400">Download</div><div id="download">-</div></div>
<div class="glass p-3 rounded-xl"><div class="text-xs text-gray-400">Upload</div><div id="upload">-</div></div>

<div class="glass p-3 rounded-xl col-span-2">
<div class="text-xs text-gray-400">Today's Quota</div>
<div id="today">-</div>
</div>

<div class="glass p-3 rounded-xl col-span-2">
<div class="text-xs text-gray-400">Session Quota</div>
<div id="session">-</div>
</div>

</div>

<div class="glass p-4 mt-4 rounded-xl">
<canvas id="chart"></canvas>
</div>

<div class="glass p-4 mt-4 rounded-xl">
<h2>Config</h2>
<input id="socks_host" class="bg-gray-900 p-2 w-full mt-2 rounded">
<input id="socks_port" class="bg-gray-900 p-2 w-full mt-2 rounded">
<input id="socks_user" class="bg-gray-900 p-2 w-full mt-2 rounded">
<input id="socks_pass" type="password" class="bg-gray-900 p-2 w-full mt-2 rounded">
<button onclick="saveConfig()" class="mt-3 bg-blue-600 px-4 py-2 rounded w-full">Save</button>
</div>

<div class="glass p-3 mt-4 rounded-xl h-64 overflow-y-scroll font-mono text-xs">
<div id="logs"></div>
</div>

</div>

<script>

let running=false
let chart

const ACCOUNT_QUOTA=20000

let data={labels:[],u:[],d:[],s:[],t:[]}

function init(){
chart=new Chart(document.getElementById("chart"),{
type:"line",
data:{
labels:data.labels,
datasets:[
{label:"Upload KB",data:data.u,borderColor:"#22c55e"},
{label:"Download KB",data:data.d,borderColor:"#3b82f6"},
{label:"Session",data:data.s,borderColor:"#f59e0b"},
{label:"Today",data:data.t,borderColor:"#ef4444"}
]
},
options:{responsive:true,maintainAspectRatio:false}
})
}

function fmt(v){
if(v>1024*1024)return(v/1024/1024).toFixed(2)+" GB"
if(v>1024)return(v/1024).toFixed(2)+" MB"
return v.toFixed(2)+" KB"
}

function sync(){
let b=document.getElementById("toggleBtn")
if(running){
b.innerText="Stop Goose"
b.classList.replace("bg-green-600","bg-red-600")
}else{
b.innerText="Start Goose"
b.classList.replace("bg-red-600","bg-green-600")
}
}

async function toggle(){
document.getElementById("logs").innerHTML=""
let r=await fetch("/toggle").then(r=>r.json())
running=r.running
sync()
}

function showError(m){
document.getElementById("errorBox").classList.remove("hidden")
document.getElementById("errorText").innerText=m
}

function ignoreError(){
document.getElementById("errorBox").classList.add("hidden")
}

async function restart(){
await fetch("/toggle")
ignoreError()
}

async function loadConfig(){
let c=await fetch("/config").then(r=>r.json())
socks_host.value=c.socks_host||""
socks_port.value=c.socks_port||""
socks_user.value=c.socks_user||""
socks_pass.value=c.socks_pass||""
}

async function saveConfig(){
await fetch("/config/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
socks_host:socks_host.value,
socks_port:socks_port.value,
socks_user:socks_user.value,
socks_pass:socks_pass.value
})})
}

let last=0

async function update(){
let s=await fetch("/status").then(r=>r.json())

running=!!s.running
sync()

document.getElementById("status").innerText=
running?"🟢 Running":"🔴 Stopped"

if(s.startup_error)showError(s.startup_error)
if(s.runtime_error)showError(s.runtime_error)

let st=s.stats||{}

let u=st.upload_kb||0
let d=st.download_kb||0
let sess=st.session_used||0
let today=st.today_used||0

document.getElementById("active").innerText=st.active??"-"
document.getElementById("sessions").innerText=st.sessions??"-"
document.getElementById("upload").innerText=fmt(u)
document.getElementById("download").innerText=fmt(d)

document.getElementById("today").innerText=
today+" / ~"+(st.quota_total||0)

document.getElementById("session").innerText=
sess+" / ~"+(st.quota_total||0)

data.labels.push("")
data.u.push(u)
data.d.push(d)
data.s.push(sess)
data.t.push(today)

if(data.labels.length>25){
data.labels.shift()
data.u.shift()
data.d.shift()
data.s.shift()
data.t.shift()
}

chart.update()

let l=await fetch("/logs").then(r=>r.json())
document.getElementById("logs").innerHTML=
l.logs.map(x=>`<div>${x}</div>`).join("")
}

setInterval(update,2000)

init()
loadConfig()
update()

</script>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=HTML_PAGE)