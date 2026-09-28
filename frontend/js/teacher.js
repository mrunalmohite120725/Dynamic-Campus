/**
 * teacher.js — Teacher Dashboard Logic
 */

const DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday"];
let teacherTid  = null;
let refreshTimer = null;

// ── Auth Tab Switching ─────────────────────────────────────────────────────
function switchAuthTab(tab) {
  const loginForm    = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const loginBtn     = document.getElementById("tab-login-btn");
  const regBtn       = document.getElementById("tab-register-btn");

  loginForm.style.display    = tab === "login"    ? "" : "none";
  registerForm.style.display = tab === "register" ? "" : "none";
  loginBtn.classList.toggle("active", tab === "login");
  regBtn.classList.toggle("active",   tab === "register");

  if (tab === "register") loadTeachersForRegister();

  // Clear error messages
  document.getElementById("login-error").style.display    = "none";
  document.getElementById("register-error").style.display = "none";
}

async function loadTeachersForRegister() {
  try {
    const res  = await fetch(`${API}/api/teachers`);
    const data = await res.json();
    const sel  = document.getElementById("reg-tid");
    sel.innerHTML = '<option value="">— Select your name —</option>';
    data.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.tid;
      opt.textContent = t.tname;
      sel.appendChild(opt);
    });
  } catch (e) { console.error("teachers for register error:", e); }
}

async function handleRegister(e) {
  e.preventDefault();
  const username = document.getElementById("reg-username").value.trim();
  const password = document.getElementById("reg-password").value.trim();
  const tid      = document.getElementById("reg-tid").value || null;
  const errEl    = document.getElementById("register-error");
  const btn      = document.getElementById("reg-btn");

  errEl.style.display = "none";
  btn.disabled = true;
  btn.textContent = "Creating…";

  try {
    const res  = await fetch(`${API}/api/register`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ username, password, tid: tid ? parseInt(tid) : null }),
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent  = data.error || "Registration failed.";
      errEl.style.display = "block";
    } else {
      // Switch to login tab and pre-fill username
      switchAuthTab("login");
      document.getElementById("username").value = username;
      const loginErr = document.getElementById("login-error");
      loginErr.style.cssText = "display:block;color:#22c55e;background:rgba(34,197,94,0.1);border-color:rgba(34,197,94,0.3)";
      loginErr.textContent = "✓ Account created! Please sign in.";
    }
  } catch (err) {
    errEl.textContent  = "Cannot reach server. Is Flask running?";
    errEl.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Create Account →";
  }
}

// ── Dashboard Init ─────────────────────────────────────────────────────────
// Called by auth.js after login / session restore
async function initDashboard(identity) {
  teacherTid = identity.tid;

  // Update sidebar
  const name = identity.username || "Teacher";
  document.getElementById("sidebar-name").textContent    = name;
  document.getElementById("sidebar-avatar").textContent  = name[0].toUpperCase();

  // Date + clock
  updateDashClock();
  setInterval(updateDashClock, 1000);

  // Load data
  await Promise.all([
    loadNowNext(),
    loadTodayTimeline(),
    loadClassrooms(),
    loadSubjectsForExtra(),
    loadClassesForExtra(),
  ]);

  // Auto-refresh now/next every 60s
  clearInterval(refreshTimer);
  refreshTimer = setInterval(loadNowNext, 60_000);
  
  // Auto-refresh classrooms every 2 mins
  setInterval(loadClassrooms, 120_000);
}

function updateDashClock() {
  const now  = new Date();
  document.getElementById("dash-clock").textContent =
    now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  const days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  document.getElementById("dash-day-date").textContent =
    `${days[now.getDay()]}, ${now.toLocaleDateString("en-IN", { day:"numeric", month:"long", year:"numeric" })}`;
}

// ── Now / Next ─────────────────────────────────────────────────────────────
async function loadNowNext() {
  try {
    const [nowRes, nextRes] = await Promise.all([
      authFetch(`${API}/api/timetable/teacher/now?tid=${teacherTid}`),
      authFetch(`${API}/api/timetable/teacher/next?tid=${teacherTid}`),
    ]);
    const nowData  = await nowRes.json();
    const nextData = await nextRes.json();

    const badge = document.getElementById("teacher-status-badge");
    const statusText = document.getElementById("teacher-status-text");

    if (nowData && nowData.sname) {
      document.getElementById("now-subject").textContent = nowData.sname;
      document.getElementById("now-time").textContent    = `${nowData.start_time} – ${nowData.end_time}`;
      setChipLabel("now-class", nowData.class_name || "—");
      setChipLabel("now-room",  nowData.room        || "—");
      badge.className    = "status-badge in-lecture";
      statusText.textContent = "In Lecture";
    } else {
      document.getElementById("now-subject").textContent = "No lecture now";
      document.getElementById("now-time").textContent    = "—";
      setChipLabel("now-class", "—");
      setChipLabel("now-room",  "—");
      badge.className    = "status-badge available";
      statusText.textContent = "Available";
    }

    if (nextData && nextData.sname) {
      document.getElementById("next-subject").textContent = nextData.sname;
      document.getElementById("next-time").textContent    = `${nextData.start_time} – ${nextData.end_time}`;
      setChipLabel("next-class", nextData.class_name || "—");
      setChipLabel("next-room",  nextData.room        || "—");
    } else {
      document.getElementById("next-subject").textContent = "No more lectures today";
      document.getElementById("next-time").textContent    = "—";
    }
  } catch (e) { console.error("now/next error:", e); }
}

function setChipLabel(id, text) {
  const el  = document.getElementById(id);
  const svg = el.querySelector("svg");
  el.textContent = " " + text;
  if (svg) el.prepend(svg);
}

// ── Today's Timeline ───────────────────────────────────────────────────────
async function loadTodayTimeline() {
  const container = document.getElementById("today-timeline");
  const today = new Date().toLocaleDateString("en-US", { weekday: "long" });
  const nowMins = new Date().getHours() * 60 + new Date().getMinutes();

  try {
    const res  = await authFetch(`${API}/api/timetable/teacher?tid=${teacherTid}`);
    const rows = await res.json();

    const todayRows = rows.filter(r => r.day === today);
    if (!todayRows.length) {
      container.innerHTML = `<div class="loading-cell">No lectures today (${today}).</div>`;
      return;
    }

    container.innerHTML = "";
    todayRows.forEach((r, idx) => {
      const [sh, sm] = r.start_time.split(":").map(Number);
      const [eh, em] = r.end_time.split(":").map(Number);
      const startMins = sh * 60 + sm;
      const endMins   = eh * 60 + em;
      const isCurrent = nowMins >= startMins && nowMins < endMins;
      const isPast    = nowMins >= endMins;

      const div = document.createElement("div");
      div.className = `timeline-item${isCurrent ? " is-current" : ""}${isPast ? " is-past" : ""}`;
      div.innerHTML = `
        <div class="tl-time">${r.start_time}<br/><small>${r.end_time}</small></div>
        <div class="tl-dot-col">
          <div class="tl-dot"></div>
          ${idx < todayRows.length - 1 ? '<div class="tl-line"></div>' : ''}
        </div>
        <div class="tl-content">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <div class="tl-subject">${r.sname}</div>
              <div class="tl-meta">
                <span>${r.class_name || "—"}</span>
                ${r.room   ? `<span>📍 ${r.room}</span>`  : ""}
                ${r.batch  ? `<span>Batch ${r.batch}</span>` : ""}
                ${r.is_extra ? `<span class="extra-badge">EXTRA</span>` : ""}
                ${isCurrent ? `<span style="color:var(--accent-light);font-weight:700">● In Progress</span>` : ""}
              </div>
            </div>
            ${!isPast ? `
              <button class="btn btn-ghost btn-sm" style="color:var(--red);border-color:rgba(239,68,68,0.2)" 
                onclick='markAbsent(${JSON.stringify(r)})'>
                Mark Absent
              </button>` : ''}
          </div>
        </div>`;
      container.appendChild(div);
    });

  } catch (e) {
    console.error("timeline error:", e);
    container.innerHTML = `<div class="loading-cell">Failed to load schedule.</div>`;
  }
}

// ── Live Classrooms ────────────────────────────────────────────────────────

function parseRoom(room) {
  const m = (room||"").match(/^([A-Za-z]\d+)-(\d)(\d+)$/);
  if (m) return { building: m[1].toUpperCase(), floor: m[2] };
  return { building:"Other", floor:"0" };
}

async function loadClassrooms() {
  const grid = document.getElementById("classroom-grid");
  if (!grid) return;
  try {
    const res = await fetch(`${API}/api/classrooms`);
    const data = await res.json();
    if (!data.length) {
      grid.innerHTML = `<div class="loading-placeholder">No classroom data available.</div>`;
      return;
    }

    const buildings = {};
    data.forEach(c => {
      const { building, floor } = parseRoom(c.room);
      if (!buildings[building]) buildings[building] = {};
      if (!buildings[building][floor]) buildings[building][floor] = [];
      buildings[building][floor].push(c);
    });

    grid.innerHTML = "";
    Object.keys(buildings).sort().forEach(bName => {
      const floors = buildings[bName];
      const allRooms = Object.values(floors).flat();
      const occCount = allRooms.filter(r => r.status === "occupied").length;
      const freeCount = allRooms.length - occCount;

      const section = document.createElement("div");
      section.className = "building-section";
      section.innerHTML = `
        <div class="building-header">
          <div class="building-badge">${bName}</div>
          <div class="building-info">
            <span class="building-name">Building ${bName}</span>
            <span class="building-counts">
              <span class="bc-free">${freeCount} Free</span>
              <span class="bc-sep">·</span>
              <span class="bc-occupied">${occCount} Occupied</span>
            </span>
          </div>
        </div>`;

      const floorContainer = document.createElement("div");
      floorContainer.className = "floor-container";

      Object.keys(floors).sort().forEach(fNum => {
        const rooms = floors[fNum].sort((a,b) => a.room.localeCompare(b.room));
        const floorBlock = document.createElement("div");
        floorBlock.className = "floor-block";
        floorBlock.innerHTML = `<div class="floor-label"><span class="floor-icon">F${fNum}</span> Floor ${fNum}</div>`;
        
        const cardRow = document.createElement("div");
        cardRow.className = "floor-cards";

        rooms.forEach(c => {
          const card = document.createElement("div");
          card.className = `classroom-card ${c.status}`;
          if (c.status === "occupied") {
            card.innerHTML = `
              <div class="cc-room">${c.room}</div>
              <div class="cc-status"><span class="cc-status-dot"></span>Occupied</div>
              <div class="cc-detail">
                <div class="cc-subject">${c.subject||"—"}</div>
                <div class="cc-teacher">${c.teacher||"—"}</div>
                <div class="cc-class">${c.class||""}</div>
                <div class="cc-time">${c.start_time||""}–${c.end_time||""}</div>
              </div>`;
          } else {
            card.innerHTML = `
              <div class="cc-room">${c.room}</div>
              <div class="cc-status"><span class="cc-status-dot"></span>Free</div>
              <div class="cc-detail" style="color:var(--text-muted);font-size:11px;margin-top:4px">Available now</div>`;
          }
          cardRow.appendChild(card);
        });
        floorBlock.appendChild(cardRow);
        floorContainer.appendChild(floorBlock);
      });
      section.appendChild(floorContainer);
      grid.appendChild(section);
    });
  } catch (e) {
    grid.innerHTML = `<div class="loading-placeholder">Could not connect to server.</div>`;
  }
}


// ── Weekly Schedule ────────────────────────────────────────────────────────
async function loadWeeklySchedule() {
  const tbody = document.getElementById("teacher-week-body");
  tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">Loading…</td></tr>`;

  try {
    const res  = await authFetch(`${API}/api/timetable/teacher?tid=${teacherTid}`);
    const rows = await res.json();

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">No schedule data.</td></tr>`;
      return;
    }

    const slots = {};
    rows.forEach(r => {
      const key = `${r.start_time}–${r.end_time}`;
      if (!slots[key]) slots[key] = {};
      if (!slots[key][r.day]) slots[key][r.day] = [];
      slots[key][r.day].push(r);
    });

    const now = new Date();
    const nowMins = now.getHours() * 60 + now.getMinutes();
    const todayName = now.toLocaleDateString("en-US", { weekday: "long" });

    tbody.innerHTML = "";
    Object.keys(slots).sort().forEach(timeKey => {
      const [start, end] = timeKey.split("–");
      const [sh, sm] = start.split(":").map(Number);
      const [eh, em] = end.split(":").map(Number);
      const isCurrent = nowMins >= sh*60+sm && nowMins < eh*60+em;

      const tr = document.createElement("tr");
      if (isCurrent) tr.classList.add("current-row");
      tr.innerHTML = `<td class="time-col">${start}<br/><small>${end}</small></td>`;

      DAYS.forEach(day => {
        const cells = slots[timeKey][day] || [];
        if (!cells.length) { tr.innerHTML += `<td style="color:var(--text-muted)">—</td>`; return; }
        let html = "";
        cells.forEach(c => {
          html += `<div>`;
          if (c.batch) html += `<span class="cell-batch">${c.batch}</span><br/>`;
          html += `<span class="cell-subject">${c.sname}</span><br/>`;
          html += `<span class="cell-teacher">${c.class_name || ""}</span>`;
          if (c.room) html += ` · ${c.room}`;
          if (c.is_extra) html += ` <span class="extra-badge">EXTRA</span>`;
          html += `</div>`;
        });
        tr.innerHTML += `<td>${html}</td>`;
      });
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">Failed to load.</td></tr>`;
  }
}

// ── Extra Lecture Form ─────────────────────────────────────────────────────
async function loadSubjectsForExtra() {
  try {
    // Use the public /api/subjects endpoint (no auth needed)
    const res  = await fetch(`${API}/api/subjects`);
    const data = await res.json();
    const sel  = document.getElementById("extra-subject");
    sel.innerHTML = '<option value="">— Select Subject —</option>';
    data.forEach(s => {
      const opt = document.createElement("option");
      opt.value       = s.sid;   // store sid as value
      opt.textContent = s.sname;
      sel.appendChild(opt);
    });
    if (!data.length) {
      const opt = document.createElement("option");
      opt.disabled = true;
      opt.textContent = "No subjects yet — upload a timetable first";
      sel.appendChild(opt);
    }
  } catch (e) { console.error("subjects error:", e); }
}

async function loadClassesForExtra() {
  try {
    const res  = await fetch(`${API}/api/classes`);
    const data = await res.json();
    const sel  = document.getElementById("extra-class");
    const nSel = document.getElementById("notif-class");
    sel.innerHTML = '<option value="">— Select Class —</option>';
    if (nSel) nSel.innerHTML = '<option value="">— Entire College —</option>';
    data.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.cid;
      opt.textContent = `${c.class_name} ${c.class_room_no} (Sem ${c.sem})`;
      sel.appendChild(opt);
      if (nSel) nSel.appendChild(opt.cloneNode(true));
    });
  } catch (e) { console.error("classes error:", e); }
}

document.getElementById("extra-class").addEventListener("change", async (e) => {
  const cid = e.target.value;
  const batchSel = document.getElementById("extra-batch");
  batchSel.innerHTML = '<option value="">Entire Class</option>';
  batchSel.disabled = true;
  
  if (!cid) return;
  
  try {
    const res = await fetch(`${API}/api/batches?cid=${cid}`);
    const batches = await res.json();
    batches.forEach(b => {
      const opt = document.createElement("option");
      opt.value = b;
      opt.textContent = `Batch ${b}`;
      batchSel.appendChild(opt);
    });
    if (batches.length > 0) batchSel.disabled = false;
  } catch (err) { console.error("batch error", err); }
});

document.getElementById("notif-class").addEventListener("change", async (e) => {
  const cid = e.target.value;
  const batchSel = document.getElementById("notif-batch");
  batchSel.innerHTML = '<option value="">— Entire Class —</option>';
  batchSel.disabled = true;
  if (!cid) return;
  try {
    const res = await fetch(`${API}/api/batches?cid=${cid}`);
    const batches = await res.json();
    batches.forEach(b => {
      const opt = document.createElement("option");
      opt.value = b; opt.textContent = `Batch ${b}`;
      batchSel.appendChild(opt);
    });
    if (batches.length > 0) batchSel.disabled = false;
  } catch (err) { console.error("notif batch error", err); }
});

async function submitExtraLecture(e) {
  e.preventDefault();
  const resultEl = document.getElementById("extra-result");
  resultEl.style.display = "none";

  const sid        = document.getElementById("extra-subject").value;
  const cid        = document.getElementById("extra-class").value;
  const batch      = document.getElementById("extra-batch").value;
  const day        = document.getElementById("extra-day").value;
  const start_time = document.getElementById("extra-start").value;
  const end_time   = document.getElementById("extra-end").value;
  const room       = document.getElementById("extra-room").value;
  const reason     = document.getElementById("extra-reason").value;

  if (!sid || !cid || !day || !start_time || !end_time) {
    resultEl.className   = "upload-result-box error";
    resultEl.textContent = "✗ Please fill in all required fields.";
    resultEl.style.display = "block";
    return;
  }

  try {
    const res  = await authFetch(`${API}/api/extra-lecture/request`, {
      method: "POST",
      body:   JSON.stringify({
        sid: parseInt(sid), cid: parseInt(cid), batch,
        day, start_time, end_time, room, reason,
      }),
    });
    const data = await res.json();

    if (res.ok) {
      resultEl.className   = "upload-result-box success";
      resultEl.textContent = "✓ Extra lecture successfully scheduled!";
      document.getElementById("extra-form").reset();
      loadSubjectsForExtra();  // re-populate dropdowns
      loadClassesForExtra();
    } else {
      resultEl.className   = "upload-result-box error";
      resultEl.textContent = `✗ ${data.error || data.msg || "Submission failed."}`;
    }
    resultEl.style.display = "block";
  } catch (err) {
    resultEl.className   = "upload-result-box error";
    resultEl.textContent = "✗ Cannot connect to server.";
    resultEl.style.display = "block";
  }
}

// ── Free Room Suggestions & Conflict Check ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const classSelect = document.getElementById("extra-class");
  const batchSelect = document.getElementById("extra-batch");
  const daySelect = document.getElementById("extra-day");
  const startInput = document.getElementById("extra-start");
  const endInput = document.getElementById("extra-end");

  const checkConflictsAndRooms = () => {
    const cid = classSelect.value;
    const batch = batchSelect.value;
    const day = daySelect.value;
    const start = startInput.value;
    const end = endInput.value;
    
    if (cid && day && start && end) {
      fetchFreeRooms(cid, batch, day, start, end);
    } else {
      document.getElementById("free-rooms-container").style.display = "none";
      document.getElementById("conflict-warning").style.display = "none";
    }
  };

  if(classSelect) classSelect.addEventListener('change', checkConflictsAndRooms);
  if(batchSelect) batchSelect.addEventListener('change', checkConflictsAndRooms);
  if(daySelect) daySelect.addEventListener('change', checkConflictsAndRooms);
  if(startInput) startInput.addEventListener('change', checkConflictsAndRooms);
  if(endInput) endInput.addEventListener('change', checkConflictsAndRooms);
});

async function fetchFreeRooms(cid, batch, day, start, end) {
  const container = document.getElementById("free-rooms-container");
  const list = document.getElementById("free-rooms-list");
  const warning = document.getElementById("conflict-warning");
  const submitBtn = document.querySelector("#extra-form button[type='submit']") || document.querySelector("#extra-form .btn-primary");
  
  container.style.display = "block";
  warning.style.display = "none";
  if (submitBtn) submitBtn.disabled = false;
  
  list.innerHTML = `<div style="font-size:13px;color:var(--text-muted)">Checking availability...</div>`;

  try {
    const token = getToken();
    const batchParam = batch ? `&batch=${encodeURIComponent(batch)}` : "";
    const res = await fetch(`${API}/api/extra-lecture/check?cid=${cid}&day=${day}&start_time=${start}&end_time=${end}${batchParam}`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "Error fetching status");

    if (data.class_busy) {
      warning.style.display = "block";
      container.style.display = "none";
      if (submitBtn) submitBtn.disabled = true;
      return;
    }

    const freeRooms = data.free_rooms || [];
    
    if (freeRooms.length === 0) {
      list.innerHTML = `<div style="font-size:13px;color:var(--red);">No completely free rooms found for this slot.</div>`;
      return;
    }

    list.innerHTML = "";
    freeRooms.sort().forEach(room => {
      const chip = document.createElement("div");
      chip.className = "meta-chip";
      chip.style.cssText = "cursor:pointer;background:rgba(34,197,94,0.1);color:#22c55e;border:1px solid rgba(34,197,94,0.3);padding:6px 12px;border-radius:20px;transition:all 0.2s;";
      chip.textContent = room;
      chip.title = "Click to select this room";
      
      // Hover effects
      chip.onmouseover = () => chip.style.background = "rgba(34,197,94,0.2)";
      chip.onmouseout = () => chip.style.background = "rgba(34,197,94,0.1)";
      
      // Click to select
      chip.onclick = () => {
        document.getElementById("extra-room").value = room;
        // Optional visual feedback
        const originalText = chip.textContent;
        chip.textContent = "✓ Selected";
        setTimeout(() => chip.textContent = originalText, 1000);
      };
      
      list.appendChild(chip);
    });

  } catch (err) {
    console.error(err);
    list.innerHTML = `<div style="font-size:13px;color:var(--red);">Failed to load free rooms.</div>`;
  }
}

// ── Notifications ──────────────────────────────────────────────────────────
async function loadNotifications() {
  const list = document.getElementById("notif-list");
  list.innerHTML = `<div class="loading-cell">Loading…</div>`;

  const TYPE_COLORS = {
    info:"#6366f1", warning:"#f59e0b", change:"#3b82f6",
    extra:"#22c55e", cancel:"#ef4444"
  };

  try {
    const res  = await fetch(`${API}/api/notifications`);
    const data = await res.json();

    if (!data.length) {
      list.innerHTML = `<div class="loading-cell">No notifications yet.</div>`;
      return;
    }

    list.innerHTML = "";
    data.forEach(n => {
      const col = TYPE_COLORS[n.type] || "#6366f1";
      const div = document.createElement("div");
      div.className = "notif-item";
      div.innerHTML = `
        <div class="notif-item-inner">
          <span class="notif-badge-type" style="background:${col}22;color:${col}">${n.type}</span>
          <div style="flex:1">
            <div class="notif-msg">${n.message}</div>
            <div class="notif-meta">
              ${n.created_at}
            </div>
          </div>
        </div>`;
      list.appendChild(div);
    });
  } catch (e) {
    list.innerHTML = `<div class="loading-cell">Failed to load notifications.</div>`;
  }
}

async function sendNotification() {
  const message = document.getElementById("notif-message").value.trim();
  const target_cid = document.getElementById("notif-class").value || null;
  const target_batch = document.getElementById("notif-batch").value || null;
  const type = document.getElementById("notif-type").value;
  const result = document.getElementById("notif-result");

  if (!message) { alert("Please enter a message."); return; }

  try {
    const res = await authFetch(`${API}/api/notifications`, {
      method: "POST",
      body: JSON.stringify({ 
        message, 
        target_cid: target_cid ? parseInt(target_cid) : null, 
        target_batch,
        type 
      }),
    });
    const data = await res.json();
    result.style.cssText = res.ok 
      ? "display:block;margin-top:16px;padding:12px;border-radius:6px;font-size:14px;font-weight:600;background:rgba(34,197,94,0.1);color:#22c55e;border:1px solid rgba(34,197,94,0.3)"
      : "display:block;margin-top:16px;padding:12px;border-radius:6px;font-size:14px;font-weight:600;background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3)";
    result.textContent = res.ok ? "✓ Notification sent to students!" : `✗ ${data.error || "Failed to send"}`;
    
    if (res.ok) {
      document.getElementById("notif-message").value = "";
      loadNotifications(); // Refresh the list
    }
  } catch (e) {
    result.style.cssText = "display:block;margin-top:16px;padding:12px;border-radius:6px;font-size:14px;font-weight:600;background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3)";
    result.textContent = "✗ Cannot connect to server.";
  }
}

// ── Section Switching ──────────────────────────────────────────────────────
function showSection(name, el) {
  ["overview","schedule","extra","notify"].forEach(s => {
    const sec = document.getElementById(`section-${s}`);
    if (sec) sec.style.display = "none";
  });
  document.getElementById(`section-${name}`).style.display = "block";
  document.getElementById("dash-section-title").textContent =
    { overview:"Overview", schedule:"My Schedule", extra:"Extra Lecture", notify:"Notifications" }[name];

  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  if (el) el.classList.add("active");

  // Lazy-load data
  if (name === "schedule") loadWeeklySchedule();
  if (name === "notify")   loadNotifications();

  return false;
}

async function markAbsent(slot) {
  if (!confirm(`Are you sure you want to mark yourself absent for ${slot.sname} at ${slot.start_time}? This will notify the Admin to find a substitute.`)) return;

  try {
    const res = await authFetch(`${API}/api/teacher/mark-absent`, {
      method: "POST",
      body: JSON.stringify(slot)
    });
    const data = await res.json();
    if (res.ok) {
      alert("✓ Absence reported. Admin has been notified.");
    } else {
      alert("✗ Error: " + (data.error || "Could not report absence."));
    }
  } catch (err) {
    alert("✗ Network error.");
  }
}
