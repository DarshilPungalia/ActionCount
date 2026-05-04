/**
 * api.js — updated with weight_kg, volume, and metrics APIs
 */

const API_BASE = window.location.origin;

function getToken()    { return localStorage.getItem("ac_token"); }
function setToken(t)   { localStorage.setItem("ac_token", t); }
function clearToken()  { localStorage.removeItem("ac_token"); localStorage.removeItem("ac_username"); }
function authHeaders(extra = {}) {
  const token = getToken();
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...extra }
    : { "Content-Type": "application/json", ...extra };
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options, headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const json = await res.json(); detail = json.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

const Auth = {
  async signup(username, password, email = "") {
    const data = await apiFetch("/api/auth/signup", {
      method: "POST", body: JSON.stringify({ username, password, email }),
    });
    setToken(data.access_token);
    localStorage.setItem("ac_username", username);
    return data;
  },
  async login(email, password) {
    const data = await apiFetch("/api/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    });
    setToken(data.access_token);
    try {
      const payload = JSON.parse(atob(data.access_token.split(".")[1]));
      localStorage.setItem("ac_username", payload.sub || email);
    } catch (_) { localStorage.setItem("ac_username", email); }
    return data;
  },
  logout()    { clearToken(); window.location.href = "/login"; },
  isLoggedIn(){ return !!getToken(); },
  username()  { return localStorage.getItem("ac_username") || ""; },
};

const Profile = {
  async get()            { return apiFetch("/api/user/profile"); },
  async save(profileData){ return apiFetch("/api/user/profile", { method: "POST", body: JSON.stringify(profileData) }); },
};

const Workout = {
  // weight_kg and calories_burnt are optional
  async save(exercise, reps, sets = 1, date = null, weight_kg = null, calories_burnt = null) {
    return apiFetch("/api/workout/save", {
      method: "POST",
      body: JSON.stringify({ exercise, reps, sets, date, weight_kg, calories_burnt }),
    });
  },
  async history()         { return apiFetch("/api/workout/history"); },
  async stats(month = null){
    const qs = month ? `?month=${month}` : "";
    return apiFetch(`/api/workout/stats${qs}`);
  },
  async volume(month = null){
    const qs = month ? `?month=${month}` : "";
    return apiFetch(`/api/workout/volume${qs}`);
  },
  async calories(month = null){
    const qs = month ? `?month=${month}` : "";
    return apiFetch(`/api/workout/calories${qs}`);
  },
};

const Metrics = {
  async log(date, weight_kg = null, height_cm = null) {
    return apiFetch("/api/metrics/log", {
      method: "POST",
      body: JSON.stringify({ date, weight_kg, height_cm }),
    });
  },
  async get() { return apiFetch("/api/metrics"); },
};

const Chat = {
  async send(message)  { return apiFetch("/api/chat", { method: "POST", body: JSON.stringify({ message }) }); },
  async history()      { return apiFetch("/api/chat/history"); },
  async clear()        { return apiFetch("/api/chat", { method: "DELETE" }); },
};

const Plan = {
  /** Fetch today's plan: {weekday, exercises:[{exercise_key,sets,reps,weight_kg}], has_plan} */
  async today(day = null) {
    const qs = day ? `?day=${encodeURIComponent(day)}` : '';
    return apiFetch(`/api/plans/today${qs}`);
  },
  /** Full Mon-Sun weekly schedule */
  async week() { return apiFetch('/api/plans/week'); },
};

function requireAuth() {
  if (!Auth.isLoggedIn()) { window.location.href = "/login"; return false; }
  return true;
}
