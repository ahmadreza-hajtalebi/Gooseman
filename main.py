from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import requests
import json
import os
import re
import subprocess
import threading
import sys

app = FastAPI()

APP_VERSION = "beta"
REPO_URL = "https://api.github.com/repos/Aydiniyom/Gooseman/releases/latest"

# =========================
# STATIC
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

# =========================
# PATHS
# =========================

def get_binary_path():
    if sys.platform.startswith("win"):
        return os.path.join(BASE_DIR, "goose-client.exe")
    return os.path.join(BASE_DIR, "goose-client")

QUOTA_PER_ACCOUNT = 20_000

CONFIG_PATH = os.path.join(BASE_DIR, "client_config.json")
BINARY_PATH = get_binary_path()

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
# AUTH
# =========================

def unauthorized():
    return JSONResponse({"error": "unauthorized"}, status_code=401)

def require_auth(request: Request):
    token = request.headers.get("Authorization", "")
    return token in authorized_tokens

# =========================
# CONFIG
# =========================

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {
            "socks_host": "127.0.0.1",
            "socks_port": 1080,
            "socks_user": "",
            "socks_pass": "",
            "quota_limit": 0
        }

    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# =========================
# UTILS
# =========================

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
            today = int(part.split("today=")[1].split()[0]) if "today=" in part else 0
            script = int(part.split("script=")[1].split()[0]) if "script=" in part else 0

            accounts.append({"today": today, "script": script})

        except:
            pass

    return accounts

# =========================
# HELPERS
# =========================

def check_for_updates():
    try:
        r = requests.get(
            REPO_URL,
            timeout=5
        )

        if r.status_code != 200:
            return {"ok": False}

        data = r.json()

        latest = data.get("tag_name", "")

        return {
            "ok": True,
            "update_available": latest != APP_VERSION,
            "latest_version": latest,
            "current_version": APP_VERSION
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_app_version():

    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=BASE_DIR
        ).decode().strip().split("-")[0]

    except:
        return "beta"

APP_VERSION = get_app_version()

def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except:
        return default

# =========================
# PROCESS READER
# =========================

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

            cfg = load_config()
            quota_limit = int(cfg.get("quota_limit", 0))

            current_session = sum(a["script"] for a in acc)

            if (
                quota_limit > 0 and
                current_session >= quota_limit and
                process and
                process.poll() is None
            ):
                logs.append(
                    f"[Gooseman] Session quota limit reached ({current_session}/{quota_limit}). Stopping Goose."
                )

                process.terminate()

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

    get_app_version()

    return {"ok": True, "token": token}

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

    global process, logs, latest_stats, runtime_error, ignored_errors

    if not require_auth(request):
        return unauthorized()

    if process and process.poll() is None:
        process.terminate()
        ignored_errors.clear()
        runtime_error = None
        return {"running": False}

    logs = []
    latest_stats = {}
    runtime_error = None

    process = subprocess.Popen(
        [get_binary_path(), "-config", "client_config.json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=BASE_DIR,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    threading.Thread(target=reader, daemon=True).start()

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
        "version": APP_VERSION
    }


@app.get("/logs")
def get_logs(request: Request):

    if not require_auth(request):
        return unauthorized()

    return {"logs": logs[-200:]}


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

    cfg["socks_host"] = data.get("socks_host", cfg["socks_host"])
    cfg["socks_port"] = int(data.get("socks_port", cfg["socks_port"]))
    cfg["socks_user"] = data.get("socks_user", cfg["socks_user"])
    cfg["socks_pass"] = data.get("socks_pass", cfg["socks_pass"])
    cfg["quota_limit"] = safe_int(
        data.get("quota_limit", cfg.get("quota_limit", 0))
    )
    
    save_config(cfg)

    return {"status": "saved"}


@app.post("/update")
def update_dashboard(request: Request):

    if not require_auth(request):
        return unauthorized()

    try:
        subprocess.check_call(["git", "pull"], cwd=BASE_DIR)
        return {"ok": True}

    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/check-updates")
def manual_check_updates(request: Request):

    if not require_auth(request):
        return unauthorized()

    return check_for_updates()

@app.get("/")
def dashboard():
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))