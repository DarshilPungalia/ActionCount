/**
 * tracker.js
 * Save Set button + weight input integration for the live tracker page.
 */

const saveBtn  = document.getElementById("btn-save-set");
const saveHint = document.getElementById("save-hint");
const toast    = document.getElementById("save-toast");

const EXERCISE_DISPLAY_MAP = {
  squat: "Squat", pushup: "Push-Up", bicep_curl: "Bicep Curl",
  pullup: "Pull-Up", lateral_raise: "Lateral Raise", overhead_press: "Overhead Press",
  situp: "Sit-Up", crunch: "Crunch", leg_raise: "Leg Raise",
  knee_raise: "Knee Raise", knee_press: "Knee Press",
};

const BASE_MET = {
  "Squat": 5.5, "Push-Up": 8.0, "Bicep Curl": 3.0, "Pull-Up": 9.0,
  "Lateral Raise": 3.0, "Overhead Press": 4.5, "Sit-Up": 4.0,
  "Crunch": 3.8, "Leg Raise": 3.5, "Knee Raise": 3.5, "Knee Press": 4.0,
};

// Track rep timestamps for set_time calculation
let _repTimestamps = [];  // seconds (Date.now()/1000) when each rep was counted
let _lastRepCount  = 0;

// Fetch user body weight from profile (cached)
let _bodyWeightKg = null;
async function getBodyWeight() {
  if (_bodyWeightKg !== null) return _bodyWeightKg;
  try {
    const profile = await Profile.get();
    _bodyWeightKg = profile.weight_kg || 70;
  } catch (_) { _bodyWeightKg = 70; }
  return _bodyWeightKg;
}

function calcCalories(displayName, reps, setTimeSec, bodyWeightKg, liftedKg) {
  if (bodyWeightKg <= 0 || setTimeSec <= 0) return 0;
  const base = BASE_MET[displayName] || 4.0;
  const adj  = base * (1 + (liftedKg / bodyWeightKg) * 0.2);
  return Math.round(adj * bodyWeightKg * (setTimeSec / 3600) * 10) / 10;
}

// ── Observe rep counter ───────────────────────────────────────────────────────
const repCountEl = document.getElementById("rep-count");
const repObserver = new MutationObserver(() => {
  const reps = parseInt(repCountEl.textContent || "0", 10);
  // Record timestamp whenever rep count increases
  if (reps > _lastRepCount) {
    _repTimestamps.push(Date.now() / 1000);
    _lastRepCount = reps;
  }
  updateSaveBtn(reps);
});
if (repCountEl) repObserver.observe(repCountEl, { childList: true, subtree: true, characterData: true });

function updateSaveBtn(reps) {
  if (reps > 0) {
    saveBtn.disabled = false;
    const w = getWeight();
    saveHint.textContent = w > 0
      ? `${reps} reps · ${(reps * w).toFixed(1)} kg volume`
      : `${reps} rep${reps !== 1 ? "s" : ""} ready to save`;
  } else {
    saveBtn.disabled = true;
    saveHint.textContent = "Complete some reps first";
  }
}

function getWeight() {
  const el = document.getElementById("weight-input");
  return el ? parseFloat(el.value) || 0 : 0;
}

// Update hint whenever weight changes
const weightInputEl = document.getElementById("weight-input");
if (weightInputEl) {
  weightInputEl.addEventListener("input", () => {
    const reps = parseInt(repCountEl?.textContent || "0", 10);
    updateSaveBtn(reps);
  });
}

// ── Save Set button click ─────────────────────────────────────────────────────
if (saveBtn) {
  saveBtn.addEventListener("click", async () => {
    const reps     = parseInt(repCountEl.textContent || "0", 10);
    const slug     = document.getElementById("exercise-select")?.value || "unknown";
    const exercise = EXERCISE_DISPLAY_MAP[slug] || slug;
    const weight   = getWeight();
    if (reps <= 0) return;

    // Compute set time from rep timestamps
    let setTimeSec = 0;
    if (_repTimestamps.length >= 2) {
      setTimeSec = _repTimestamps[_repTimestamps.length - 1] - _repTimestamps[0];
    } else if (_repTimestamps.length === 1) {
      setTimeSec = reps * 3;  // fallback: ~3s per rep
    }
    const bodyWeight = await getBodyWeight();
    const calories   = calcCalories(exercise, reps, setTimeSec, bodyWeight, weight);

    saveBtn.disabled    = true;
    saveBtn.textContent = "Saving…";
    try {
      await Workout.save(exercise, reps, 1, null,
        weight > 0 ? weight : null,
        calories > 0 ? calories : null);
      const volStr = weight > 0 ? ` · ${(reps * weight).toFixed(1)} kg volume` : "";
      const calStr = calories > 0 ? ` · ~${calories.toFixed(1)} kcal` : "";
      showToast(`✅ Saved ${reps} reps of ${exercise}${volStr}${calStr}`);
      // Reset rep timestamp tracker
      _repTimestamps = [];
      _lastRepCount  = 0;
      const resetBtn = document.getElementById("btn-reset");
      if (resetBtn) resetBtn.click();
    } catch (err) {
      showToast(`⚠️ ${err.message}`, true);
    } finally {
      saveBtn.disabled    = false;
      saveBtn.textContent = "✅ Save Set";
      saveHint.textContent = "Complete some reps first";
    }
  });
}

function showToast(msg, isError = false) {
  const t = document.getElementById("save-toast");
  t.textContent = msg;
  t.style.background = isError ? "#ef4444" : "#10b981";
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3500);
}
