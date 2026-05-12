/**
 * auth.js
 * Login, Signup, and Onboarding logic for ActionCount.
 *
 * Both apps share this file. The behaviour adapts based on the URL query param:
 *   /login?app=tracker    → Tracker App  (indefinite JWT, redirects to /)
 *   /login?app=dashboard  → Dashboard App (7-day JWT, redirects to /welcome)
 *   /login               → defaults to tracker
 */

// ── Detect which app we're serving ───────────────────────────────────────────────
// Read ?app= URL param. Everything falls back to 'tracker' for backwards compatibility.
const _APP_TYPE      = new URLSearchParams(location.search).get('app') || 'tracker';
const _IS_TRACKER    = _APP_TYPE !== 'dashboard';
const _POST_LOGIN_URL = _IS_TRACKER ? '/' : '/welcome';

// ── Redirect if already logged in ─────────────────────────────────────────────
if (Auth.isLoggedIn()) {
  window.location.href = _POST_LOGIN_URL;
}

// ── Card flip ─────────────────────────────────────────────────────────────────
function flipCard() {
  document.getElementById("flipInner").classList.toggle("flipped");
}

// ── Show / hide password ──────────────────────────────────────────────────────
function togglePass(inputId, btn) {
  const inp = document.getElementById(inputId);
  const hidden = inp.type === "password";
  inp.type = hidden ? "text" : "password";
  btn.textContent = hidden ? "🙈" : "👁";
}

// ── Error helpers ─────────────────────────────────────────────────────────────
function showError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.classList.remove("hidden");
}
function clearError(id) {
  const el = document.getElementById(id);
  el.textContent = "";
  el.classList.add("hidden");
}

// ── Password Strength Meter ────────────────────────────────────────────────────
function calcPasswordStrength(p) {
  let score = 0;
  if (p.length >= 12) score++;
  if (p.length >= 16) score++;
  if (/[A-Z]/.test(p)) score++;
  if (/[a-z]/.test(p)) score++;
  if (/[0-9]/.test(p)) score++;
  if (/[^A-Za-z0-9]/.test(p)) score++;
  const levels = [
    { max: 1,  label: "Weak",        color: "#ef4444", pct: 16  },
    { max: 2,  label: "Fair",        color: "#f97316", pct: 32  },
    { max: 3,  label: "Good",        color: "#eab308", pct: 52  },
    { max: 4,  label: "Strong",      color: "#10b981", pct: 75  },
    { max: 99, label: "Very Strong", color: "#6366f1", pct: 100 },
  ];
  return levels.find(l => score <= l.max) || levels[levels.length - 1];
}

(function wireStrengthMeter() {
  const passEl = document.getElementById("signupPass");
  if (!passEl) return;
  passEl.addEventListener("input", () => {
    const val  = passEl.value;
    const wrap = document.getElementById("pwStrengthWrap");
    const bar  = document.getElementById("pwStrengthBar");
    const lbl  = document.getElementById("pwStrengthLabel");
    if (!val) { wrap.style.display = "none"; return; }
    wrap.style.display = "block";
    const { label, color, pct } = calcPasswordStrength(val);
    // Gradient always starts red, ends at current strength colour
    bar.style.width      = pct + "%";
    bar.style.background = `linear-gradient(90deg, #ef4444 0%, ${color} 100%)`;
    lbl.textContent      = label;
    lbl.style.color      = color;
  });
})();

// ── Login ─────────────────────────────────────────────────────────────────────
document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("loginError");
  const btn   = document.getElementById("loginBtn");
  const email = document.getElementById("loginEmail").value.trim();
  const pass  = document.getElementById("loginPass").value;

  if (!email || !pass) {
    showError("loginError", "Please enter your email and password.");
    return;
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    showError("loginError", "Please enter a valid email address.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Signing in…";

  try {
    const data = await Auth.login(email, pass, _APP_TYPE);
    if (data.is_new_user) {
      showOnboarding();
    } else {
      window.location.href = _POST_LOGIN_URL;
    }
  } catch (err) {
    showError("loginError", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign In";
  }
});

// ── Signup ────────────────────────────────────────────────────────────────────
document.getElementById("signupForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("signupError");
  const btn   = document.getElementById("signupBtn");
  const user  = document.getElementById("signupUser").value.trim();
  const email = document.getElementById("signupEmail").value.trim();
  const pass  = document.getElementById("signupPass").value;

  if (!user || !pass || !email) {
    showError("signupError", "Username, email and password are all required.");
    return;
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    showError("signupError", "Please enter a valid email address.");
    return;
  }
  if (pass.length < 12) {
    showError("signupError", "Password must be at least 12 characters long.");
    return;
  }
  if (!/[A-Z]/.test(pass)) {
    showError("signupError", "Password must contain at least one uppercase letter.");
    return;
  }
  if (!/[0-9]/.test(pass)) {
    showError("signupError", "Password must contain at least one digit.");
    return;
  }
  if (!/[^A-Za-z0-9]/.test(pass)) {
    showError("signupError", "Password must contain at least one special character.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Creating account…";

  try {
    await Auth.signup(user, pass, email, _APP_TYPE);
    // New users always go to onboarding
    sessionStorage.setItem('ac_is_new_user', '1');   // welcome.html reads this
    showOnboarding();
  } catch (err) {
    showError("signupError", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Create Account";
  }
});

// ── Onboarding modal ──────────────────────────────────────────────────────────
function showOnboarding() {
  document.getElementById("onboardingOverlay").classList.remove("hidden");
  goToStep(1);
}

// Goal option selection (radio via custom UI)
document.querySelectorAll(".goal-option").forEach((label) => {
  label.addEventListener("click", () => {
    document.querySelectorAll(".goal-option div").forEach((d) => {
      d.classList.remove("border-indigo-500", "bg-indigo-500/10");
      d.classList.add("border-white/10");
    });
    label.querySelector("div").classList.remove("border-white/10");
    label.querySelector("div").classList.add("border-indigo-500", "bg-indigo-500/10");
    label.querySelector("input").checked = true;
  });
});

// Dietary restriction tags
document.querySelectorAll("#dietTags .tag-btn").forEach((btn) => {
  btn.addEventListener("click", () => btn.classList.toggle("active"));
});

// Equipment tags (wired after DOM ready — step 3 exists in HTML)
document.querySelectorAll(".equip-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    // "none" is exclusive — if selected, deselect others; if another selected, deselect none
    if (btn.dataset.val === "none") {
      document.querySelectorAll(".equip-btn").forEach(b => b.classList.remove("active"));
    } else {
      document.querySelector('.equip-btn[data-val="none"]')?.classList.remove("active");
    }
    btn.classList.toggle("active");
  });
});

// ── Unified step navigator ────────────────────────────────────────────────────
const _STEPS   = 4;
const _TITLES  = [
  { icon: "🎯", title: "Tell us about yourself",  sub: "Basic stats for your AI coach" },
  { icon: "🏆", title: "Your fitness goal",        sub: "What are you working towards?" },
  { icon: "🏋️", title: "Your equipment",           sub: "We'll tailor plans to what you have" },
  { icon: "📅", title: "Build your first plan",    sub: "Let's get your week scheduled!" },
];

function goToStep(n) {
  for (let i = 1; i <= _STEPS; i++) {
    const stepEl = document.getElementById(`obStep${i}`);
    const dotEl  = document.getElementById(`step${i}Dot`);
    if (!stepEl || !dotEl) continue;
    stepEl.classList.toggle("hidden", i !== n);
    dotEl.classList.toggle("bg-indigo-500", i <= n);
    dotEl.classList.toggle("bg-white/10",   i > n);
  }
  const meta = _TITLES[n - 1];
  if (meta) {
    const icon = document.getElementById("ob-icon");
    const title = document.getElementById("ob-title");
    const sub   = document.getElementById("ob-subtitle");
    if (icon)  icon.textContent  = meta.icon;
    if (title) title.textContent = meta.title;
    if (sub)   sub.textContent   = meta.sub;
  }
}

// Keep legacy names for the inline onclick attributes still present in the HTML
function goToStep1() { goToStep(1); }
function goToStep2() { goToStep(2); }

// ── Step 1 → 2 validation ────────────────────────────────────────────────────
// The Next → button calls goToStep(2) directly; we validate inline via override
const _origGoToStep = goToStep;
// Re-bind step 1 Next button with validation
(function() {
  // Replace onclick on step1's Next button by overriding at click time
  document.querySelector('#obStep1 .btn-primary')?.addEventListener('click', function(e) {
    e.stopImmediatePropagation();
    const weight = document.getElementById("obWeight").value;
    const height = document.getElementById("obHeight").value;
    const age    = document.getElementById("obAge").value;
    const gender = document.getElementById("obGender").value;
    if (!weight || !height || !age || !gender) {
      alert("Please fill in all fields before proceeding.");
      return;
    }
    goToStep(2);
  }, true);

  // Step 2 → 3 validation
  document.querySelector('#obStep2 .btn-primary')?.addEventListener('click', function(e) {
    e.stopImmediatePropagation();
    const target = document.querySelector('input[name="target"]:checked');
    if (!target) {
      const err = document.getElementById("obError2");
      if (err) { err.textContent = "Please select a fitness goal."; err.classList.remove("hidden"); }
      return;
    }
    const err = document.getElementById("obError2");
    if (err) err.classList.add("hidden");
    goToStep(3);
  }, true);
})();

// ── Profile submit (from Step 3 "Save Profile" button) ───────────────────────
async function submitProfile() {
  const target = document.querySelector('input[name="target"]:checked');
  if (!target) {
    goToStep(2);
    alert("Please select a fitness goal first.");
    return;
  }

  const restrictions = [...document.querySelectorAll("#dietTags .tag-btn.active")].map(b => b.dataset.val);
  const equipment    = [...document.querySelectorAll(".equip-btn.active")].map(b => b.dataset.val);
  const goalsExtra   = (document.getElementById("obGoalsExtra")?.value || "").trim();

  const payload = {
    weight_kg:              parseFloat(document.getElementById("obWeight").value),
    height_cm:              parseFloat(document.getElementById("obHeight").value),
    age:                    parseInt(document.getElementById("obAge").value, 10),
    gender:                 document.getElementById("obGender").value,
    target:                 target.value,
    goals_extra:            goalsExtra || null,
    equipment_availability: equipment.length ? equipment : ["none"],
    dietary_restrictions:   restrictions,
  };

  const btn = document.getElementById("obSubmitBtn");
  btn.disabled = true;
  btn.textContent = "Saving…";

  try {
    await Profile.save(payload);
    // Advance to step 4 — first plan creation
    goToStep(4);
    _adaptStep4ForApp();  // hides Plans/Chatbot buttons for Tracker App
  } catch (err) {
    alert("Could not save profile: " + err.message);
    btn.disabled = false;
    btn.textContent = "Save Profile →";
  }
}

// ── Step 4 navigation helpers ──────────────────────────────────────────────
// For the Tracker App, only the "Skip" option is shown (plans & chatbot live in
// the Dashboard App).  We adapt Step 4 after the profile is saved.
function _adaptStep4ForApp() {
  if (!_IS_TRACKER) return;   // Dashboard App — show all options as usual

  // Hide the two-column grid (Manual + AI buttons)
  const grid = document.querySelector('#obStep4 .grid');
  if (grid) grid.style.display = 'none';

  // Update the description
  const desc = document.querySelector('#obStep4 p');
  if (desc) desc.textContent = 'Your profile is saved. Head straight to the Tracker and start your first workout!';

  // Update skip button label
  const skipBtn = document.querySelector('#obStep4 button[onclick="skipPlanCreation()"]');
  if (skipBtn) skipBtn.textContent = '🚀 Go to Tracker';
}

function goToPlansManual() {
  // Mark welcome seen so plans page doesn't redirect back
  sessionStorage.setItem("seen_welcome", "1");
  window.location.href = "/plans";
}

function goToChatForPlan() {
  sessionStorage.setItem("seen_welcome", "1");
  // Pre-seed a plan-generation prompt in sessionStorage for chatbot.html to pick up
  sessionStorage.setItem("chatbot_initial_prompt", "Generate a weekly workout plan for me based on my goals and equipment.");
  window.location.href = "/chatbot";
}

function skipPlanCreation() {
  sessionStorage.setItem("seen_welcome", "1");
  window.location.href = _POST_LOGIN_URL;
}
