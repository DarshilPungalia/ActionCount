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

// ── Login ─────────────────────────────────────────────────────────────────────
document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("loginError");
  const btn  = document.getElementById("loginBtn");
  const user = document.getElementById("loginUser").value.trim();
  const pass = document.getElementById("loginPass").value;

  if (!user || !pass) {
    showError("loginError", "Please enter your username and password.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Signing in…";

  try {
    const data = await Auth.login(user, pass);
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

  if (!user || !pass) {
    showError("signupError", "Username and password are required.");
    return;
  }
  if (pass.length < 6) {
    showError("signupError", "Password must be at least 6 characters.");
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
