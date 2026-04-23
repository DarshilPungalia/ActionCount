/**
 * api.js
 * Centralized API client for ActionCount frontend.
 * All fetch calls go through here — handles auth headers and error normalization.
 */

const API_BASE = window.location.origin;

/** Read JWT token from localStorage */
function getToken() {
  return localStorage.getItem("ac_token");
}

/** Save JWT token to localStorage */
function setToken(token) {
  localStorage.setItem("ac_token", token);
}

/** Remove JWT token (logout) */
function clearToken() {
  localStorage.removeItem("ac_token");
  localStorage.removeItem("ac_username");
}

/** Build Authorization header object */
function authHeaders(extra = {}) {
  const token = getToken();
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...extra }
    : { "Content-Type": "application/json", ...extra };
}

/** Generic fetch wrapper — throws on non-2xx */
async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      detail = json.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

const Auth = {
  async signup(username, password, email = "") {
    const data = await apiFetch("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ username, password, email }),
    });
    setToken(data.access_token);
    localStorage.setItem("ac_username", username);
    return data; // { access_token, is_new_user }
  },

  async login(email, password) {
    const data = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.access_token);
    // Decode JWT to get the username (sub) for local storage
    try {
      const payload = JSON.parse(atob(data.access_token.split(".")[1]));
      localStorage.setItem("ac_username", payload.sub || email);
    } catch (_) {
      localStorage.setItem("ac_username", email);
    }
    return data;
  },

  logout() {
    clearToken();
    window.location.href = "/login";
  },

  isLoggedIn() {
    return !!getToken();
  },

  username() {
    return localStorage.getItem("ac_username") || "";
  },
};

// ── Profile ───────────────────────────────────────────────────────────────────

const Profile = {
  async get() {
    return apiFetch("/api/user/profile");
  },

  async save(profileData) {
    return apiFetch("/api/user/profile", {
      method: "POST",
      body: JSON.stringify(profileData),
    });
  },
};

// ── Workouts ──────────────────────────────────────────────────────────────────

const Workout = {
  async save(exercise, reps, sets = 1, date = null) {
    return apiFetch("/api/workout/save", {
      method: "POST",
      body: JSON.stringify({ exercise, reps, sets, date }),
    });
  },

  async history() {
    return apiFetch("/api/workout/history");
  },

  async stats(month = null) {
    const qs = month ? `?month=${month}` : "";
    return apiFetch(`/api/workout/stats${qs}`);
  },
};

// ── Chat ──────────────────────────────────────────────────────────────────────

const Chat = {
  async send(message) {
    return apiFetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },

  async history() {
    return apiFetch("/api/chat/history");
  },

  async clear() {
    return apiFetch("/api/chat", { method: "DELETE" });
  },
};

// ── Route guard — redirect to login if not authenticated ───────────────────

function requireAuth() {
  if (!Auth.isLoggedIn()) {
    window.location.href = "/login";
    return false;
  }
  return true;
}
