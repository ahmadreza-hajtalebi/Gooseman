from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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

ignored_errors = set()
authorized_tokens = set()

stats_pattern = re.compile(
    r"active=(\d+).*sessions=(\d+)/(\d+).*bytes=([\d\.A-Z]+)/([\d\.A-Z]+)"
)

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

*{
  box-sizing:border-box;
}

html{
  scroll-behavior:smooth;
}

body{
  background:
    radial-gradient(circle at top left,#172554 0%,transparent 35%),
    radial-gradient(circle at bottom right,#3b0764 0%,transparent 35%),
    #0b0f19;
  min-height:100vh;
  overflow-x:hidden;
}

body::before{
  content:"";
  position:fixed;
  inset:0;
  background:
    linear-gradient(rgba(255,255,255,0.015),rgba(255,255,255,0.015));
  pointer-events:none;
}

.glass{
  background:rgba(255,255,255,0.045);
  backdrop-filter:blur(18px);
  border:1px solid rgba(255,255,255,0.08);
  box-shadow:
    0 10px 40px rgba(0,0,0,0.25),
    inset 0 1px rgba(255,255,255,0.04);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease,
    border-color 0.25s ease;
}

.glass:hover{
  transform:translateY(-2px);
  border-color:rgba(255,255,255,0.14);
  box-shadow:
    0 20px 50px rgba(0,0,0,0.35),
    0 0 30px rgba(59,130,246,0.08);
}

.toggle-btn{
  transition:
    background-color 0.35s ease,
    transform 0.16s ease,
    opacity 0.2s ease,
    box-shadow 0.3s ease;
}

.btn{
  transition:
    transform 0.16s ease,
    opacity 0.2s ease,
    background-color 0.25s ease,
    box-shadow 0.25s ease;
}

.btn:hover,
.toggle-btn:hover{
  transform:translateY(-2px) scale(1.01);
  opacity:0.96;
}

.btn:active,
.toggle-btn:active{
  transform:scale(0.98);
}

.btn:disabled,
.toggle-btn:disabled{
  opacity:0.45;
  cursor:not-allowed;
  transform:none;
  box-shadow:none;
}

.bg-green-600{
  box-shadow:0 0 25px rgba(34,197,94,0.28);
}

.bg-red-600{
  box-shadow:0 0 25px rgba(239,68,68,0.28);
}

.bg-blue-600{
  box-shadow:0 0 25px rgba(37,99,235,0.22);
}

.log-stopped{
  opacity:0.42;
  filter:saturate(0.7);
  transition:all 0.35s ease;
}

.log-running{
  opacity:1;
  transition:all 0.35s ease;
}

input{
  outline:none;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease,
    box-shadow 0.25s ease,
    transform 0.18s ease;
  border:1px solid transparent;
}

input:focus{
  border-color:rgba(59,130,246,0.5);
  box-shadow:
    0 0 0 4px rgba(59,130,246,0.08),
    0 0 20px rgba(59,130,246,0.15);
  transform:translateY(-1px);
}

input::placeholder{
  color:#9ca3af;
}

#loginOverlay{
  backdrop-filter:blur(22px);
  animation:fadeIn 0.3s ease;
}

#status{
  border:1px solid rgba(255,255,255,0.08);
  backdrop-filter:blur(12px);
}

canvas{
  filter:drop-shadow(0 0 14px rgba(59,130,246,0.12));
}

::-webkit-scrollbar{
  width:10px;
}

::-webkit-scrollbar-track{
  background:transparent;
}

::-webkit-scrollbar-thumb{
  background:rgba(255,255,255,0.12);
  border-radius:999px;
}

::-webkit-scrollbar-thumb:hover{
  background:rgba(255,255,255,0.2);
}

@keyframes pulseGlow{
  0%{
    box-shadow:0 0 0 rgba(34,197,94,0.2);
  }
  50%{
    box-shadow:0 0 25px rgba(34,197,94,0.28);
  }
  100%{
    box-shadow:0 0 0 rgba(34,197,94,0.2);
  }
}

@keyframes fadeIn{
  from{
    opacity:0;
    transform:translateY(10px);
  }
  to{
    opacity:1;
    transform:none;
  }
}

.page-enter{
  animation:fadeIn 0.45s ease;
}

.glow-blue{
  position:absolute;
  width:400px;
  height:400px;
  background:#2563eb;
  opacity:0.08;
  filter:blur(120px);
  border-radius:999px;
  top:-120px;
  left:-120px;
  pointer-events:none;
}

.glow-purple{
  position:absolute;
  width:400px;
  height:400px;
  background:#9333ea;
  opacity:0.08;
  filter:blur(120px);
  border-radius:999px;
  bottom:-120px;
  right:-120px;
  pointer-events:none;
}

</style>
</head>

<body class="text-white font-sans">
<div class="glow-blue"></div>
<div class="glow-purple"></div>

<div id="loginOverlay"
class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70">

<div class="glass w-[92%] max-w-md p-7 rounded-[2rem] shadow-2xl border border-white/10">
<div class="text-3xl font-bold mb-2 text-center">🦢 Gooseman</div>

<div class="text-gray-400 text-sm text-center mb-6">
Enter the SOCKS5 password to continue
</div>

<input
id="loginPassword"
type="password"
placeholder="SOCKS5 password"
class="w-full bg-gray-900 p-3 rounded-xl mb-4"
/>

<button
onclick="login()"
id="loginBtn"
class="btn w-full bg-blue-600 rounded-xl py-3 font-semibold">
Unlock
</button>

<div id="loginError"
class="hidden text-red-400 text-sm mt-3 text-center">
Invalid password
</div>

</div>
</div>

<div id="errorBox"
class="hidden fixed top-0 left-0 right-0 z-50 p-3">

<div class="glass p-4 rounded-xl flex justify-between items-center gap-4">

<div id="errorText"
class="text-red-400 font-semibold break-all"></div>

<div class="flex gap-2 shrink-0">

<button
onclick="restart()"
class="btn bg-red-600 px-3 py-1 rounded-lg">
Restart
</button>

<button
onclick="ignoreError()"
class="btn bg-gray-600 px-3 py-1 rounded-lg">
Ignore
</button>

</div>
</div>
</div>

<div class="max-w-6xl mx-auto p-4 relative z-10 page-enter">

<div class="flex justify-between items-center mb-4 gap-3">

<h1 class="font-bold text-2xl">🦢 Gooseman</h1>

<div id="status"
class="bg-gray-800/70 px-4 py-1.5 rounded-full text-sm shadow-lg">
Loading...
</div>

</div>

<button
id="toggleBtn"
onclick="toggle()"
class="toggle-btn w-full py-3 rounded-2xl bg-green-600 font-semibold text-lg">
Start Goose
</button>

<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">

<div class="glass p-3 rounded-2xl">
<div class="text-xs text-gray-400">Active</div>
<div id="active" class="text-lg">-</div>
</div>

<div class="glass p-3 rounded-2xl">
<div class="text-xs text-gray-400">Sessions</div>
<div id="sessions" class="text-lg">-</div>
</div>

<div class="glass p-3 rounded-2xl">
<div class="text-xs text-gray-400">Download</div>
<div id="download" class="text-lg">-</div>
</div>

<div class="glass p-3 rounded-2xl">
<div class="text-xs text-gray-400">Upload</div>
<div id="upload" class="text-lg">-</div>
</div>

<div class="glass p-3 rounded-2xl col-span-2">
<div class="text-xs text-gray-400">Today's Quota</div>
<div id="today" class="text-lg">0 / ~0</div>
</div>

<div class="glass p-3 rounded-2xl col-span-2">
<div class="text-xs text-gray-400">Session Quota</div>
<div id="session" class="text-lg">0 / ~0</div>
</div>

</div>

<div class="glass p-5 mt-4 rounded-3xl overflow-hidden relative">

<div class="absolute inset-0 opacity-[0.03]"
style="background-image:linear-gradient(to right,white 1px,transparent 1px),linear-gradient(to bottom,white 1px,transparent 1px);background-size:24px 24px">
</div>

<div class="font-semibold mb-3 relative z-10">
📊 Quota per usage (KB)
</div>

<div class="h-[280px] relative z-10">
<canvas id="chart"></canvas>
</div>

</div>

<div class="glass p-4 mt-4 rounded-2xl">

<div class="font-semibold mb-3">
⚙️ SOCKS5 Config
</div>

<div class="grid md:grid-cols-2 gap-3">

<input
id="socks_host"
placeholder="SOCKS5 Host (127.0.0.1)"
class="bg-gray-900 p-3 rounded-xl"
/>

<input
id="socks_port"
placeholder="SOCKS5 Port (1080)"
class="bg-gray-900 p-3 rounded-xl"
/>

<input
id="socks_user"
placeholder="SOCKS5 Username"
class="bg-gray-900 p-3 rounded-xl"
/>

<input
id="socks_pass"
type="password"
placeholder="SOCKS5 Password"
class="bg-gray-900 p-3 rounded-xl"
/>

</div>

<button
onclick="saveConfig()"
class="btn mt-4 bg-blue-600 px-4 py-3 rounded-xl w-full font-semibold">
Save Configuration
</button>

</div>

<div
id="logBox"
class="glass p-3 mt-4 rounded-2xl h-64 overflow-y-scroll font-mono text-xs log-stopped">

<div id="logs"></div>

</div>

</div>

<script>

let running = false
let chart
let ignoredError = null
let locked = false
let authToken = null

let data = {
labels:[],
u:[],
d:[],
s:[],
t:[]
}

function authHeaders(){
return {
"Authorization": authToken || ""
}
}

async function api(url, options={}){

options.headers = {
...(options.headers || {}),
...authHeaders()
}

let r = await fetch(url, options)

if(r.status === 401){

document.getElementById("loginOverlay").style.display = "flex"

throw new Error("Unauthorized")

}

return r

}

function init(){

chart = new Chart(document.getElementById("chart"),{

type:"line",

data:{
labels:data.labels,
datasets:[
{
label:"Upload KB",
data:data.u,
borderColor:"#22c55e",
tension:0.35
},
{
label:"Download KB",
data:data.d,
borderColor:"#3b82f6",
tension:0.35
},
{
label:"Session Quota",
data:data.s,
borderColor:"#f59e0b",
tension:0.35
},
{
label:"Today's Quota",
data:data.t,
borderColor:"#ef4444",
tension:0.35
}
]
},

options:{
responsive:true,
maintainAspectRatio:false
}

})

}

function fmt(v){

if(v > 1024 * 1024)
return (v/1024/1024).toFixed(2) + " GB"

if(v > 1024)
return (v/1024).toFixed(2) + " MB"

return v.toFixed(2) + " KB"

}

function sync(){

let b = document.getElementById("toggleBtn")

if(running){

document.getElementById("status").style.animation =
"pulseGlow 2s infinite"

b.innerText = "Stop Goose"

b.classList.remove("bg-green-600")
b.classList.add("bg-red-600")

}else{

document.getElementById("status").style.animation = "none"

b.innerText = "Start Goose"

b.classList.remove("bg-red-600")
b.classList.add("bg-green-600")

}

}

function showError(msg){

document.getElementById("errorBox").classList.remove("hidden")
document.getElementById("errorText").innerText = msg

}

function hideError(){

document.getElementById("errorBox").classList.add("hidden")

}

async function ignoreError(){

if(!ignoredError) return

await api("/ignore-error",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({
error: ignoredError
})
})

hideError()

}

async function restart(){

await toggle()

setTimeout(async ()=>{
await toggle()
}, 500)

hideError()

}

async function login(){

const password = document.getElementById("loginPassword").value

const r = await fetch("/login",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({
password
})
})

const d = await r.json()

if(!d.ok){

document.getElementById("loginError").classList.remove("hidden")
return

}

authToken = d.token

document.getElementById("loginOverlay").style.display = "none"

await loadConfig()
await update()

}

async function toggle(){

if(locked) return

locked = true

const b = document.getElementById("toggleBtn")

b.disabled = true

document.getElementById("logs").innerHTML = ""

let r = await api("/toggle")
let d = await r.json()

running = d.running

sync()

setTimeout(()=>{
locked = false
b.disabled = false
}, 3000)

}

async function loadConfig(){

let c = await (await api("/config")).json()

socks_host.value = c.socks_host || ""
socks_port.value = c.socks_port || ""
socks_user.value = c.socks_user || ""
socks_pass.value = c.socks_pass || ""

}

async function saveConfig(){

await api("/config/update",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({
socks_host:socks_host.value,
socks_port:socks_port.value,
socks_user:socks_user.value,
socks_pass:socks_pass.value
})
})

}

async function update(){

let s = await (await api("/status")).json()

running = !!s.running

sync()

document.getElementById("status").innerText =
running ? "🟢 Running" : "🔴 Stopped"

document.getElementById("logBox").className =
running
? "glass p-3 mt-4 rounded-2xl h-64 overflow-y-scroll font-mono text-xs log-running"
: "glass p-3 mt-4 rounded-2xl h-64 overflow-y-scroll font-mono text-xs log-stopped"

if(s.startup_error){
showError(s.startup_error)
}

if(s.runtime_error){

ignoredError = s.runtime_error
showError(s.runtime_error)

}

let st = s.stats || {}

let u = st.upload_kb || 0
let d = st.download_kb || 0
let sess = st.session_used || 0
let today = st.today_used || 0

document.getElementById("active").innerText = st.active ?? "-"
document.getElementById("sessions").innerText = st.sessions ?? "-"
document.getElementById("upload").innerText = fmt(u)
document.getElementById("download").innerText = fmt(d)

document.getElementById("today").innerText =
today + " / ~" + (st.quota_total || 0)

document.getElementById("session").innerText =
sess + " / ~" + (st.quota_total || 0)

data.labels.push("")
data.u.push(u)
data.d.push(d)
data.s.push(sess)
data.t.push(today)

if(data.labels.length > 25){

data.labels.shift()
data.u.shift()
data.d.shift()
data.s.shift()
data.t.shift()

}

chart.update()

let l = await (await api("/logs")).json()

document.getElementById("logs").innerHTML =
l.logs.map(x => `
<div class="py-1 border-b border-white/5 break-all">
${x}
</div>
`).join("")

}

setInterval(async ()=>{

if(authToken){

try{
await update()
}catch{}

}

}, 3000)

init()

document.getElementById("loginOverlay").style.display = "flex"

</script>

</body>
</html>
"""

def require_auth(request: Request):

    token = request.headers.get("Authorization", "")

    return token in authorized_tokens


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
        return {
            "socks_host": "127.0.0.1",
            "socks_port": 1080
        }

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

            today = 0
            script = 0

            if "today=" in part:
                today = int(part.split("today=")[1].split()[0])

            if "script=" in part:
                script = int(part.split("script=")[1].split()[0])

            accounts.append({
                "today": today,
                "script": script
            })

        except:
            continue

    return accounts


def reader():

    global latest_stats
    global runtime_error

    for line in process.stdout:

        line = line.strip()

        logs.append(line)

        if "ERROR" in line and line not in ignored_errors:
            runtime_error = line

        m = stats_pattern.search(line)

        if m:

            latest_stats["active"] = int(m.group(1))
            latest_stats["sessions"] = f"{m.group(2)}/{m.group(3)}"

            latest_stats["upload_kb"] = to_kb(m.group(4))
            latest_stats["download_kb"] = to_kb(m.group(5))

        acc = parse_accounts(line)

        if acc:

            latest_stats["today_used"] = sum(a["today"] for a in acc)
            latest_stats["session_used"] = sum(a["script"] for a in acc)
            latest_stats["quota_total"] = len(acc) * QUOTA_PER_ACCOUNT


@app.post("/login")
async def login(request: Request):

    data = await request.json()

    cfg = load_config()

    real_password = cfg.get("socks_pass", "")

    if data.get("password") != real_password:
        return {"ok": False}

    token = os.urandom(32).hex()

    authorized_tokens.add(token)

    return {
        "ok": True,
        "token": token
    }


@app.post("/ignore-error")
async def ignore_error(request: Request):

    if not require_auth(request):
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    global runtime_error

    data = await request.json()

    err = data.get("error")

    if err:
        ignored_errors.add(err)

    runtime_error = None

    return {"ok": True}


@app.get("/toggle")
def toggle(request: Request):

    if not require_auth(request):
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    global process
    global logs
    global latest_stats
    global runtime_error
    global ignored_errors

    if not check_integrity():
        return {"running": False}

    if process and process.poll() is None:

        process.terminate()

        ignored_errors = set()
        runtime_error = None

        return {"running": False}

    logs = []
    latest_stats = {}
    runtime_error = None

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
def status(request: Request):

    if not require_auth(request):
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    return {
        "running": process and process.poll() is None,
        "stats": latest_stats,
        "startup_error": startup_error,
        "runtime_error": runtime_error
    }


@app.get("/logs")
def get_logs(request: Request):

    if not require_auth(request):
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    return {
        "logs": logs[-200:]
    }


@app.get("/config")
def get_config(request: Request):

    if not require_auth(request):
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    return load_config()


@app.post("/config/update")
async def update_config(request: Request):

    if not require_auth(request):
        return JSONResponse({"error":"unauthorized"}, status_code=401)

    data = await request.json()

    cfg = load_config()

    cfg["socks_host"] = data.get("socks_host", "127.0.0.1")
    cfg["socks_port"] = int(data.get("socks_port", 1080))
    cfg["socks_user"] = data.get("socks_user", "")
    cfg["socks_pass"] = data.get("socks_pass", "")

    save_config(cfg)

    return {"status":"saved"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=HTML_PAGE)