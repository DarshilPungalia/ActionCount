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

// ── Observe rep counter ───────────────────────────────────────────────────────
const repCountEl = document.getElementById("rep-count");
const repObserver = new MutationObserver(() => {
  const reps = parseInt(repCountEl.textContent || "0", 10);
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

    saveBtn.disabled    = true;
    saveBtn.textContent = "Saving…";
    try {
      await Workout.save(exercise, reps, 1, null, weight > 0 ? weight : null);
      const volStr = weight > 0 ? ` · ${(reps * weight).toFixed(1)} kg volume` : "";
      showToast(`✅ Saved ${reps} reps of ${exercise}${volStr}`);
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
