const $ = id => document.getElementById(id);

let running = false;
let authToken = localStorage.getItem('goose_token');
let chart;
let currentConfig = {};
let selectedAccount = null;

const ENDPOINTS = {
    login: '/auth/login',
    status: '/client/status',
    start: '/client/start',
    stop: '/client/stop',
    config: '/config',
    update: '/config/update',
    logs: '/logs'
};

// ==========================================
// 1. API & AUTH
// ==========================================
async function api(url, options = {}) {
    options.headers = {
        ...(options.headers || {}),
        'Content-Type': 'application/json',
        'Authorization': authToken || ""
    };
    try {
        const r = await fetch(url, options);
        if (r.status === 401) {
            $("loginOverlay").style.display = "flex";
            return null;
        }
        return await r.json();
    } catch (e) {
        console.error("API Error:", e);
        return null;
    }
}

async function login() {
    const password = $("loginPassword").value;
    const r = await fetch(ENDPOINTS.login, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password })
    });
    
    if (r.ok) {
        const data = await r.json();
        authToken = data.token;
        localStorage.setItem("goose_token", authToken);
        $("loginOverlay").style.display = "none";
        initApp();
    } else {
        $("loginError").classList.remove("hidden");
        $("loginPassword").value = "";
    }
}

// ==========================================
// 2. UI UTILS & CHART
// ==========================================
function toggleVis(id) {
    const el = $(id);
    if (el) el.type = el.type === "password" ? "text" : "password";
}

function showToast(message, type = "success", duration = 2500) {
    let container = $("toastContainer");
    if (!container) {
        container = document.createElement("div");
        container.id = "toastContainer";
        container.className = "fixed bottom-4 right-4 z-[999] flex flex-col gap-2";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `bg-gray-900 border border-white/10 text-white p-4 rounded-xl shadow-lg flex justify-between items-center min-w-[250px] transition-all duration-300 transform translate-y-10 opacity-0`;
    if(type === "error") toast.style.borderLeft = "4px solid #ef4444";
    else toast.style.borderLeft = "4px solid #10b981";
    
    toast.innerHTML = `<div style="flex:1">${message}</div><button class="ml-4 text-gray-500 hover:text-white" onclick="this.parentElement.remove()">✕</button>`;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.remove("translate-y-10", "opacity-0"));
    setTimeout(() => {
        toast.classList.add("opacity-0");
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

const chartData = { labels: [], u: [], d: [], s: [], t: [], scr: [] };

function initChart() {
    const ctx = $("myChart").getContext("2d");
    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: chartData.labels,
            datasets: [
                { label: "Upload KB", data: chartData.u, borderColor: "#10b981", tension: 0.35, borderWidth: 2 },
                { label: "Download KB", data: chartData.d, borderColor: "#3b82f6", tension: 0.35, borderWidth: 2 },
                { label: "Session Quota", data: chartData.s, borderColor: "#f59e0b", tension: 0.35, borderWidth: 2 },
                { label: "Today Quota", data: chartData.t, borderColor: "#ef4444", tension: 0.35, borderWidth: 2 },
                { label: "Script Quota", data: chartData.scr, borderColor: "#c084fc", tension: 0.35, borderWidth: 2 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } }, x: { display: false } },
            plugins: { legend: { labels: { color: "rgba(255,255,255,0.7)" } } }
        }
    });
}

function updateChart(stats) {
    if (!chart || !stats) return;
    const now = new Date().toLocaleTimeString();
    chartData.labels.push(now);

    const parseVal = (v) => {
        if (typeof v === 'string') {
            if (v.includes("MB")) return parseFloat(v) * 1024;
            if (v.includes("GB")) return parseFloat(v) * 1024 * 1024;
            return parseFloat(v) || 0;
        }
        return v || 0;
    };

    let up = 0, down = 0, sess = 0, tdy = 0, scr = 0;
    if (stats.global) {
        up = parseVal(stats.global.upload_str);
        down = parseVal(stats.global.download_str);
        sess = parseInt(stats.global.sessions?.split('/')[0]) || 0;
    }
    if (stats.accounts) {
        tdy = stats.accounts.reduce((s, a) => s + (a.today || 0), 0);
        scr = stats.accounts.reduce((s, a) => s + (a.script || 0), 0);
    }

    chartData.u.push(up); chartData.d.push(down);
    chartData.s.push(sess); chartData.t.push(tdy); chartData.scr.push(scr);

    if (chartData.labels.length > 30) {
        chartData.labels.shift(); chartData.u.shift(); chartData.d.shift();
        chartData.s.shift(); chartData.t.shift(); chartData.scr.shift();
    }
    chart.update('none');
}

// ==========================================
// 3. SETTINGS & CONFIG
// ==========================================
function handleSettingsClick() {
    if (running) {
        showToast("Cannot access settings while the client is running. Please stop it first.", "error", 4000);
        return;
    }
    openSettings();
}

function openSettings() {
    $("settingsModal").classList.remove("hidden");
    loadConfigIntoUI();
}
function closeSettings() {
    $("settingsModal").classList.add("hidden");
}

async function loadConfigIntoUI() {
    currentConfig = await api(ENDPOINTS.config);
    if (!currentConfig) return;

    $("tunnel_key").value = currentConfig.tunnel_key || "";
    $("socks_host").value = currentConfig.socks_host || "127.0.0.1";
    $("socks_port").value = currentConfig.socks_port || "1080";
    $("socks_user").value = currentConfig.socks_user || "";
    $("socks_pass").value = currentConfig.socks_pass || "";
    
    $("google_host").value = currentConfig.google_host || "";
    $("sni").value = (currentConfig.sni || []).join(", ");
    $("coalesce").value = currentConfig.coalesce_step_ms || 0;
    $("idle_slots").value = currentConfig.idle_slots_per_bucket || 1;
    $("debug_timing").checked = currentConfig.debug_timing || false;

    const hasPass = currentConfig.dashboard_password && currentConfig.dashboard_password.trim() !== "";
    const chk = $("enableDashboardAuth");
    if(chk) {
        chk.checked = hasPass;
        $("dash_pass_container").classList.toggle("hidden", !hasPass);
        $("dashboard_pass").value = currentConfig.dashboard_password || "";
    }
    if($("quota_limit")) {
        $("quota_limit").value = currentConfig.quota_limit || "";
    }
    
    // نمایش یا مخفی کردن دکمه قفل در هدر
    const lockBtn = $("lockBtn");
    if(lockBtn) {
        if(hasPass) lockBtn.classList.remove("hidden");
        else lockBtn.classList.add("hidden");
    }
    
    renderAccountList();
}

async function saveAllConfig() {
    // ذخیره با حفظ ترتیب اکانت‌ها
    if (selectedAccount) {
        const lines = $("scriptIds").value.split("\n").map(l => l.trim()).filter(l => l);
        const accountOrder = [...new Set(currentConfig.script_keys.map(k => k.account))];
        let newScriptKeys = [];
        for (let a of accountOrder) {
            if (a === selectedAccount) {
                newScriptKeys.push(...lines.map(id => ({ id, account: a })));
            } else {
                newScriptKeys.push(...currentConfig.script_keys.filter(k => k.account === a));
            }
        }
        currentConfig.script_keys = newScriptKeys;
    }

    currentConfig.tunnel_key = $("tunnel_key").value;
    currentConfig.socks_host = $("socks_host").value;
    currentConfig.socks_port = parseInt($("socks_port").value) || 1080;
    currentConfig.socks_user = $("socks_user").value;
    currentConfig.socks_pass = $("socks_pass").value;
    
    currentConfig.google_host = $("google_host").value;
    currentConfig.sni = $("sni").value.split(",").map(s => s.trim()).filter(s => s);
    currentConfig.coalesce_step_ms = parseInt($("coalesce").value) || 0;
    currentConfig.idle_slots_per_bucket = parseInt($("idle_slots").value) || 1;
    currentConfig.debug_timing = $("debug_timing").checked;

    const chk = $("enableDashboardAuth");
    if(chk && chk.checked) {
        currentConfig.dashboard_password = $("dashboard_pass").value;
    } else {
        currentConfig.dashboard_password = "";
    }
    if($("quota_limit")) {
        currentConfig.quota_limit = parseInt($("quota_limit").value) || 0;
    }

    // آپدیت آنی دکمه قفل روی صفحه بعد از ذخیره کردن تنظیمات
    const lockBtn = $("lockBtn");
    if(lockBtn) {
        if(currentConfig.dashboard_password) lockBtn.classList.remove("hidden");
        else lockBtn.classList.add("hidden");
    }

    const res = await api(ENDPOINTS.update, { method: "POST", body: JSON.stringify(currentConfig) });
    if (res && res.status === "saved") {
        showToast("Configuration saved successfully", "success");
        closeSettings();
    }
}

// ==========================================
// 4. ACCOUNT MANAGER
// ==========================================
function renderAccountList() {
    const list = $("accountList");
    if(!list) return;
    list.innerHTML = "";
    if(!currentConfig.script_keys) currentConfig.script_keys = [];
    
    const accounts = [...new Set(currentConfig.script_keys.map(k => k.account))];
    accounts.forEach(acc => {
        const div = document.createElement("div");
        const isSelected = selectedAccount === acc;
        div.className = `p-3 rounded-xl cursor-pointer transition-all flex justify-between items-center mb-2 border ${isSelected ? 'bg-blue-600/20 border-blue-500 text-white' : 'bg-white/5 border-white/5 hover:bg-white/10 text-gray-300'}`;
        
        // اضافه کردن کلیک به کل کادر اکانت
        div.onclick = () => selectAccount(acc);
        
        div.innerHTML = `
            <span class="font-bold text-sm flex-1 cursor-pointer">${acc}</span>
            <div class="flex gap-2">
                <button onclick="renameAccount('${acc}', event)" class="text-gray-400 hover:text-white relative z-10" title="Rename Account">✏️</button>
                <button onclick="deleteAccount('${acc}', event)" class="text-red-400 hover:text-red-500 relative z-10" title="Delete Account">🗑️</button>
            </div>
        `;
        list.appendChild(div);
    });
}

function renameAccount(oldName, event) {
    event.stopPropagation();
    const newName = prompt(`Enter new name for account "${oldName}":`, oldName);
    if (newName && newName.trim() && newName.trim() !== oldName) {
        currentConfig.script_keys.forEach(k => {
            if (k.account === oldName) k.account = newName.trim();
        });
        if (selectedAccount === oldName) selectedAccount = newName.trim();
        renderAccountList();
        if (selectedAccount) selectAccount(selectedAccount);
    }
}

function deleteAccount(accName, event) {
    event.stopPropagation();
    if (confirm(`Are you sure you want to completely delete account "${accName}" and all its scripts?`)) {
        currentConfig.script_keys = currentConfig.script_keys.filter(k => k.account !== accName);
        if (selectedAccount === accName) {
            selectedAccount = null;
            $("accountDetails").classList.add("hidden");
        }
        renderAccountList();
    }
}

function selectAccount(acc) {
    if (selectedAccount === acc) return; 
    
    // ذخیره خودکار اسکریپت‌ها با حفظ ترتیب (جلوگیری از باگ پریدن اکانت)
    if (selectedAccount && !$("accountDetails").classList.contains("hidden")) {
        const lines = $("scriptIds").value.split("\n").map(l => l.trim()).filter(l => l);
        const accountOrder = [...new Set(currentConfig.script_keys.map(k => k.account))];
        let newScriptKeys = [];
        for (let a of accountOrder) {
            if (a === selectedAccount) {
                newScriptKeys.push(...lines.map(id => ({ id, account: a })));
            } else {
                newScriptKeys.push(...currentConfig.script_keys.filter(k => k.account === a));
            }
        }
        currentConfig.script_keys = newScriptKeys;
    }
    
    selectedAccount = acc;
    renderAccountList();
    $("accountDetails").classList.remove("hidden");
    $("selectedAccountName").innerText = `${acc}`;
    const ids = currentConfig.script_keys.filter(k => k.account === acc).map(k => k.id).join("\n");
    $("scriptIds").value = ids;
}

function addNewAccount() {
    const name = prompt("Enter new account name (e.g. Account3):");
    if (name && name.trim()) {
        currentConfig.script_keys.push({ id: "", account: name.trim() });
        selectedAccount = name.trim();
        renderAccountList();
        selectAccount(selectedAccount);
    }
}

let sessionPercentageMode = false;

function toggleSessionPercentage() {
    sessionPercentageMode = !sessionPercentageMode;
    updateDashboard();
}

function lockDashboard() {
    authToken = null;
    localStorage.removeItem("goose_token");
    $("loginOverlay").style.display = "flex";
    $("loginPassword").value = "";
    showToast("Dashboard Locked", "success");
}

// ==========================================
// 5. MONITORING CYCLES
// ==========================================
async function toggleClient() {
    if (running) {
        if (!confirm("Are you sure you want to STOP the Goose client?")) return;
    }
    const action = running ? ENDPOINTS.stop : ENDPOINTS.start;
    const res = await api(action, { method: "POST" });
    if (res && res.status === "error") showToast("Core error: " + res.message, "error", 5000);
}

async function updateDashboard() {
    const data = await api(ENDPOINTS.status);
    if (!data) return;

    running = data.running;
    const btn = $("mainActionBtn");
    const statusBox = $("statusIndicator");
    const statusText = $("statusText");

    if (running) {
        btn.innerText = "STOP CLIENT";
        btn.className = "bg-red-600 hover:bg-red-700 px-8 py-3 rounded-2xl font-bold transition-all shadow-lg uppercase tracking-wider text-sm";
        
        if (data.stats && data.stats.quota_exhausted) {
            statusBox.className = "flex items-center gap-2 px-4 py-2 rounded-full bg-yellow-500/10 border border-yellow-500/20 text-yellow-500 animate-pulse";
            statusText.innerText = "EXHAUSTED";
        } else {
            statusBox.className = "flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 font-bold";
            statusText.innerText = "RUNNING";
        }
        
        if (data.stats) {
            if(data.stats.global) {
                $("statTraffic").innerText = `${data.stats.global.upload_str || "0 B"} / ${data.stats.global.download_str || "0 B"}`;
                $("statActive").innerText = data.stats.global.active || "0";
                $("statEndpoints").innerText = `${data.stats.global.endpoints_active || 0} / ${data.stats.global.endpoints_total || 0}`;
                
                const sUsed = parseInt(data.stats.global.sessions.split("/")[0]) || 0;
                const sLim = parseInt(data.stats.global.sessions.split("/")[1]) || 0;
                
                if (sessionPercentageMode && sLim > 0) {
                    $("statSession").innerText = `${((sUsed / sLim) * 100).toFixed(1)}%`;
                } else {
                    $("statSession").innerText = `${sUsed} / ${sLim}`;
                }
            }

            if (data.stats.accounts && data.stats.accounts.length > 0) {
                const container = $("dynamicAccounts");
                container.innerHTML = "";
                
                data.stats.accounts.forEach(acc => {
                    const eps = (data.stats.endpoints || []).filter(e => e.account === acc.name);
                    
                    let epsHtml = eps.map(e => `
                <div class="flex justify-between items-center text-[11px] mt-2 p-2 ${e.bl ? 'bg-red-900/30 border-red-500/30' : 'bg-black/40 border-white/5'} border rounded-lg">
                    <span class="font-mono text-gray-300 w-16 truncate" title="${e.id}">${e.id}</span>
                    <span class="text-emerald-400" title="OK">O:${e.ok}</span>
                    <span class="text-red-400" title="Fail">F:${e.fail}</span>
                    <span class="text-yellow-500" title="Today">T:${e.today}</span>
                    <span class="text-blue-400" title="Script Quota">S:${e.script}</span>
                    ${e.bl ? `<span class="text-yellow-500 font-bold ml-1 animate-pulse" title="Blacklisted">BL</span>` : ''}
                </div>
            `).join("");

            const accCard = document.createElement("div");
            accCard.className = "bg-gray-900/60 border border-white/10 p-4 rounded-2xl shadow-lg";
            accCard.innerHTML = `
                <div class="flex justify-between items-center mb-2 pb-2 border-b border-white/10">
                    <span class="font-bold text-sm text-blue-400 truncate">${acc.name}</span>
                    <div class="flex gap-2">
                        <span class="text-[9px] bg-black/60 px-2 py-1 rounded-md text-gray-300 font-mono tracking-wide">Tdy: ${acc.today}/20k</span>
                        <span class="text-[9px] bg-blue-900/40 px-2 py-1 rounded-md text-blue-300 font-mono tracking-wide">Scr: ${acc.script}/20k</span>
                    </div>
                </div>
                <div>${epsHtml || '<span class="text-[10px] text-gray-500 italic">No deployments yet</span>'}</div>
            `;
                    container.appendChild(accCard);
                });
            }

            updateChart(data.stats);
        }
    } else {
        btn.innerText = "START CLIENT";
        btn.className = "bg-blue-600 hover:bg-blue-700 px-8 py-3 rounded-2xl font-bold transition-all shadow-lg uppercase tracking-wider text-sm";
        statusBox.className = "flex items-center gap-2 px-4 py-2 rounded-full bg-red-500/10 border border-red-500/20 text-red-500";
        statusText.innerText = "STOPPED";

        // ریست کردن آمار در صورت توقف کلاینت
        $("statTraffic").innerText = "0 B / 0 B";
        $("statActive").innerText = "0";
        $("statEndpoints").innerText = "0 / 0";
        $("statSession").innerText = "0 / 0";
        $("dynamicAccounts").innerHTML = '<div class="text-xs text-gray-500 pl-2">Waiting for engine data...</div>';
    }
}

async function updateLogs() {
    const data = await api(ENDPOINTS.logs);
    if (data && data.logs) {
        const logDiv = $("logs");
        const box = $("logBox");
        if(!logDiv || !box) return;
        
        const savedScrollTop = box.scrollTop; // ذخیره مکان فعلی اسکرول
        const isNearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50;
        
        logDiv.innerHTML = data.logs.map(line => {
            let color = "text-emerald-400/80";
            if (line.toLowerCase().includes("error") || line.toLowerCase().includes("panic") || line.toLowerCase().includes("exhausted")) color = "text-red-400 font-bold";
            if (line.toLowerCase().includes("ready")) color = "text-blue-400 font-bold";
            return `<div class="${color} mb-1">${line}</div>`;
        }).join("");
        
        if(isNearBottom) {
            box.scrollTop = box.scrollHeight;
        } else {
            box.scrollTop = savedScrollTop; // جلوگیری از پرش به بالا
        }
    }
}

function openSettings() {
    if (running) {
        alert("برنامه در حال اجراست! تنظیمات قفل شده است. برای تغییرات، ابتدا اتصال را قطع کنید.");
        return;
    }
    $("settingsModal").classList.remove("hidden");
    loadConfigIntoUI();
}

function closeSettings() {
    $("settingsModal").classList.add("hidden");
}

// ==========================================
// 6. UPDATES & BOOT
// ==========================================
async function checkUpdate(manual = false) {
    if (manual) {
        $("checkUpdateBtn").innerText = "Checking...";
        $("checkUpdateBtn").disabled = true;
    }
    try {
        const res = await api('/check-updates');
        if (res && res.ok && res.latest !== res.current) {
            $("versionText").innerText = `Update Available: ${res.latest} (Current: ${res.current})`;
            $("versionText").classList.replace("text-gray-400", "text-blue-400");
            $("updateIndicator").classList.replace("bg-white/30", "bg-blue-500");
            $("updateIndicator").classList.add("animate-ping");
            $("updateLink").classList.remove("hidden");
            $("checkUpdateBtn").classList.add("hidden");
            if (manual) showToast(`New version ${res.latest} is available!`, "success");
        } else if (manual) {
            showToast("You are using the latest version.", "success");
            $("checkUpdateBtn").innerText = "Check for Updates";
            $("checkUpdateBtn").disabled = false;
        }
    } catch (e) {
        if (manual) {
            showToast("Could not connect to GitHub.", "error");
            $("checkUpdateBtn").innerText = "Check for Updates";
            $("checkUpdateBtn").disabled = false;
        }
    }
}

async function initApp() {
    const checkAuth = await api(ENDPOINTS.status);
    if(checkAuth !== null) {
        $("loginOverlay").style.display = "none";
        initChart();
        setInterval(updateDashboard, 2000);
        setInterval(updateLogs, 1500);
        checkUpdate(false);
    }
}

// ارسال سیگنال تپش قلب برای جلوگیری از بسته شدن خودکار سرور
setInterval(() => {
    fetch(ENDPOINTS.status, { headers: { 'Authorization': authToken || "" } }).catch(() => {});
}, 3000);

initApp();