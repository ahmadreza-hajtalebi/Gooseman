from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

import json
import os
import re
import subprocess
import threading

app = FastAPI()

# =========================
# CONFIG
# =========================

QUOTA_PER_ACCOUNT = 20_000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "client_config.json")
BINARY_PATH = os.path.join(BASE_DIR, "goose-client")

# =========================
# STATE
# =========================

process = None

logs = []
latest_stats = {}

startup_error = None
runtime_error = None

ignored_errors = set()
authorized_tokens = set()

stats_pattern = re.compile(
    r"active=(\d+).*sessions=(\d+)/(\d+).*bytes=([\d\.A-Z]+)/([\d\.A-Z]+)"
)

# =========================
# HTML
# =========================

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />

<title>Gooseman</title>

<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

:root{
  --glass:rgba(255,255,255,.045);
  --border:rgba(255,255,255,.08);
  --blue:#2563eb;
  --green:#22c55e;
  --red:#ef4444;
}

*{
  box-sizing:border-box;
}

html,
body{
  min-height:100%;
}

html{
  scroll-behavior:smooth;
}

body{
  margin:0;
  min-height:100vh;
  overflow-x:hidden;

  background:
    radial-gradient(circle at top left,#172554 0%,transparent 35%),
    radial-gradient(circle at bottom right,#3b0764 0%,transparent 35%),
    #0b0f19;

  background-repeat:no-repeat;
  background-attachment:fixed;

  color:white;
  font-family:sans-serif;
}

body::before{
  content:"";
  position:fixed;
  inset:0;
  background:rgba(255,255,255,.015);
  pointer-events:none;
}

.glass{
  background:var(--glass);
  border:1px solid var(--border);
  backdrop-filter:blur(18px);
  box-shadow:
    0 10px 40px rgba(0,0,0,.25),
    inset 0 1px rgba(255,255,255,.04);
  transition:.25s ease;
}

.glass:hover{
  transform:translateY(-2px);
  border-color:rgba(255,255,255,.14);
}

.btn{
  transition:.2s ease;
}

.btn:hover{
  transform:translateY(-2px);
  opacity:.96;
}

.btn:active{
  transform:scale(.98);
}

.btn:disabled{
  opacity:.45;
  cursor:not-allowed;
}

input{
  width:100%;
  min-width:0;
  outline:none;
  border:1px solid transparent;
  transition:.2s ease;
}

input:focus{
  border-color:rgba(59,130,246,.5);
  box-shadow:
    0 0 0 4px rgba(59,130,246,.08),
    0 0 20px rgba(59,130,246,.15);
}

.log-stopped{
  opacity:.42;
  filter:saturate(.7);
}

.glow{
  position:absolute;
  width:400px;
  height:400px;
  opacity:.08;
  filter:blur(120px);
  border-radius:999px;
  pointer-events:none;
}

.glow.blue{
  background:var(--blue);
  top:-120px;
  left:-120px;
}

.glow.purple{
  background:#9333ea;
  bottom:-120px;
  right:-120px;
}

::-webkit-scrollbar{
  width:10px;
}

::-webkit-scrollbar-thumb{
  background:rgba(255,255,255,.12);
  border-radius:999px;
}

@keyframes pulse{
  50%{
    box-shadow:0 0 25px rgba(34,197,94,.28);
  }
}

</style>

</head>

<body>

<div class="glow blue"></div>
<div class="glow purple"></div>

<!-- LOGIN -->

<div
  id="loginOverlay"
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xl p-4"
>

  <div
    class="glass w-full max-w-md rounded-[2rem] p-6 sm:p-7 overflow-hidden"
  >

    <h1 class="text-3xl font-bold text-center mb-2 break-words">
      🦢 Gooseman
    </h1>

    <p class="text-sm text-gray-400 text-center mb-6">
      Enter the SOCKS5 password
    </p>

    <input
      id="loginPassword"
      type="password"
      placeholder="SOCKS5 password"
      class="bg-gray-900 rounded-xl p-3 mb-4"
    />

    <button
      onclick="login()"
      class="btn w-full bg-blue-600 rounded-xl py-3 font-semibold"
    >
      Unlock
    </button>

    <div
      id="loginError"
      class="hidden text-red-400 text-sm text-center mt-3"
    >
      Invalid password
    </div>

  </div>

</div>

<!-- ERROR -->

<div
  id="errorBox"
  class="hidden fixed top-0 inset-x-0 z-50 p-3"
>

  <div class="glass rounded-xl p-4 flex justify-between items-center gap-4">

    <div
      id="errorText"
      class="text-red-400 font-semibold break-all"
    ></div>

    <div class="flex gap-2 shrink-0">

      <button
        onclick="restart()"
        class="btn bg-red-600 px-3 py-1 rounded-lg"
      >
        Restart
      </button>

      <button
        onclick="ignoreError()"
        class="btn bg-gray-600 px-3 py-1 rounded-lg"
      >
        Ignore
      </button>

    </div>

  </div>

</div>

<!-- MAIN -->

<div class="max-w-6xl mx-auto p-4 relative z-10">

  <!-- HEADER -->

  <div class="flex justify-between items-center mb-4 gap-3">

    <h1 class="text-2xl font-bold">
      🦢 Gooseman
    </h1>

    <div
      id="status"
      class="glass bg-gray-800/70 px-4 py-1.5 rounded-full text-sm"
    >
      Loading...
    </div>

  </div>

  <!-- TOGGLE -->

  <button
    id="toggleBtn"
    onclick="toggle()"
    class="btn w-full py-3 rounded-2xl bg-green-600 font-semibold text-lg"
  >
    Start Goose
  </button>

  <!-- STATS -->

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

  <!-- CHART -->

  <div class="glass p-5 mt-4 rounded-3xl">

    <div class="font-semibold mb-3">
      📊 Quota per usage (KB)
    </div>

    <div class="h-[280px]">
      <canvas id="chart"></canvas>
    </div>

  </div>

  <!-- CONFIG -->

  <div class="glass p-4 mt-4 rounded-2xl">

    <div class="font-semibold mb-3">
      ⚙️ SOCKS5 Config
    </div>

    <div class="grid md:grid-cols-2 gap-3">

      <input id="socks_host" placeholder="Host" class="bg-gray-900 p-3 rounded-xl" />
      <input id="socks_port" placeholder="Port" class="bg-gray-900 p-3 rounded-xl" />
      <input id="socks_user" placeholder="Username" class="bg-gray-900 p-3 rounded-xl" />
      <input id="socks_pass" type="password" placeholder="Password" class="bg-gray-900 p-3 rounded-xl" />

    </div>

    <button
      onclick="saveConfig()"
      class="btn mt-4 bg-blue-600 px-4 py-3 rounded-xl w-full font-semibold"
    >
      Save Configuration
    </button>

  </div>

  <!-- LOGS -->

  <div
    id="logBox"
    class="glass p-3 mt-4 rounded-2xl h-64 overflow-y-scroll font-mono text-xs log-stopped"
  >
    <div id="logs"></div>
  </div>

</div>


<script>

const $ = id => document.getElementById(id)

let running = false
let locked = false
let authToken = null
let ignoredError = null
let chart

const data = {
  labels: [],
  u: [],
  d: [],
  s: [],
  t: []
}

const api = async (url, options = {}) => {

  options.headers = {
    ...(options.headers || {}),
    Authorization: authToken || ""
  }

  const r = await fetch(url, options)

  if(r.status === 401){
    $("loginOverlay").style.display = "flex"
    throw new Error("Unauthorized")
  }

  return r
}

const fmt = v => {

  if(v > 1024 * 1024)
    return (v / 1024 / 1024).toFixed(2) + " GB"

  if(v > 1024)
    return (v / 1024).toFixed(2) + " MB"

  return v.toFixed(2) + " KB"
}

function sync(){

  const b = $("toggleBtn")

  $("status").style.animation =
    running ? "pulse 2s infinite" : "none"

  b.innerText = running
    ? "Stop Goose"
    : "Start Goose"

  b.classList.toggle("bg-green-600", !running)
  b.classList.toggle("bg-red-600", running)
}

function showError(msg){
  $("errorText").innerText = msg
  $("errorBox").classList.remove("hidden")
}

function hideError(){
  $("errorBox").classList.add("hidden")
}

function pushData(arr, value){

  arr.push(value)

  if(arr.length > 25)
    arr.shift()
}

async function login(){

  const r = await fetch("/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      password: $("loginPassword").value
    })
  })

  const d = await r.json()

  if(!d.ok)
    return $("loginError").classList.remove("hidden")

  authToken = d.token

  $("loginOverlay").style.display = "none"

  await loadConfig()
  await update()
}

async function toggle(){

  if(locked)
    return

  locked = true

  $("toggleBtn").disabled = true
  $("logs").innerHTML = ""

  const d = await (await api("/toggle")).json()

  running = d.running

  sync()

  setTimeout(() => {
    locked = false
    $("toggleBtn").disabled = false
  }, 3000)
}

async function loadConfig(){

  const c = await (await api("/config")).json()

  for(const k in c){
    if($(k))
      $(k).value = c[k]
  }
}

async function saveConfig(){

  await api("/config/update", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      socks_host: $("socks_host").value,
      socks_port: $("socks_port").value,
      socks_user: $("socks_user").value,
      socks_pass: $("socks_pass").value
    })
  })
}

async function ignoreError(){

  if(!ignoredError)
    return

  await api("/ignore-error", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      error: ignoredError
    })
  })

  hideError()
}

async function restart(){

  await toggle()

  setTimeout(toggle, 500)

  hideError()
}

async function update(){

  const s = await (await api("/status")).json()

  running = !!s.running

  sync()

  $("status").innerText =
    running ? "🟢 Running" : "🔴 Stopped"

  $("logBox").classList.toggle("log-stopped", !running)

  if(s.startup_error)
    showError(s.startup_error)

  if(s.runtime_error){
    ignoredError = s.runtime_error
    showError(s.runtime_error)
  }

  const st = s.stats || {}

  $("active").innerText = st.active ?? "-"
  $("sessions").innerText = st.sessions ?? "-"
  $("upload").innerText = fmt(st.upload_kb || 0)
  $("download").innerText = fmt(st.download_kb || 0)

  $("today").innerText =
    `${st.today_used || 0} / ~${st.quota_total || 0}`

  $("session").innerText =
    `${st.session_used || 0} / ~${st.quota_total || 0}`

  pushData(data.labels, "")
  pushData(data.u, st.upload_kb || 0)
  pushData(data.d, st.download_kb || 0)
  pushData(data.s, st.session_used || 0)
  pushData(data.t, st.today_used || 0)

  chart.update()

  const l = await (await api("/logs")).json()

  $("logs").innerHTML = l.logs.map(x => `
    <div class="py-1 border-b border-white/5 break-all">
      ${x}
    </div>
  `).join("")
}

function init(){

  chart = new Chart($("chart"), {

    type: "line",

    data: {
      labels: data.labels,

      datasets: [
        { label:"Upload KB", data:data.u, borderColor:"#22c55e", tension:.35 },
        { label:"Download KB", data:data.d, borderColor:"#3b82f6", tension:.35 },
        { label:"Session Quota", data:data.s, borderColor:"#f59e0b", tension:.35 },
        { label:"Today's Quota", data:data.t, borderColor:"#ef4444", tension:.35 }
      ]
    },

    options: {
      responsive: true,
      maintainAspectRatio: false
    }
  })
}

setInterval(async () => {

  if(!authToken)
    return

  try{
    await update()
  }catch{}

}, 3000)

init()

$("loginOverlay").style.display = "flex"

</script>

</body>
</html>
"""

# =========================
# HELPERS
# =========================

def unauthorized():
    return JSONResponse(
        {"error": "unauthorized"},
        status_code=401
    )


def require_auth(request: Request):

    token = request.headers.get("Authorization", "")

    return token in authorized_tokens


def check_integrity():

    global startup_error

    required = {
        CONFIG_PATH: "Missing client_config.json",
        BINARY_PATH: "Missing goose-client binary"
    }

    for path, err in required.items():

        if not os.path.exists(path):
            startup_error = err
            return False

    startup_error = None

    return True


def load_config():

    if not os.path.exists(CONFIG_PATH):

        return {
            "socks_host": "127.0.0.1",
            "socks_port": 1080,
            "socks_user": "",
            "socks_pass": ""
        }

    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):

    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def to_kb(value):

    if not value:
        return 0.0

    value = str(value).upper().strip()

    units = {
        "KB": 1,
        "MB": 1024,
        "GB": 1024 * 1024,
        "B": 1 / 1024
    }

    try:

        for unit, mult in units.items():

            if value.endswith(unit):
                return float(value[:-len(unit)]) * mult

        return float(value)

    except:
        return 0.0


def parse_accounts(line):

    if "accounts=[" not in line:
        return None

    raw = line.split("accounts=[", 1)[1].split("]", 1)[0]

    accounts = []

    for part in raw.split("|"):

        try:

            today = int(
                part.split("today=")[1].split()[0]
            ) if "today=" in part else 0

            script = int(
                part.split("script=")[1].split()[0]
            ) if "script=" in part else 0

            accounts.append({
                "today": today,
                "script": script
            })

        except:
            pass

    return accounts


def reader():

    global runtime_error

    for line in process.stdout:

        line = line.strip()

        logs.append(line)

        if "ERROR" in line and line not in ignored_errors:
            runtime_error = line

        m = stats_pattern.search(line)

        if m:

            latest_stats.update({
                "active": int(m.group(1)),
                "sessions": f"{m.group(2)}/{m.group(3)}",
                "upload_kb": to_kb(m.group(4)),
                "download_kb": to_kb(m.group(5))
            })

        acc = parse_accounts(line)

        if acc:

            latest_stats.update({
                "today_used": sum(a["today"] for a in acc),
                "session_used": sum(a["script"] for a in acc),
                "quota_total": len(acc) * QUOTA_PER_ACCOUNT
            })

# =========================
# ROUTES
# =========================

@app.post("/login")
async def login(request: Request):

    data = await request.json()

    if data.get("password") != load_config().get("socks_pass", ""):
        return {"ok": False}

    token = os.urandom(32).hex()

    authorized_tokens.add(token)

    return {
        "ok": True,
        "token": token
    }


@app.post("/ignore-error")
async def ignore_error(request: Request):

    global runtime_error

    if not require_auth(request):
        return unauthorized()

    err = (await request.json()).get("error")

    if err:
        ignored_errors.add(err)

    runtime_error = None

    return {"ok": True}


@app.get("/toggle")
def toggle(request: Request):

    global process
    global logs
    global latest_stats
    global runtime_error
    global ignored_errors

    if not require_auth(request):
        return unauthorized()

    if not check_integrity():
        return {"running": False}

    if process and process.poll() is None:

        process.terminate()

        ignored_errors.clear()
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

    threading.Thread(
        target=reader,
        daemon=True
    ).start()

    return {"running": True}


@app.get("/status")
def status(request: Request):

    if not require_auth(request):
        return unauthorized()

    return {
        "running": process and process.poll() is None,
        "stats": latest_stats,
        "startup_error": startup_error,
        "runtime_error": runtime_error
    }


@app.get("/logs")
def get_logs(request: Request):

    if not require_auth(request):
        return unauthorized()

    return {
        "logs": logs[-200:]
    }


@app.get("/config")
def get_config(request: Request):

    if not require_auth(request):
        return unauthorized()

    return load_config()


@app.post("/config/update")
async def update_config(request: Request):

    if not require_auth(request):
        return unauthorized()

    data = await request.json()

    cfg = {
        "socks_host": data.get("socks_host", "127.0.0.1"),
        "socks_port": int(data.get("socks_port", 1080)),
        "socks_user": data.get("socks_user", ""),
        "socks_pass": data.get("socks_pass", "")
    }

    save_config(cfg)

    return {"status": "saved"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(HTML_PAGE)