from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import requests
import json
import os
import re
import subprocess
import threading
import sys

app = FastAPI()

APP_VERSION = "1.0.0"
REPO_API = "https://api.github.com/repos/Aydiniyom/Gooseman/releases/latest"

# =========================
# STATIC
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print(BASE_DIR)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

# =========================
# SHUSH
# =========================

def get_binary_path():
    if sys.platform.startswith("win"):
        return os.path.join(BASE_DIR, "goose-client.exe")
    return os.path.join(BASE_DIR, "goose-client")

# =========================
# CONFIG
# =========================

QUOTA_PER_ACCOUNT = 20_000

CONFIG_PATH = os.path.join(BASE_DIR, "client_config.json")
BINARY_PATH = get_binary_path()

# =========================
# STATE
# =========================

update_available = False
latest_version = APP_VERSION

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

def check_for_updates():

    global update_available
    global latest_version

    try:

        r = requests.get(REPO_API, timeout=5)

        if r.status_code != 200:
            return

        data = r.json()

        latest = data.get("tag_name", "").replace("v", "")

        latest_version = latest

        update_available = latest != APP_VERSION

    except:
        pass

check_for_updates()

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

    binary = get_binary_path()

    process = subprocess.Popen(
      [binary, "-config", "client_config.json"],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      cwd=BASE_DIR,
      text=True,
      encoding="utf-8",
      errors="replace"
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
        "runtime_error": runtime_error,

        "version": APP_VERSION,
        "latest_version": latest_version,
        "update_available": update_available
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

    cfg = load_config()

    cfg["socks_host"] = data.get(
        "socks_host",
        cfg.get("socks_host", "127.0.0.1")
    )

    cfg["socks_port"] = int(
        data.get(
            "socks_port",
            cfg.get("socks_port", 1080)
        )
    )

    cfg["socks_user"] = data.get(
        "socks_user",
        cfg.get("socks_user", "")
    )

    cfg["socks_pass"] = data.get(
        "socks_pass",
        cfg.get("socks_pass", "")
    )

    save_config(cfg)

    return {
        "status": "saved"
    }

@app.post("/update")
def update_dashboard(request: Request):

    if not require_auth(request):
        return unauthorized()

    try:

        subprocess.check_call(
            ["git", "pull"],
            cwd=BASE_DIR
        )

        return {
            "ok": True
        }

    except Exception as e:

        return {
            "ok": False,
            "error": str(e)
        }

@app.get("/")
def dashboard():

    return FileResponse(
        os.path.join(BASE_DIR, "templates", "index.html")
    )