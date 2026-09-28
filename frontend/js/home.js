/**
 * home.js — Dynamic Campus Public Homepage Logic
 * Handles: clock, class/batch selector, timetable display,
 *          current/next lecture cards, classroom cards grouped by Building+Floor
 */

const API = "http://localhost:5000";

// State
let selectedCid   = null;
let selectedBatch = "";
let classroomRefreshTimer = null;
let lectureRefreshTimer   = null;

// ── Clock ────────────────────────────────────────────────────────────────
function updateClock() {
  document.getElementById("nav-clock").textContent =
    new Date().toLocaleTimeString("en-IN", { hour:"2-digit", minute:"2-digit", second:"2-digit" });
}
setInterval(updateClock, 1000);
updateClock();

// ── Class Selector ────────────────────────────────────────────────────────
// Maps semester number → year label
const SEM_YEAR = { 1:"FE",2:"FE",3:"SE",4:"SE",5:"TE",6:"TE",7:"BE",8:"BE" };
// Convert Roman numeral suffix to digit: "TE-I" -> "TE1", "SE-III" -> "SE3"
function formatDivision(className) {
  return (className || "")
    .replace("-I","1").replace("-II","2").replace("-III","3")
    .replace("-IV","4").replace("-V","5").replace("-VI","6");
}

async function loadClasses() {
  try {
    const res  = await fetch(`${API}/api/classes`);
    const data = await res.json();
    const sel  = document.getElementById("sel-class");

    // Group by year
    const grouped = {};
    data.forEach(cls => {
      const year = SEM_YEAR[cls.sem] || ("Sem" + cls.sem);
      if (!grouped[year]) grouped[year] = [];
      grouped[year].push(cls);
    });

    Object.keys(grouped).sort().forEach(year => {
      const og = document.createElement("optgroup");
      og.label = year;
      grouped[year].forEach(cls => {
        const opt = document.createElement("option");
        opt.value = cls.cid;
        const div = formatDivision(cls.class_name);
        opt.textContent = `${div}  (${cls.class_room_no})`;
        og.appendChild(opt);
      });
      sel.appendChild(og);
    });
  } catch (e) { console.error("loadClasses:", e); }
}

async function onClassChange() {
  const sel  = document.getElementById("sel-class");
  const cid  = parseInt(sel.value);
  const bSel = document.getElementById("sel-batch");

  bSel.innerHTML = '<option value="">— All (Theory) —</option>';
  bSel.disabled  = true;
  document.getElementById("view-btn").disabled = true;
  if (!cid) { selectedCid = null; return; }
  selectedCid = cid;

  try {
    const res     = await fetch(`${API}/api/batches?cid=${cid}`);
    const batches = await res.json();
    batches.forEach(b => {
      const opt = document.createElement("option");
      opt.value = b; opt.textContent = `Batch ${b}`;
      bSel.appendChild(opt);
    });
    if (batches.length) bSel.disabled = false;
    document.getElementById("view-btn").disabled = false;
  } catch (e) { console.error("onClassChange:", e); }
}

function onBatchChange() {
  selectedBatch = document.getElementById("sel-batch").value;
  document.getElementById("view-btn").disabled = !selectedCid;
}

// ── Student View ──────────────────────────────────────────────────────────
async function loadStudentView() {
  if (!selectedCid) return;
  document.getElementById("lecture-strip").style.display     = "block";
  document.getElementById("timetable-section").style.display = "block";
  document.getElementById("lecture-strip").scrollIntoView({ behavior:"smooth" });

  const selEl = document.getElementById("sel-class");
  const label = selEl.options[selEl.selectedIndex].text.trim() +
                (selectedBatch ? ` | Batch ${selectedBatch}` : " | All");
  document.getElementById("timetable-label").textContent = label;

  await Promise.all([
    loadCurrentLecture(),
    loadNextLecture(),
    loadWeeklyTimetable(),
    loadRecentNotifications()
  ]);
  clearInterval(lectureRefreshTimer);
  lectureRefreshTimer = setInterval(() => { loadCurrentLecture(); loadNextLecture(); }, 60000);
}

async function loadRecentNotifications() {
  const list = document.getElementById("notifications-list");
  const banner = document.getElementById("notifications-banner");
  if (!list) return;

  try {
    const url = `${API}/api/notifications` + (selectedCid ? `?cid=${selectedCid}${selectedBatch ? `&batch=${selectedBatch}` : ""}` : "");
    const res = await fetch(url);
    const data = await res.json();

    if (!data.length) {
      if (!selectedCid) {
        banner.style.display = "none";
      } else {
        list.innerHTML = `<div style="font-size:13px; font-style:italic; color:var(--text-secondary);">No active notifications for this class.</div>`;
        banner.style.display = "block";
      }
      return;
    }

    banner.style.display = "block";
    list.innerHTML = "";
    data.forEach(n => {
      const item = document.createElement("div");
      item.style.cssText = "padding: 10px 14px; border-radius: 10px; background: rgba(255,255,255,0.03); display: flex; align-items: center; gap: 12px; border: 1px solid rgba(255,255,255,0.05); transition: transform 0.2s;";
      
      const typeColors = { info: "#6366f1", warning: "#f59e0b", change: "#3b82f6", cancel: "#ef4444" };
      const col = typeColors[n.type] || "#6366f1";

      const typeBadge = document.createElement("span");
      typeBadge.style.cssText = `font-size:10px; font-weight:800; text-transform:uppercase; padding: 4px 8px; border-radius: 6px; background: ${col}22; color: ${col}; border: 1px solid ${col}44; letter-spacing: 0.5px;`;
      typeBadge.textContent = n.type;

      const msg = document.createElement("div");
      msg.style.cssText = "flex: 1; color: var(--text-primary); font-size: 14px; line-height: 1.5;";
      msg.textContent = n.message;

      item.appendChild(typeBadge);
      item.appendChild(msg);
      list.appendChild(item);
    });
  } catch (e) {
    console.error("loadRecentNotifications error:", e);
  }
}

// ── Current Lecture ────────────────────────────────────────────────────────
async function loadCurrentLecture() {
  try {
    const d = await (await fetch(`${API}/api/timetable/now?cid=${selectedCid}&batch=${selectedBatch}`)).json();
    if (d && d.sname) {
      document.getElementById("current-subject").textContent = d.sname;
      document.getElementById("current-time").textContent    = `${d.start_time} to ${d.end_time}`;
      setChipText("current-teacher", d.tname || "");
      setChipText("current-room",    d.room  || "");
      if (d.is_extra) {
        document.getElementById("current-subject").innerHTML = `${d.sname} <span class="extra-badge">EXTRA</span>`;
      }
    } else {
      document.getElementById("current-subject").textContent = "No lecture running";
      document.getElementById("current-time").textContent    = "";
      setChipText("current-teacher", ""); setChipText("current-room","");
    }
  } catch (e) { console.error(e); }
}

// ── Next Lecture ───────────────────────────────────────────────────────────
async function loadNextLecture() {
  try {
    const d = await (await fetch(`${API}/api/timetable/next?cid=${selectedCid}&batch=${selectedBatch}`)).json();
    if (d && d.sname) {
      document.getElementById("next-subject").textContent = d.sname;
      document.getElementById("next-time").textContent    = `${d.start_time} to ${d.end_time}`;
      setChipText("next-teacher", d.tname || "");
      setChipText("next-room",    d.room  || "");
      if (d.is_extra) {
        document.getElementById("next-subject").innerHTML = `${d.sname} <span class="extra-badge">EXTRA</span>`;
      }
    } else {
      document.getElementById("next-subject").textContent = "No more lectures today";
      document.getElementById("next-time").textContent    = "";
      setChipText("next-teacher", ""); setChipText("next-room","");
    }
  } catch (e) { console.error(e); }
}

function setChipText(id, text) {
  const el = document.getElementById(id);
  const svg = el.querySelector("svg");
  el.textContent = text;
  if (svg) el.prepend(svg);
}

// ── Weekly Timetable ───────────────────────────────────────────────────────
const DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday"];

async function loadWeeklyTimetable() {
  const tbody = document.getElementById("timetable-body");
  tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">Loading...</td></tr>`;
  try {
    const rows = await (await fetch(`${API}/api/timetable/student?cid=${selectedCid}&batch=${selectedBatch}`)).json();
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="loading-cell">No data found.</td></tr>`;
      return;
    }
    const slots = {};
    rows.forEach(r => {
      const key = `${r.start_time}|${r.end_time}`;
      if (!slots[key]) slots[key] = {};
      if (!slots[key][r.day]) slots[key][r.day] = [];
      slots[key][r.day].push(r);
    });
    const nowMins = new Date().getHours()*60 + new Date().getMinutes();
    tbody.innerHTML = "";
    Object.keys(slots).sort().forEach(key => {
      const [start, end] = key.split("|");
      const [sh,sm] = start.split(":").map(Number);
      const [eh,em] = end.split(":").map(Number);
      const isCur   = nowMins >= sh*60+sm && nowMins < eh*60+em;
      const tr = document.createElement("tr");
      if (isCur) tr.classList.add("current-row");
      tr.innerHTML = `<td class="time-col">${start}<br/><small>${end}</small></td>`;
      DAYS.forEach(day => {
        const cells = slots[key][day] || [];
        if (!cells.length) { tr.innerHTML += `<td class="empty-cell">—</td>`; return; }
        let html = "";
        cells.forEach(c => {
          html += `<div>`;
          if (c.batch) html += `<span class="cell-batch">${c.batch}</span><br/>`;
          html += `<span class="cell-subject">${c.sname||"—"}</span><br/>`;
          if (c.tname) html += `<span class="cell-teacher">${c.tname}</span>`;
          if (c.room)  html += `<span class="cell-teacher"> · ${c.room}</span>`;
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

// ═══════════════════════════════════════════════════════════════════════════
// CLASSROOM CARDS — Building → Floor grouping
// Room format: "A1-309" → building=A1, floor=3, "F1-201" → building=F1, floor=2
// ═══════════════════════════════════════════════════════════════════════════

function parseRoom(room) {
  // Matches: A1-309, F1-101, A2-204 etc.
  const m = (room||"").match(/^([A-Za-z]\d+)-(\d)(\d+)$/);
  if (m) return { building: m[1].toUpperCase(), floor: m[2] };
  return { building:"Other", floor:"0" };
}

async function loadClassrooms() {
  const grid = document.getElementById("classroom-grid");
  try {
    const data = await (await fetch(`${API}/api/classrooms`)).json();
    if (!data.length) {
      grid.innerHTML = `<div class="loading-placeholder">No classroom data available.</div>`;
      return;
    }

    // Group: buildings[building][floor] = [rooms]
    const buildings = {};
    data.forEach(c => {
      const { building, floor } = parseRoom(c.room);
      if (!buildings[building])         buildings[building]         = {};
      if (!buildings[building][floor])  buildings[building][floor]  = [];
      buildings[building][floor].push(c);
    });

    grid.innerHTML = "";

    Object.keys(buildings).sort().forEach(bName => {
      const floors     = buildings[bName];
      const allRooms   = Object.values(floors).flat();
      const occCount   = allRooms.filter(r => r.status === "occupied").length;
      const freeCount  = allRooms.length - occCount;

      // Building section wrapper
      const section = document.createElement("div");
      section.className = "building-section";

      // Building header
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

      // Floors
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
          card.id = `room-${c.room.replace(/[^a-z0-9]/gi,"-")}`;

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
    console.error("classrooms error:", e);
    grid.innerHTML = `<div class="loading-placeholder">Could not connect to server.</div>`;
  }
}

// ── WebSocket ──────────────────────────────────────────────────────────────
function initSocket() {
  try {
    const socket = io(API);
    socket.on("connect", () => socket.emit("subscribe", { room:"classrooms" }));
    socket.on("classroom_update",  () => loadClassrooms());
    socket.on("timetable_updated", ({ cid }) => {
      if (selectedCid === cid) { loadWeeklyTimetable(); loadCurrentLecture(); loadNextLecture(); }
      loadClassrooms();
    });
    socket.on("new_notification", d => {
      const isGlobal = !d.target_cid;
      const isTargetedClass = d.target_cid == selectedCid;
      const isTargetedBatch = !d.target_batch || d.target_batch == selectedBatch;

      if (isGlobal || (isTargetedClass && isTargetedBatch)) {
        showToast(d.message, d.type || "info");
        loadRecentNotifications(); // Refresh the list
      }
    });
  } catch (e) {
    console.warn("WS unavailable, polling.");
    setInterval(loadClassrooms, 60000);
  }
}

function showToast(message, type) {
  const c = { info:"#6366f1",warning:"#f59e0b",change:"#38bdf8",extra:"#22c55e",cancel:"#ef4444" };
  const t = document.createElement("div");
  t.style.cssText = `position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${(c[type]||c.info)}22;border:1px solid ${(c[type]||c.info)}55;
    color:#fff;padding:14px 20px;border-radius:12px;font-size:14px;font-weight:500;
    max-width:360px;backdrop-filter:blur(12px);font-family:'Inter',sans-serif;`;
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 5000);
}

// ── Init ───────────────────────────────────────────────────────────────────
(async function init() {
  await loadClasses();
  await loadClassrooms();
  await initFacultyHub();
  await loadRecentNotifications();
  initSocket();
  classroomRefreshTimer = setInterval(loadClassrooms, 120000);
})();

// ── Faculty Information Hub & Search ───────────────────────────────────────
async function initFacultyHub() {
  const searchInput = document.getElementById("teacher-search-input");
  const suggestionsBox = document.getElementById("teacher-suggestions");

  if (!searchInput) return;

  // 1. Setup Search Autocomplete
  searchInput.addEventListener("input", async (e) => {
    const val = e.target.value.trim();
    if (!val) {
      suggestionsBox.style.display = "none";
      return;
    }

    try {
      const res = await fetch(`${API}/api/faculty/search?q=${encodeURIComponent(val)}`);
      const matches = await res.json();
      
      if (matches.length === 0) {
        suggestionsBox.innerHTML = '<div class="suggestion-item" style="color:var(--text-muted)">No matches found</div>';
      } else {
        suggestionsBox.innerHTML = "";
        matches.forEach(t => {
          const div = document.createElement("div");
          div.className = "suggestion-item";
          div.innerHTML = `
            <div class="suggestion-name">${t.tname}</div>
            <div class="suggestion-meta">${t.department || "General"} · Cabin: ${t.cabin_no || "—"}</div>
          `;
          div.addEventListener("click", () => {
            searchInput.value = t.tname;
            suggestionsBox.style.display = "none";
            showFacultyProfile(t.tid);
          });
          suggestionsBox.appendChild(div);
        });
      }
      suggestionsBox.style.display = "block";
    } catch (err) {
      console.error(err);
    }
  });

  // Close suggestions on clicking outside
  document.addEventListener("click", (e) => {
    if (e.target !== searchInput && e.target !== suggestionsBox) {
      suggestionsBox.style.display = "none";
    }
  });

  // 2. Load Department Accordion
  await loadDepartmentsAccordion();
}

async function loadDepartmentsAccordion() {
  const container = document.getElementById("departments-list");
  if (!container) return;

  try {
    const res = await fetch(`${API}/api/faculty`);
    const faculty = await res.json();

    if (faculty.length === 0) {
      container.innerHTML = '<div class="loading-cell">No faculty members found.</div>';
      return;
    }

    // Group by department
    const groups = {};
    faculty.forEach(f => {
      const dept = f.department || "General / Unassigned";
      if (!groups[dept]) groups[dept] = [];
      groups[dept].push(f);
    });

    container.innerHTML = "";
    Object.keys(groups).sort().forEach(dept => {
      const teachers = groups[dept];
      
      const item = document.createElement("div");
      item.className = "accordion-item";
      
      const header = document.createElement("div");
      header.className = "accordion-header";
      header.innerHTML = `
        <span>${dept} (${teachers.length})</span>
        <svg viewBox="0 0 20 20" fill="currentColor" style="width:16px; height:16px; transition:transform 0.2s;">
          <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
        </svg>
      `;
      
      const content = document.createElement("div");
      content.className = "accordion-content";
      content.style.display = "none";
      
      const grid = document.createElement("div");
      grid.className = "faculty-grid";
      
      teachers.forEach(t => {
        const card = document.createElement("div");
        card.className = "faculty-card glass-card";
        card.innerHTML = `
          <div style="font-weight:700; color:var(--text-primary); margin-bottom:4px;">${t.tname}</div>
          <div style="font-size:12px; color:var(--text-secondary)">Cabin: ${t.cabin_no || "—"}</div>
        `;
        card.addEventListener("click", () => showFacultyProfile(t.tid));
        grid.appendChild(card);
      });
      
      content.appendChild(grid);
      
      header.addEventListener("click", () => {
        const isCollapsed = content.style.display === "none";
        content.style.display = isCollapsed ? "block" : "none";
        header.querySelector("svg").style.transform = isCollapsed ? "rotate(180deg)" : "rotate(0deg)";
      });
      
      item.appendChild(header);
      item.appendChild(content);
      container.appendChild(item);
    });

  } catch (err) {
    container.innerHTML = '<div class="loading-cell" style="color:var(--red)">Failed to load departments.</div>';
  }
}

async function showFacultyProfile(tid) {
  const placeholder = document.getElementById("teacher-details-placeholder");
  const content = document.getElementById("teacher-details-content");

  if (!placeholder || !content) return;

  placeholder.style.display = "none";
  content.style.display = "block";
  content.innerHTML = '<div class="loading-cell">Fetching profile & schedules...</div>';

  try {
    const res = await fetch(`${API}/api/faculty/${tid}/info`);
    if (!res.ok) throw new Error("Faculty profile not found");
    const data = await res.json();
    const t = data.teacher;

    let badgeColorStyle = "background:var(--green-bg);color:var(--green);border-color:rgba(34,197,94,0.3);";
    if (t.status === "In Lecture") {
      badgeColorStyle = "background:var(--red-bg);color:var(--red);border-color:rgba(239,68,68,0.3);";
    } else if (t.status === "Busy") {
      badgeColorStyle = "background:var(--amber-bg);color:var(--amber);border-color:rgba(245,158,11,0.3);";
    } else if (t.status === "On Leave") {
      badgeColorStyle = "background:rgba(255,255,255,0.05);color:var(--text-muted);border-color:var(--border);";
    }

    // Render Free Slots HTML
    let freeSlotsHtml = '<div class="free-slots-grid">';
    const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
    DAYS.forEach(day => {
      const slots = data.free_slots[day] || [];
      freeSlotsHtml += `
        <div class="free-slot-day">
          <div class="free-slot-day-name">${day.substring(0,3)}</div>
          ${slots.length === 0 ? '<div class="no-slots">No slots</div>' : slots.map(s => `<span class="free-slot-badge">${s}</span>`).join('')}
        </div>
      `;
    });
    freeSlotsHtml += '</div>';

    // Render Timetable HTML
    let timetableHtml = `
      <div class="table-wrapper" style="margin-top:16px;">
        <table class="timetable-table" style="font-size:12px;">
          <thead>
            <tr>
              <th>Day</th>
              <th>Time</th>
              <th>Subject</th>
              <th>Class & Room</th>
            </tr>
          </thead>
          <tbody>
            ${data.weekly_schedule.length === 0 ? '<tr><td colspan="4" class="loading-cell">No classes scheduled this week.</td></tr>' : 
              data.weekly_schedule.map(s => `
                <tr>
                  <td style="font-weight:700">${s.day}</td>
                  <td>${s.start_time} - ${s.end_time}</td>
                  <td style="color:var(--accent-light); font-weight:700;">${s.subject} ${s.is_extra ? '<span class="extra-badge">EXTRA</span>':''}</td>
                  <td>${s.class} ${s.room ? `· 📍 ${s.room}`:''}</td>
                </tr>
              `).join('')
            }
          </tbody>
        </table>
      </div>
    `;

    content.innerHTML = `
      <!-- Header Profile Info -->
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 20px;">
        <div>
          <h2 style="font-size:22px; font-weight:800; color:white; margin-bottom:4px;">${t.tname}</h2>
          <p style="font-size:13px; color:var(--text-secondary);">${t.department}</p>
        </div>
        <div class="live-badge" style="${badgeColorStyle}">
          ${t.status === "In Lecture" ? '<span class="live-dot"></span>' : ''} ${t.status}
        </div>
      </div>

      <div style="font-size:14px; color:var(--text-secondary); margin-bottom: 24px; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px solid var(--border);">
        <strong>Current Status:</strong> ${t.details}
        ${t.current_room ? `<br><strong>Current Room:</strong> <span style="color:var(--accent-light); font-weight:700;">📍 ${t.current_room}</span>` : ''}
      </div>

      <!-- Quick Details Grid -->
      <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px;">
        <div class="meta-chip" style="border-radius:8px; justify-content:center; flex-direction:column; padding:12px; height:auto; width:100%;">
          <small style="color:var(--text-muted); font-size:10px; text-transform:uppercase;">Cabin Number</small>
          <strong style="color:white; font-size:14px; margin-top:2px;">${t.cabin_no || "—"}</strong>
        </div>
        <div class="meta-chip" style="border-radius:8px; justify-content:center; flex-direction:column; padding:12px; height:auto; width:100%;">
          <small style="color:var(--text-muted); font-size:10px; text-transform:uppercase;">Email Address</small>
          <strong style="color:white; font-size:11px; margin-top:2px; word-break:break-all;" title="${t.email || "—"}">${t.email || "—"}</strong>
        </div>
        <div class="meta-chip" style="border-radius:8px; justify-content:center; flex-direction:column; padding:12px; height:auto; width:100%;">
          <small style="color:var(--text-muted); font-size:10px; text-transform:uppercase;">Phone Number</small>
          <strong style="color:white; font-size:13px; margin-top:2px;">${t.phone || "—"}</strong>
        </div>
      </div>

      <!-- Collapsible Timetable -->
      <div class="accordion-item" style="border-color: var(--border);">
        <div class="accordion-header" id="prof-timetable-header" style="padding:12px 16px; font-size:14px;">
          <span>Weekly Timetable Schedule</span>
          <svg viewBox="0 0 20 20" fill="currentColor" style="width:14px; height:14px; transform: rotate(0deg); transition:transform 0.2s;">
            <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </div>
        <div class="accordion-content" id="prof-timetable-content" style="display:none; padding:12px;">
          ${timetableHtml}
        </div>
      </div>

      <!-- Free Slots Section -->
      <div style="margin-top:24px;">
        <h4 style="font-size:14px; font-weight:700; color:white; margin-bottom:8px;">Calculated Weekly Free Slots</h4>
        <p style="font-size:11px; color:var(--text-secondary); margin-bottom:12px;">
          Calculated dynamically based on classes, approved extra lectures, and leave/status reports.
        </p>
        ${freeSlotsHtml}
      </div>
    `;

    // Hook collapsible click
    const ttHeader = document.getElementById("prof-timetable-header");
    const ttContent = document.getElementById("prof-timetable-content");
    if (ttHeader && ttContent) {
      ttHeader.addEventListener("click", () => {
        const isCollapsed = ttContent.style.display === "none";
        ttContent.style.display = isCollapsed ? "block" : "none";
        ttHeader.querySelector("svg").style.transform = isCollapsed ? "rotate(180deg)" : "rotate(0deg)";
      });
    }

  } catch (err) {
    content.innerHTML = `<div class="loading-cell" style="color:var(--red)">Failed to load profile details. ${err.message}</div>`;
  }
}
