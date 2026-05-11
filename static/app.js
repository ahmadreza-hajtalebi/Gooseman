const $ = id => document.getElementById(id)

let running = false
let locked = false
let authToken = null
let ignoredError = null
let chart
let previousStats = {}
let persistentDeltas = {
  upload: 0,
  download: 0,
  today: 0,
  session: 0
}
let sessionPercentageMode = false
let lastMeaningfulUpdate = Date.now()

function isMeaningfulChange(newStats, oldStats = {}) {
  const keys = ["upload_kb", "download_kb", "session_used", "today_used", "active"]
  return keys.some(k => (newStats[k] ?? 0) !== (oldStats[k] ?? 0))
}

function formatDelta(delta, isBytes=true) {
  if (!delta || delta <= 0) return ""

  if (isBytes) {
    if (delta > 1024 * 1024)
      return ` (+${(delta / 1024 / 1024).toFixed(2)} GB)`

    if (delta > 1024)
      return ` (+${(delta / 1024).toFixed(2)} MB)`

    return ` (+${delta.toFixed(2)} KB)`
  } else {
    return ` (+${delta})`
  }
}

const data = {
  labels: [],
  u: [],
  d: [],
  s: [],
  t: []
}

let lastGraphValues = {
  upload: null,
  download: null,
  session: null,
  today: null
}

const api = async (url, options = {}) => {
  options.headers = {
    ...(options.headers || {}),
    Authorization: authToken || ""
  }

  const r = await fetch(url, options)

  if (r.status === 401) {
    $("loginOverlay").style.display = "flex"
    throw new Error("Unauthorized")
  }

  return r
}

const fmt = v => {
  if (v > 1024 * 1024) return (v / 1024 / 1024).toFixed(2) + " GB"
  if (v > 1024) return (v / 1024).toFixed(2) + " MB"
  return v.toFixed(2) + " KB"
}

function formatPercentage(value, total) {
  if (!total || total <= 0) return "0%"
  return ((value / total) * 100).toFixed(2) + "%"
}

function toggleSessionMode() {

  sessionPercentageMode = !sessionPercentageMode

  $("sessionModeBtn").innerText =
    sessionPercentageMode ? "123" : "%"

  update()
}

function lockDashboard() {

  authToken = null

  $("loginPassword").value = ""

  $("loginOverlay").style.display = "flex"

  showToast("Dashboard locked", "success")
}

function sync() {
  const b = $("toggleBtn")

  $("status").style.animation = running ? "pulse 2s infinite" : "none"

  b.innerText = running ? "Stop Goose" : "Start Goose"

  b.classList.toggle("bg-green-600", !running)
  b.classList.toggle("bg-red-600", running)

  b.classList.toggle("btn-glow-green", !running)
  b.classList.toggle("btn-glow-red", running)
}

function showError(msg) {
  ignoredError = msg
  
  api("/ignore-error", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ error: msg })
  }).catch(() => {})
  
  showToast(msg, "error", 4000)
}

function hideError() {}

function pushData(arr, value) {
  arr.push(value)
  if (arr.length > 25) arr.shift()
}

async function login() {
  const r = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      password: $("loginPassword").value
    })
  })

  const d = await r.json()

  if (!d.ok)
    return $("loginError").classList.remove("hidden")

  authToken = d.token
  $("loginOverlay").style.display = "none"

  await loadConfig()
  await update()
  await updateCheck()
}

async function toggle() {
  if (locked) return

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

async function loadConfig() {
  const c = await (await api("/config")).json()

  for (const k in c) {
    if ($(k)) $(k).value = c[k]
  }
}

async function saveConfig() {
  try {
    await api("/config/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        socks_host: $("socks_host").value,
        socks_port: $("socks_port").value,
        socks_user: $("socks_user").value,
        socks_pass: $("socks_pass").value
      })
    })

    showToast("Configuration saved successfully", "success")

  } catch (e) {
    showToast("Failed to save configuration", "error")
  }
}

async function ignoreError() {
  if (!ignoredError) return

  await api("/ignore-error", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ error: ignoredError })
  })

  hideError()
}

async function restart() {
  await toggle()
  setTimeout(toggle, 500)
  hideError()
}

async function performUpdate() {
  const btn = $("updateBtn")
  let prevButtonText = btn.innerText

  btn.disabled = true
  btn.innerText = "Updating..."

  try {
    const r = await api("/update", { method: "POST" })
    const d = await r.json()

    if (!d.ok) {
      showToast(`Failed to update dashboard, error: ${d.error}`, "error", 5000)
      btn.innerText = prevButtonText
      btn.disabled = false
      return
    }

    showToast("Dashboard updated successfully. Restart Gooseman.", "success", 5000)
    btn.innerText = "Done!"

  } catch (e) {
    btn.innerText = prevButtonText
    btn.disabled = false
    showToast("Failed to update dashboard", "error")
  }
}

async function update() {
  const s = await (await api("/status")).json()

  running = !!s.running
  sync()

  $("status").innerText = running ? "🟢 Running" : "🔴 Stopped"
  $("logBox").classList.toggle("log-stopped", !running)

  if (s.startup_error) showError(s.startup_error)

  if (s.runtime_error) {
    ignoredError = s.runtime_error
    showError(s.runtime_error)
  }

  const st = s.stats || {}

  const currentStats = {
    upload_kb: st.upload_kb || 0,
    download_kb: st.download_kb || 0,
    sessions: st.sessions || "0/0",
    today_used: st.today_used || 0,
    session_used: st.session_used || 0,
    active: st.active || 0
  }

  if (isMeaningfulChange(currentStats, previousStats)) {
    lastMeaningfulUpdate = Date.now()
  }

  const uploadDelta =
  currentStats.upload_kb - (previousStats.upload_kb || 0)

  const downloadDelta =
    currentStats.download_kb - (previousStats.download_kb || 0)

  const todayDelta =
    currentStats.today_used - (previousStats.today_used || 0)

  const sessionDelta =
    currentStats.session_used - (previousStats.session_used || 0)

  if (uploadDelta > 0)
    persistentDeltas.upload = uploadDelta

  if (downloadDelta > 0)
    persistentDeltas.download = downloadDelta

  if (todayDelta > 0)
    persistentDeltas.today = todayDelta

  if (sessionDelta > 0)
    persistentDeltas.session = sessionDelta

  previousStats = currentStats

  $("upload").innerHTML =
    `${fmt(currentStats.upload_kb)}<span class="text-gray-400 text-xs">${formatDelta(persistentDeltas.upload)}</span>`

  $("download").innerHTML =
    `${fmt(currentStats.download_kb)}<span class="text-gray-400 text-xs">${formatDelta(persistentDeltas.download)}</span>`

  $("today").innerHTML =
    `${currentStats.today_used} / ~${st.quota_total || 0}
    <span class="text-gray-400 text-xs">
      ${formatDelta(persistentDeltas.today, false)}
    </span>`
  
  const quotaTotal = st.quota_total || 0

  if (sessionPercentageMode) {

    const currentPercent =
      formatPercentage(st.session_used || 0, quotaTotal)

    const deltaPercent =
      quotaTotal > 0
        ? ((persistentDeltas.session / quotaTotal) * 100).toFixed(2)
        : 0

    $("session").innerHTML =
      `${currentPercent}
      <span class="text-gray-400 text-xs">
        (+${deltaPercent}%)
      </span>`

  } else {

    $("session").innerHTML =
      `${st.session_used || 0} / ~${quotaTotal}
      <span class="text-gray-400 text-xs">
        ${formatDelta(persistentDeltas.session, false)}
      </span>`
  }
  
  $("active").innerText = st.active ?? 0
  $("sessions").innerText = currentStats.sessions


  const upload = st.upload_kb || 0
  const download = st.download_kb || 0
  const session = st.session_used || 0
  const today = st.today_used || 0

  const graphChanged =
    upload !== lastGraphValues.upload ||
    download !== lastGraphValues.download ||
    session !== lastGraphValues.session ||
    today !== lastGraphValues.today

  if (graphChanged) {
    lastGraphValues = { upload, download, session, today }

    pushData(data.labels, "")
    pushData(data.u, upload)
    pushData(data.d, download)
    pushData(data.s, session)
    pushData(data.t, today)

    chart.update()
  }

  const l = await (await api("/logs")).json()
  $("logs").innerHTML = l.logs.map(x => `
    <div class="py-1 border-b border-white/5 break-all">
      ${x}
    </div>
  `).join("")

  $("versionText").innerText = `Gooseman ${s.version}`
}

async function updateCheck() {
  const btn = $("checkUpdateBtn")

  btn.disabled = true
  const original = btn.innerText
  btn.innerText = "Checking..."

  try {
    const r = await api("/check-updates", { method: "POST" })
    const d = await r.json()

    if (d.update_available) {
      $("updateBtn").classList.remove("hidden")
      $("updateBtn").innerText = `Update → ${d.latest_version}`

      showToast(`Update available: ${d.latest_version}`, "success")
    } else {
      showToast("Gooseman is already up to date", "success")
    }

  } catch (e) {
    showToast("Failed to check for updates", "error")
  } finally {
    btn.disabled = false
    btn.innerText = original
  }
}

function init() {
  chart = new Chart($("chart"), {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        { label: "Upload KB", data: data.u, borderColor: "#22c55e", tension: .35 },
        { label: "Download KB", data: data.d, borderColor: "#3b82f6", tension: .35 },
        { label: "Session Quota", data: data.s, borderColor: "#f59e0b", tension: .35 },
        { label: "Today's Quota", data: data.t, borderColor: "#ef4444", tension: .35 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false
    }
  })
}

function showToast(message, type = "success", duration = 2500) {
  const container = $("toastContainer")

  const toast = document.createElement("div")
  toast.className = `toast ${type}`

  const closeBtn = document.createElement("button")
  closeBtn.innerText = "✕"

  closeBtn.onclick = () => toast.remove()

  const text = document.createElement("div")
  text.style.flex = "1"
  text.innerText = message

  toast.appendChild(text)
  toast.appendChild(closeBtn)

  container.appendChild(toast)

  requestAnimationFrame(() => toast.classList.add("show"))

  setTimeout(() => {
    toast.classList.add("hide")
    setTimeout(() => toast.remove(), 250)
  }, duration)
}

setInterval(async () => {
  if (!authToken) return
  try { await update() } catch {}
}, 3000)

setInterval(() => {
  const el = $("lastUpdateAgo")
  if (!el) return

  const secs = Math.floor((Date.now() - lastMeaningfulUpdate) / 1000)

  if (secs < 10) el.innerText = " (just now)"
  else if (secs < 60) el.innerText = ` (${secs}s ago)`
  else el.innerText = ` (${Math.floor(secs / 60)}m ago)`
}, 1000)

init()
$("loginOverlay").style.display = "flex"