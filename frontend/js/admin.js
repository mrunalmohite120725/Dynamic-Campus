/**
 * admin.js — Admin Dashboard Logic
 */

let classroomTimer = null;
let selectedPDF = null;

async function initDashboard(identity) {
  const name = identity.username || "Admin";
  document.getElementById("sidebar-name").textContent = name;
  document.getElementById("sidebar-avatar").textContent = name[0].toUpperCase();

  updateAdminClock();
  setInterval(updateAdminClock, 1000);

  await Promise.all([
    loadAdminClassrooms(),
    loadExtraRequests(),
    loadClassesForUpload(),
    loadTeachersForUser(),
  ]);

  classroomTimer = setInterval(loadAdminClassrooms, 60_000);
  initAdminSocket();
}

function updateAdminClock() {
  const now = new Date();
  document.getElementById("dash-clock").textContent =
    now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  document.getElementById("dash-day-date").textContent =
    `${days[now.getDay()]}, ${now.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}`;
}

// ── Classroom Monitor ──────────────────────────────────────────────────────
async function loadAdminClassrooms() {
  const grid = document.getElementById("admin-classroom-grid");
  try {
    const res = await fetch(`${API}/api/classrooms`);
    const data = await res.json();

    const total = data.length;
    const occupied = data.filter(c => c.status === "occupied").length;
    const free = total - occupied;
    const pct = total ? Math.round((occupied / total) * 100) : 0;

    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-free").textContent = free;
    document.getElementById("stat-occupied").textContent = occupied;
    document.getElementById("occupancy-pct").textContent = `${pct}%`;

    const bar = document.getElementById("occ-bar-fill");
    bar.style.width = `${pct}%`;
    bar.className = `occ-bar-fill${pct >= 80 ? " full" : pct >= 50 ? " high" : ""}`;

    // Sort: occupied first
    data.sort((a, b) => {
      if (a.status !== b.status) return a.status === "occupied" ? -1 : 1;
      return a.room.localeCompare(b.room);
    });

    grid.innerHTML = "";
    data.forEach(c => {
      const card = document.createElement("div");
      card.className = `classroom-card ${c.status}`;
      card.id = `admin-room-${c.room.replace(/[^a-z0-9]/gi, "-")}`;

      if (c.status === "occupied") {
        card.innerHTML = `
          <div class="cc-room">${c.room}</div>
          <div class="cc-status"><span class="cc-status-dot"></span> Occupied</div>
          <div class="cc-detail">
            <div class="cc-subject">${c.subject || "—"}</div>
            <div>${c.teacher || "—"}</div>
            <div class="cc-class">${c.class || "—"}</div>
            <div class="cc-time">${c.start_time || ""} – ${c.end_time || ""}</div>
          </div>`;
      } else {
        card.innerHTML = `
          <div class="cc-room">${c.room}</div>
          <div class="cc-status"><span class="cc-status-dot"></span> Free</div>
          <div class="cc-detail" style="color:var(--text-muted);font-size:12px">Available now</div>`;
      }
      grid.appendChild(card);
    });

    if (!data.length) {
      grid.innerHTML = `<div class="loading-placeholder">No classroom data. Upload a timetable first.</div>`;
    }

  } catch (e) {
    grid.innerHTML = `<div class="loading-placeholder">Cannot connect to server.</div>`;
  }
}

// ── Upload ─────────────────────────────────────────────────────────────────
async function loadClassesForUpload() {
  try {
    const res = await fetch(`${API}/api/classes`);
    const data = await res.json();
    const sel = document.getElementById("upload-cid");
    sel.innerHTML = "";
    data.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.cid;
      opt.textContent = `${c.class_name} ${c.class_room_no} (Sem ${c.sem})`;
      sel.appendChild(opt);
    });
    if (!data.length) {
      const opt = document.createElement("option");
      opt.value = 1; opt.textContent = "Default (cid=1)";
      sel.appendChild(opt);
    }
  } catch (e) { console.error("load classes error:", e); }
}

function onDragOver(e) { e.preventDefault(); document.getElementById("upload-zone").classList.add("drag-over"); }
function onDragLeave(e) { document.getElementById("upload-zone").classList.remove("drag-over"); }
function onDrop(e) {
  e.preventDefault();
  document.getElementById("upload-zone").classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file && file.type === "application/pdf") setFile(file);
  else alert("Please drop a PDF file.");
}
function onFileSelect(e) {
  const file = e.target.files[0];
  if (file) setFile(file);
}
function setFile(file) {
  selectedPDF = file;
  document.getElementById("upload-filename").textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  document.getElementById("upload-btn").disabled = false;
}

async function uploadPDF() {
  if (!selectedPDF) return;

  const btn = document.getElementById("upload-btn");
  const progWrap = document.getElementById("progress-wrap");
  const progBar = document.getElementById("progress-bar");
  const result = document.getElementById("upload-result");

  btn.disabled = true;
  btn.textContent = "Processing…";
  progWrap.style.display = "block";
  result.style.display = "none";

  // Animate bar to 30% while waiting for AI
  progBar.style.width = "30%";

  const formData = new FormData();
  formData.append("file", selectedPDF);
  formData.append("cid", document.getElementById("upload-cid").value);
  formData.append("sem", document.getElementById("upload-sem").value);
  formData.append("year", document.getElementById("upload-year").value);

  try {
    const token = getToken();
    progBar.style.width = "60%";

    const res = await fetch(`${API}/api/upload`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData,
    });
    const data = await res.json();

    progBar.style.width = "100%";
    setTimeout(() => { progWrap.style.display = "none"; progBar.style.width = "0%"; }, 800);

    result.className = `upload-result-box ${res.ok ? "success" : "error"}`;
    result.textContent = res.ok
      ? `✓ ${data.message || "Timetable processed successfully!"}`
      : `✗ Error: ${data.error || data.msg || "Unauthorized"}`;
    result.style.display = "block";

    if (res.ok) loadAdminClassrooms();

  } catch (e) {
    progBar.style.width = "100%";
    result.className = "upload-result-box error";
    result.textContent = "✗ Cannot connect to server. Is Flask running?";
    result.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload & Process →";
  }
}

// ── Extra Lecture Requests ─────────────────────────────────────────────────
async function loadExtraRequests() {
  const queue = document.getElementById("extra-queue");
  const badge = document.getElementById("extra-badge");
  try {
    const res = await authFetch(`${API}/api/extra-lectures`);
    if (!res.ok) { queue.innerHTML = `<div class="loading-cell">No pending requests.</div>`; return; }
    const data = await res.json();

    const pending = data.filter(r => r.status === "pending");
    if (pending.length > 0) {
      badge.textContent = pending.length;
      badge.style.display = "block";
    } else {
      badge.style.display = "none";
    }

    if (!data.length) {
      queue.innerHTML = `<div class="loading-cell">No extra lecture requests yet.</div>`;
      return;
    }

    queue.innerHTML = "";
    data.forEach(r => {
      const item = document.createElement("div");
      item.className = "queue-item";
      item.innerHTML = `
        <div>
          <div class="queue-detail">${r.sname || "—"} · ${r.day} ${r.start_time}–${r.end_time}</div>
          <div class="queue-meta">
            Teacher: ${r.tname || "—"} · Class: ${r.class_name || r.cid} · Room: ${r.room || "TBD"}
            ${r.reason ? ` · Reason: ${r.reason}` : ""}
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:12px">
          <span class="card-tag tag-${r.status}">${r.status}</span>
          ${r.status === "pending" ? `
            <button class="btn-approve" onclick="decideExtra(${r.eid},'approve')">Approve</button>
            <button class="btn-reject"  onclick="decideExtra(${r.eid},'reject')">Reject</button>
          ` : ""}
        </div>`;
      queue.appendChild(item);
    });

  } catch (e) {
    queue.innerHTML = `<div class="loading-cell">Cannot load requests.</div>`;
  }
}

async function decideExtra(eid, action) {
  try {
    const res = await authFetch(`${API}/api/extra-lecture/${eid}/${action}`, { method: "PUT" });
    if (res.ok) { loadExtraRequests(); showToastAdmin(`Request ${action}d successfully.`, action === "approve" ? "extra" : "warning"); }
    else showToastAdmin("Action failed.", "warning");
  } catch (e) { showToastAdmin("Cannot connect.", "warning"); }
}

// ── Notifications ──────────────────────────────────────────────────────────
async function sendNotification() {
  const message = document.getElementById("notif-message").value.trim();
  const sem = document.getElementById("notif-sem").value || null;
  const type = document.getElementById("notif-type").value;
  const result = document.getElementById("notif-result");

  if (!message) { alert("Please enter a message."); return; }

  try {
    const res = await authFetch(`${API}/api/notifications`, {
      method: "POST",
      body: JSON.stringify({ message, target_sem: sem ? parseInt(sem) : null, type }),
    });
    const data = await res.json();
    result.className = "notif-success";
    result.textContent = res.ok ? "✓ Notification sent to students!" : `✗ ${data.error}`;
    result.style.display = "block";
    if (res.ok) document.getElementById("notif-message").value = "";
  } catch (e) {
    result.className = "notif-success"; // reuse styles
    result.style.background = "var(--red-bg)";
    result.textContent = "✗ Cannot connect to server.";
    result.style.display = "block";
  }
}

// ── User Management ────────────────────────────────────────────────────────
async function loadTeachersForUser() {
  // No-op: teachers self-register via Teacher Portal → Register tab
}

function toggleTidField() {
  // No-op: only admin accounts created from this panel
}

async function createUser() {
  const username = document.getElementById("new-username").value.trim();
  const password = document.getElementById("new-password").value.trim();
  const result   = document.getElementById("user-result");

  if (!username || !password) { alert("Username and password are required."); return; }

  try {
    const res  = await authFetch(`${API}/api/admin/users`, {
      method: "POST",
      body:   JSON.stringify({ username, password }),
    });
    const data = await res.json();
    result.className   = `upload-result-box ${res.ok ? "success" : "error"}`;
    result.textContent = res.ok
      ? `✓ Admin account '${username}' created.`
      : `✗ ${data.error || data.msg}`;
    result.style.display = "block";
    if (res.ok) {
      document.getElementById("new-username").value = "";
      document.getElementById("new-password").value = "";
    }
  } catch (e) {
    result.className   = "upload-result-box error";
    result.textContent = "✗ Cannot connect.";
    result.style.display = "block";
  }
}

// ── Section Switching ──────────────────────────────────────────────────────
function showSection(name, el) {
  ["monitor", "upload", "extra", "notify", "users", "absences"].forEach(s => {
    const sec = document.getElementById(`section-${s}`);
    if (sec) sec.style.display = "none";
  });
  document.getElementById(`section-${name}`).style.display = "block";
  document.getElementById("dash-section-title").textContent = {
        monitor: "Live Monitor", upload: "Upload Timetable",
        extra: "Extra Lectures", absences: "Absences",
        notify: "Notifications", users: "Manage Users"
      }[name];
 
   document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
   if (el) el.classList.add("active");

   if (name === "absences") loadAbsenceReports();
}

// ── WebSocket ──────────────────────────────────────────────────────────────
function initAdminSocket() {
  try {
    const socket = io(API);
    socket.on("connect", () => { socket.emit("subscribe", { room: "classrooms" }); });
    socket.on("classroom_update", () => loadAdminClassrooms());
    socket.on("timetable_updated", () => { loadAdminClassrooms(); loadExtraRequests(); });
    socket.on("absence_reported", (data) => {
      showToastAdmin(data.message, "warning");
      const badge = document.getElementById("absence-badge");
      badge.textContent = parseInt(badge.textContent || "0") + 1;
      badge.style.display = "block";
      loadAbsenceReports();
    });
  } catch (e) { console.warn("WebSocket unavailable."); }
}

// ── Absence & AI Suggestion Logic ──────────────────────────────────────────
async function loadAbsenceReports() {
  const list = document.getElementById("absence-list");
  const badge = document.getElementById("absence-badge");
  try {
    // We query notifications with ?admin=1 to see both public and admin-only alerts
    const res = await authFetch(`${API}/api/notifications?admin=1`);
    const data = await res.json();
    
    // Filter for absence alerts (type cancel)
    // Note: in a real app, you might have a dedicated table for absences
    const alerts = data.filter(n => n.type === "cancel");
    
    if (alerts.length > 0) {
      badge.textContent = alerts.length;
      badge.style.display = "block";
    } else {
      badge.style.display = "none";
    }

    if (!alerts.length) {
      list.innerHTML = `<div class="loading-cell">No absence reports today.</div>`;
      return;
    }

    list.innerHTML = "";
    alerts.forEach(n => {
      const item = document.createElement("div");
      item.className = "queue-item";
      // We parse the message or use the metadata if we had it.
      // For this demo, we'll assume the message has the info or we store it in a hidden data attribute
      item.innerHTML = `
        <div style="flex:1">
          <div class="queue-detail">${n.message}</div>
          <div class="queue-meta">${n.created_at}</div>
        </div>
        <div>
          <button class="btn btn-primary btn-sm" onclick='triggerAISuggestion("${encodeURIComponent(JSON.stringify(n))}")'>
            ✨ Find AI Substitute
          </button>
        </div>
      `;
      list.appendChild(item);
    });
  } catch (e) { console.error("load absences error:", e); }
}

async function triggerAISuggestion(encodedData) {
  const notif = JSON.parse(decodeURIComponent(encodedData));
  
  // Parse metadata (contains real sid, day, start, end)
  let meta = {};
  try {
    meta = typeof notif.metadata === 'string' ? JSON.parse(notif.metadata) : (notif.metadata || {});
  } catch(e) { console.warn("Metadata parse error", e); }

  const sid   = meta.sid   || 1;
  const day   = meta.day   || new Date().toLocaleDateString("en-US", { weekday: "long" });
  const start = meta.start || "09:00";
  const end   = meta.end   || "10:00";
  const sname = meta.sname || "Subject";

  document.getElementById("ai-modal").style.display = "flex";
  document.getElementById("ai-context").innerHTML = `Finding best match for <strong>${sname}</strong> on ${day} (${start}-${end})...`;
  
  const resultsList = document.getElementById("ai-results-list");
  resultsList.innerHTML = '<div class="loading-cell">AI is calculating vectors...</div>';

  try {
    // Call AI Suggester with real parameters
    const res = await authFetch(`${API}/api/ai/substitute-suggestions?sid=${sid}&day=${day}&start_time=${start}&end_time=${end}`);
    const suggestions = await res.json();
    
    if (suggestions.error) throw new Error(suggestions.error);

    resultsList.innerHTML = "";
    if (suggestions.length === 0) {
      resultsList.innerHTML = '<div class="loading-cell">No available teachers found.</div>';
      return;
    }

    suggestions.forEach(s => {
      const div = document.createElement("div");
      div.className = "ai-suggestion-item";
      div.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:12px;border-bottom:1px solid var(--border);";
      
      // Use single quotes for the onclick to avoid JSON.stringify issues
      div.innerHTML = `
        <div>
          <div style="font-weight:700;font-size:15px">${s.tname}</div>
          <div style="font-size:12px;color:var(--text-secondary)">
            Match Score: <span style="color:var(--accent);font-weight:700">${(s.score * 100).toFixed(1)}%</span> · ${s.reason}
          </div>
        </div>
        <button class="btn btn-primary btn-sm" onclick='assignSub(${s.tid}, "${s.tname}", ${JSON.stringify(meta)})'>Assign</button>
      `;
      resultsList.appendChild(div);
    });

  } catch (err) {
    resultsList.innerHTML = `<div class="loading-cell" style="color:var(--red)">AI Error: ${err.message}</div>`;
  }
}

function closeAIModal() {
  document.getElementById("ai-modal").style.display = "none";
}

async function assignSub(tid, tname, slotData) {
  if (!confirm(`Assign ${tname} as the substitute?`)) return;
  
  try {
    const res = await authFetch(`${API}/api/extra-lecture/request`, {
      method: "POST",
      body: JSON.stringify({
        tid: tid,
        sid: slotData.sid,
        cid: slotData.cid || 1,
        day: slotData.day,
        start_time: slotData.start,
        end_time: slotData.end,
        room: "TBD", // Admin can update this later
        reason: `AI Substitute for ${slotData.sname}`,
        status: 'approved' // Auto-approve for Admin
      })
    });

    if (res.ok) {
      showToastAdmin(`✓ ${tname} has been assigned as substitute.`, "extra");
      closeAIModal();
      loadAbsenceReports();
      // Optionally notify via socket so teacher dashboard refreshes
    } else {
      const err = await res.json();
      alert("Error: " + (err.error || "Assignment failed"));
    }
  } catch (e) {
    console.error(e);
    alert("Network error during assignment.");
  }
}

// ── Toast ──────────────────────────────────────────────────────────────────
function showToastAdmin(message, type = "info") {
  const colors = { info: "#6366f1", warning: "#f59e0b", extra: "#22c55e" };
  const col = colors[type] || colors.info;
  const toast = document.createElement("div");
  toast.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${col}22;border:1px solid ${col}55;color:#fff;
    padding:14px 20px;border-radius:12px;font-size:14px;font-weight:500;
    max-width:360px;backdrop-filter:blur(12px);font-family:'Inter',sans-serif;`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}
