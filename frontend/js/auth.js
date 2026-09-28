/**
 * auth.js — Shared JWT auth helper for Teacher & Admin dashboards
 */
const API = "http://localhost:5000";

function getToken()   { return localStorage.getItem("dc_token"); }
function getIdentity(){ return JSON.parse(localStorage.getItem("dc_identity") || "{}"); }

async function handleLogin(e) {
  e.preventDefault();
  const btn      = document.getElementById("login-btn");
  const errEl    = document.getElementById("login-error");
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();

  btn.disabled = true;
  btn.textContent = "Signing in…";
  errEl.style.display = "none";

  try {
    const res  = await fetch(`${API}/api/login`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent  = data.error || "Login failed. Check your credentials.";
      errEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Sign In →";
      return;
    }

    localStorage.setItem("dc_token",    data.token);
    localStorage.setItem("dc_identity", JSON.stringify(data));

    // Show dashboard, hide login
    document.getElementById("login-overlay").style.display = "none";
    document.getElementById("dashboard").style.display      = "flex";

    // Init dashboard
    if (typeof initDashboard === "function") initDashboard(data);

  } catch (err) {
    errEl.textContent  = "Cannot reach server. Is Flask running?";
    errEl.style.display = "block";
    btn.disabled = false;
    btn.textContent = "Sign In →";
  }
}

function logout() {
  localStorage.removeItem("dc_token");
  localStorage.removeItem("dc_identity");
  location.reload();
}

async function authFetch(url, options = {}) {
  const token = getToken();
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      "Authorization": `Bearer ${token}`,
      "Content-Type":  "application/json",
    },
  });
}

// Auto-restore session on page load
document.addEventListener("DOMContentLoaded", () => {
  const token = getToken();
  if (!token) return;   // Stay on login screen

  const identity = getIdentity();
  // Skip login screen, go straight to dashboard
  const loginEl = document.getElementById("login-overlay");
  const dashEl  = document.getElementById("dashboard");
  if (loginEl) loginEl.style.display = "none";
  if (dashEl)  dashEl.style.display  = "flex";
  if (typeof initDashboard === "function") initDashboard(identity);
});
