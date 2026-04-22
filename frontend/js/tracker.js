/**
 * tracker.js
 * Save Set button integration for the live tracker page.
 * Works alongside the existing app.js WebSocket/camera logic.
 */

const saveBtn  = document.getElementById("btn-save-set");
const saveHint = document.getElementById("save-hint");
const toast    = document.getElementById("save-toast");

// ── Map exercise select value → display name sent to API ─────────────────────
const EXERCISE_DISPLAY_MAP = {
  squat:          "Squat",
  pushup:         "Push-Up",
  bicep_curl:     "Bicep Curl",
  pullup:         "Pull-Up",
  lateral_raise:  "Lateral Raise",
  overhead_press: "Overhead Press",
  situp:          "Sit-Up",
  crunch:         "Crunch",
  leg_raise:      "Leg Raise",
  knee_raise:     "Knee Raise",
  knee_press:     "Knee Press",
};

// ── Observe rep counter and enable button when reps > 0 ───────────────────────
const repCountEl = document.getElementById("rep-count");

const repObserver = new MutationObserver(() => {
  const reps = parseInt(repCountEl.textContent || "0", 10);
  if (reps > 0) {
    saveBtn.disabled = false;
    saveHint.textContent = `${reps} rep${reps !== 1 ? "s" : ""} ready to save`;
  } else {
    saveBtn.disabled = true;
    saveHint.textContent = "Complete some reps first";
  }
});

if (repCountEl) {
  repObserver.observe(repCountEl, { childList: true, subtree: true, characterData: true });
}

// ── Save Set button click ─────────────────────────────────────────────────────
if (saveBtn) {
  saveBtn.addEventListener("click", async () => {
    const reps     = parseInt(repCountEl.textContent || "0", 10);
    const selectEl = document.getElementById("exercise-select");
    const slug     = selectEl ? selectEl.value : "unknown";
    const exercise = EXERCISE_DISPLAY_MAP[slug] || slug;

    if (reps <= 0) return;

    saveBtn.disabled    = true;
    saveBtn.textContent = "Saving…";

    try {
      await Workout.save(exercise, reps, 1);

      // Flash success toast
      showToast(`✅ Saved ${reps} reps of ${exercise}`);

      // Reset the rep counter in the UI via the Reset button click
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

// ── Toast helper ──────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
  const t = document.getElementById("save-toast");
  t.textContent = msg;
  t.style.background = isError ? "#ef4444" : "#10b981";
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3000);
}
