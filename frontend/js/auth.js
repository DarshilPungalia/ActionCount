/**
 * auth.js
 * Login, Signup, and Onboarding logic for ActionCount.
 */

// ── Redirect if already logged in ─────────────────────────────────────────────
if (Auth.isLoggedIn()) {
  window.location.href = "/";
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
    const data = await Auth.login(email, pass);
    if (data.is_new_user) {
      showOnboarding();
    } else {
      window.location.href = "/";
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
    await Auth.signup(user, pass, email);
    // New users always go to onboarding
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
  btn.addEventListener("click", () => {
    btn.classList.toggle("active");
  });
});

// Step navigation
function goToStep2() {
  const weight = document.getElementById("obWeight").value;
  const height = document.getElementById("obHeight").value;
  const age    = document.getElementById("obAge").value;
  const gender = document.getElementById("obGender").value;
  if (!weight || !height || !age || !gender) {
    alert("Please fill in all fields before proceeding.");
    return;
  }
  document.getElementById("obStep1").classList.add("hidden");
  document.getElementById("obStep2").classList.remove("hidden");
  document.getElementById("step2Dot").classList.replace("bg-white/10", "bg-indigo-500");
}

function goToStep1() {
  document.getElementById("obStep2").classList.add("hidden");
  document.getElementById("obStep1").classList.remove("hidden");
  document.getElementById("step2Dot").classList.replace("bg-indigo-500", "bg-white/10");
}

// Submit onboarding
document.getElementById("onboardingForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("obError");

  const target = document.querySelector('input[name="target"]:checked');
  if (!target) {
    showError("obError", "Please select a fitness goal.");
    return;
  }

  const restrictions = [...document.querySelectorAll("#dietTags .tag-btn.active")].map(
    (b) => b.dataset.val
  );

  const payload = {
    weight_kg: parseFloat(document.getElementById("obWeight").value),
    height_cm: parseFloat(document.getElementById("obHeight").value),
    age:       parseInt(document.getElementById("obAge").value, 10),
    gender:    document.getElementById("obGender").value,
    target:    target.value,
    dietary_restrictions: restrictions,
  };

  const btn = document.getElementById("obSubmitBtn");
  btn.disabled = true;
  btn.textContent = "Saving…";

  try {
    await Profile.save(payload);
    window.location.href = "/";
  } catch (err) {
    showError("obError", err.message);
    btn.disabled = false;
    btn.textContent = "Get Started 🚀";
  }
});
