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
import webbrowser
import time

app = FastAPI()

APP_VERSION = "1.3.0"
CORE_VERSION = "1.6.0"
REPO_URL = "https://api.github.com/repos/Aydiniyom/Gooseman/releases/latest"

# ==============================================================================
# PATHS
# ==============================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS 
    WORK_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WORK_DIR = BASE_DIR

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

def get_binary_path():
    if sys.platform.startswith("win"):
        return os.path.join(WORK_DIR, "goose-client.exe")
    return os.path.join(WORK_DIR, "goose-client")

CONFIG_PATH = os.path.join(WORK_DIR, "client_config.json")
SECRET_PATH = os.path.join(WORK_DIR, ".gooseman_secret")
BINARY_PATH = get_binary_path()

# ==============================================================================
# STRICT ORIGINAL DEFAULT CONFIG
# ==============================================================================
DEFAULT_CONFIG = {
  "debug_timing": False,
  "socks_host": "127.0.0.1",
  "socks_port": 1080,
  "google_host": "216.239.38.120",
  "sni": ["www.google.com", "mail.google.com", "accounts.google.com"],
  "script_keys": [
    {"id": "REPLACE_WITH_DEPLOYMENT_ID", "account": "acct-a"},
    {"id": "OPTIONAL_SECOND_DEPLOYMENT_ID", "account": "acct-a"},
    {"id": "OPTIONAL_THIRD_DEPLOYMENT_ID", "account": "acct-b"}
  ],
  "tunnel_key": "REPLACE_WITH_OUTPUT_OF_scripts_gen-key.sh",
  "_comment_socks_auth": "Optional: require SOCKS5 username/password (RFC 1929). Both fields must be set together or both omitted.",
  "socks_user": "",
  "socks_pass": "",
  "_comment_coalesce": "Optional: adaptive uplink coalescing. Set coalesce_step_ms to a positive number to make a burst of TX operations wait a little for more operations before sending, which reduces Apps Script calls. A good starting range is 20-40 ms. Set it to 0 to turn coalescing off.",
  "coalesce_step_ms": 0,
  "_comment_idle_slots": "Optional download-throughput tuning. Default 1 (safe). Raise to 2 if each account has 2+ deployments — this may increase download throughput; leave at 1 for accounts with one deployment. Max 3. Omitting the field is equivalent to 1.",
  "idle_slots_per_bucket": 1
}

def ensure_config_exists():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)

# ==============================================================================
# DASHBOARD PASSWORD HANDLER
# ==============================================================================
def get_secrets():
    if os.path.exists(SECRET_PATH):
        try:
            with open(SECRET_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content.startswith("{"): return json.loads(content)
                else: return {"dashboard_password": content, "quota_limit": 0}
        except: pass
    return {"dashboard_password": "", "quota_limit": 0}

def save_secrets(secrets):
    with open(SECRET_PATH, "w", encoding="utf-8") as f:
        json.dump(secrets, f)

def get_dashboard_pass():
    return get_secrets().get("dashboard_password", "")

# ==============================================================================
# STATE & PARSER
# ==============================================================================
process = None
logs = []
latest_stats = {}
startup_error = None
runtime_error = None
authorized_tokens = set()

def parse_log_line(line):
    global latest_stats, runtime_error, process
    
    # 1. خوانش آمار اصلی
    m_global = re.search(r"active=(\d+)\s+sessions=([\d/]+)\s+frames=([\d/]+)\s+bytes=([\d\.A-Z]+)/([\d\.A-Z]+)\s+polls=([\d/]+)\s+rst=(\d+)\s+endpoints=([\d/]+)", line)
    if m_global:
        latest_stats["global"] = {
            "active": m_global.group(1), "sessions": m_global.group(2), "frames": m_global.group(3),
            "upload_str": m_global.group(4), "download_str": m_global.group(5),
            "polls": m_global.group(6), "rst": int(m_global.group(7)), "endpoints_active": m_global.group(8).split('/')[0], "endpoints_total": m_global.group(8).split('/')[1]
        }

    # 2. خوانش وضعیت اکانت‌ها (استخراج دقیق Today و Script)
    m_acc = re.search(r"accounts=\[(.*?)\]", line)
    if m_acc:
        acc_raw = m_acc.group(1).split(" | ")
        acc_list = []
        total_session = 0
        for a in acc_raw:
            parts = a.strip().split()
            if not parts: continue
            name = parts[0]
            t_val = int(re.search(r"today=(\d+)", a).group(1)) if re.search(r"today=(\d+)", a) else 0
            s_val = int(re.search(r"script=(\d+)", a).group(1)) if re.search(r"script=(\d+)", a) else 0
            total_session += t_val
            acc_list.append({"name": name, "today": t_val, "script": s_val})
        
        latest_stats["accounts"] = acc_list
        latest_stats["total_session_used"] = total_session
        
        secrets = get_secrets()
        limit = int(secrets.get("quota_limit", 0))
        if limit > 0 and total_session >= limit:
            latest_stats["quota_exhausted"] = True
            if process and process.poll() is None:
                process.terminate()

    # 3. خوانش وضعیت تک‌تک اسکریپت‌ها
    m_ep = re.search(r"endpoints:\s+(.*)", line)
    if m_ep:
        ep_raw = m_ep.group(1).split(" | ")
        ep_list = []
        for e in ep_raw:
            e = e.strip()
            if not e: continue
            id_acc = e.split()[0]
            ep_id = id_acc.split('@')[0] if '@' in id_acc else id_acc
            acc_name = id_acc.split('@')[1] if '@' in id_acc else "Unknown"
            
            ep_list.append({
                "id": ep_id[:8] + "..", "account": acc_name,
                "ok": re.search(r"ok=(\d+)", e).group(1) if re.search(r"ok=(\d+)", e) else "0",
                "fail": re.search(r"fail=(\d+)", e).group(1) if re.search(r"fail=(\d+)", e) else "0",
                "today": re.search(r"today=(\d+)", e).group(1) if re.search(r"today=(\d+)", e) else "0",
                "script": re.search(r"script=(\d+)", e).group(1) if re.search(r"script=(\d+)", e) else "0",
                "bl": re.search(r"bl=([^\s]+)", e).group(1) if re.search(r"bl=([^\s]+)", e) else None
            })
        latest_stats["endpoints"] = ep_list

    if "exhausted" in line.lower():
        latest_stats["quota_exhausted"] = True

    if "error" in line.lower() or "panic" in line.lower():
        if "context canceled" not in line.lower():
            runtime_error = line

def log_reader():
    global process, logs
    try:
        for line in iter(process.stdout.readline, b''):
            if line:
                decoded = line.decode("utf-8", errors="replace").strip()
                logs.append(decoded)
                if len(logs) > 1000:
                    logs.pop(0)
                parse_log_line(decoded)
    except Exception:
        pass

# ==============================================================================
# CORE & API
# ==============================================================================
def load_config():
    ensure_config_exists()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def require_auth(request: Request):
    dash_pass = get_dashboard_pass()
    if not dash_pass:
        return True
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header in authorized_tokens:
        return True
    return False

def unauthorized():
    return JSONResponse(status_code=401, content={"error": "Unauthorized"})

last_ping_time = time.time()

def watchdog():
    global last_ping_time, process
    while True:
        time.sleep(3)
        # اگر ۱۵ ثانیه گذشت و مرورگر تپش قلبی نفرستاد، یعنی بسته شده!
        if time.time() - last_ping_time > 15:
            if process is not None:
                process.terminate() # خاموش کردن موتور VPN
            os._exit(0) # بستن بی‌رحمانه کل برنامه از حافظه رم

@app.on_event("startup")
def startup_event():
    ensure_config_exists()
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000")
    threading.Thread(target=open_browser, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start() # روشن کردن سگ نگهبان

@app.get("/")
def serve_dashboard():
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))

@app.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    password = data.get("password", "")
    actual_password = get_dashboard_pass()
    
    if not actual_password or password == actual_password:
        import uuid
        token = str(uuid.uuid4())
        authorized_tokens.add(token)
        return {"token": token}
    return JSONResponse(status_code=401, content={"error": "Invalid password"})

@app.get("/client/status")
def client_status(request: Request):
    global last_ping_time
    last_ping_time = time.time() # ثبت زمان آخرین حضور مرورگر
    
    if not require_auth(request): return unauthorized()
    is_running = process is not None and process.poll() is None
    return {
        "running": is_running,
        "stats": latest_stats,
        "startup_error": startup_error,
        "runtime_error": runtime_error,
        "version": APP_VERSION,
        "core_version": CORE_VERSION
    }

@app.post("/client/start")
def start_client(request: Request):
    global process, logs, startup_error, runtime_error, latest_stats
    if not require_auth(request): return unauthorized()

    if process is not None and process.poll() is None:
        return {"status": "already_running"}

    if not os.path.exists(BINARY_PATH):
        startup_error = f"Binary not found: {BINARY_PATH}"
        return {"status": "error", "message": startup_error}

    logs.clear()
    latest_stats = {}
    startup_error = None
    runtime_error = None

    try:
        process = subprocess.Popen(
            [BINARY_PATH, "-config", CONFIG_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        )
        threading.Thread(target=log_reader, daemon=True).start()
        return {"status": "started"}
    except Exception as e:
        startup_error = str(e)
        return {"status": "error", "message": startup_error}

@app.post("/client/stop")
def stop_client(request: Request):
    global process
    if not require_auth(request): return unauthorized()

    if process is not None:
        process.terminate()
        process = None
        return {"status": "stopped"}
    return {"status": "not_running"}

@app.get("/config")
def get_config(request: Request):
    if not require_auth(request): return unauthorized()
    cfg = load_config()
    secrets = get_secrets()
    cfg["dashboard_password"] = secrets.get("dashboard_password", "")
    cfg["quota_limit"] = secrets.get("quota_limit", 0)
    return cfg

@app.post("/config/update")
async def update_config(request: Request):
    if not require_auth(request): return unauthorized()
    
    new_data = await request.json()
    cfg = load_config()
    secrets = get_secrets()
    
    if "dashboard_password" in new_data:
        secrets["dashboard_password"] = new_data["dashboard_password"]
    if "quota_limit" in new_data:
        secrets["quota_limit"] = int(new_data["quota_limit"])
    save_secrets(secrets)
        
    for key, value in new_data.items():
        if key in cfg and key not in ["dashboard_password", "quota_limit"]:
            cfg[key] = value
            
    save_config(cfg)
    return {"status": "saved"}

@app.get("/logs")
def get_logs(request: Request):
    if not require_auth(request): return unauthorized()
    return {"logs": logs[-200:]}

@app.get("/check-updates")
def check_updates(request: Request):
    if not require_auth(request): return unauthorized()
    try:
        r = requests.get(REPO_URL, timeout=5)
        if r.status_code == 200:
            return {"ok": True, "latest": r.json().get("tag_name", APP_VERSION), "current": f"v{APP_VERSION}"}
    except:
        pass
    return {"ok": False}

# ==============================================================================
# RUNNER (For EXE standalone compatibility)
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    import multiprocessing
    import socket
    
    if sys.platform.startswith("win"):
        multiprocessing.freeze_support()

    # جادوی جلوگیری از اجرای چندباره و حل چالش ۱۵ ثانیه
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    if is_port_in_use(5000):
        # اگر سرور از قبل روشن است، فقط مرورگر را باز کن و این پروسه جدید را ببند
        webbrowser.open("http://127.0.0.1:5000")
        sys.exit(0)

    # فیکس کردن باگ Uvicorn در حالت بدون کنسول (Windowed)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
        
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": True,
        "handlers": {
            "default": {
                "class": "logging.NullHandler",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "CRITICAL"},
            "uvicorn.error": {"handlers": ["default"], "level": "CRITICAL"},
            "uvicorn.access": {"handlers": ["default"], "level": "CRITICAL"},
        },
    }
    
    uvicorn.run(app, host="127.0.0.1", port=5000, log_config=LOGGING_CONFIG)
