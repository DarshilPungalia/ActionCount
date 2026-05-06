/**
 * tracker.js
 * ----------
 * Save Set logic for the live tracker page.
 *
 * Exports window.saveSet(repsOverride?, silent?) — callable from:
 *   - Save Set button click
 *   - Voice command (via dispatchFrontendCommand in index.html)
 *   - PlanLoader auto-save on timer expiry (silent=true)
 *
 * If PlanLoader is active, saveSet() calls PlanLoader.onSetSaved() which
 * handles camera stop → rest timer → auto-advance.
 * If no plan is active, falls back to manual mode (just resets the counter).
 */

const saveBtn  = document.getElementById('btn-save-set');
const saveHint = document.getElementById('save-hint');

const EXERCISE_DISPLAY_MAP = {
  squat: 'Squat', pushup: 'Push-Up', bicep_curl: 'Bicep Curl',
  pullup: 'Pull-Up', lateral_raise: 'Lateral Raise', overhead_press: 'Overhead Press',
  situp: 'Sit-Up', crunch: 'Crunch', leg_raise: 'Leg Raise',
  knee_raise: 'Knee Raise', knee_press: 'Knee Press',
};

const BASE_MET = {
  'Squat': 5.5, 'Push-Up': 8.0, 'Bicep Curl': 3.0, 'Pull-Up': 9.0,
  'Lateral Raise': 3.0, 'Overhead Press': 4.5, 'Sit-Up': 4.0,
  'Crunch': 3.8, 'Leg Raise': 3.5, 'Knee Raise': 3.5, 'Knee Press': 4.0,
};

// Track rep timestamps for set_time calculation
let _repTimestamps = [];
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
const repCountEl = document.getElementById('rep-count');
const repObserver = new MutationObserver(() => {
  const reps = parseInt(repCountEl.textContent || '0', 10);
  if (reps > _lastRepCount) {
    _repTimestamps.push(Date.now() / 1000);
    _lastRepCount = reps;
  }
  updateSaveBtn(reps);
});
if (repCountEl) repObserver.observe(repCountEl, { childList: true, subtree: true, characterData: true });

function updateSaveBtn(reps) {
  if (!saveBtn) return;
  if (reps > 0) {
    saveBtn.disabled = false;
    const w = getWeight();
    saveHint.textContent = w > 0
      ? `${reps} reps · ${(reps * w).toFixed(1)} kg volume`
      : `${reps} rep${reps !== 1 ? 's' : ''} ready to save`;
  } else {
    saveBtn.disabled = true;
    saveHint.textContent = 'Complete some reps first';
  }
}

function getWeight() {
  const el = document.getElementById('weight-input');
  return el ? parseFloat(el.value) || 0 : 0;
}

// Update hint whenever weight changes
const weightInputEl = document.getElementById('weight-input');
if (weightInputEl) {
  weightInputEl.addEventListener('input', () => {
    const reps = parseInt(repCountEl?.textContent || '0', 10);
    updateSaveBtn(reps);
  });
}

// ── Core save function ────────────────────────────────────────────────────────
/**
 * Save the current set.
 *
 * @param {number|null} repsOverride  - Use this rep count instead of reading
 *                                      from the DOM. Used by auto-save on timer
 *                                      expiry so the snapshot value is used.
 * @param {boolean}     silent        - If true, suppress the success toast.
 *                                      Used by PlanLoader auto-save.
 */
async function saveSet(repsOverride = null, silent = false) {
  const reps     = repsOverride !== null
    ? repsOverride
    : parseInt(repCountEl?.textContent || '0', 10);
  const slug     = document.getElementById('exercise-select')?.value || 'unknown';
  const exercise = EXERCISE_DISPLAY_MAP[slug] || slug;
  const weight   = getWeight();

  // Skip save if no reps (per user requirement: 0 reps → just advance)
  if (reps <= 0) {
    if (window.PlanLoader && PlanLoader.isActive()) {
      PlanLoader.markSaved();
      // _onTimerComplete in plan_loader will handle advance
    }
    return;
  }

  // Compute set time from rep timestamps
  let setTimeSec = 0;
  if (_repTimestamps.length >= 2) {
    setTimeSec = _repTimestamps[_repTimestamps.length - 1] - _repTimestamps[0];
  } else if (_repTimestamps.length === 1) {
    setTimeSec = reps * 3;
  }

  const bodyWeight = await getBodyWeight();
  const calories   = calcCalories(exercise, reps, setTimeSec, bodyWeight, weight);

  if (saveBtn) {
    saveBtn.disabled    = true;
    saveBtn.textContent = 'Saving…';
  }

  try {
    await Workout.save(
      exercise, reps, 1, null,
      weight   > 0 ? weight   : null,
      calories > 0 ? calories : null,
    );

    // Reset rep timestamps
    _repTimestamps = [];
    _lastRepCount  = 0;

    if (!silent) {
      const volStr = weight   > 0 ? ` · ${(reps * weight).toFixed(1)} kg volume` : '';
      const calStr = calories > 0 ? ` · ~${calories.toFixed(1)} kcal` : '';
      showToast(`✅ Saved ${reps} reps of ${exercise}${volStr}${calStr}`);
    }

    if (window.PlanLoader && PlanLoader.isActive()) {
      // Mark saved BEFORE onSetSaved so camera-stop listener sees _pendingSave=true
      PlanLoader.markSaved();
      PlanLoader.onSetSaved(reps);
    } else {
      // Manual mode — just reset the rep counter
      const resetBtn = document.getElementById('btn-reset');
      if (resetBtn) resetBtn.click();
    }
  } catch (err) {
    if (!silent) showToast(`⚠️ ${err.message}`, true);
    else console.warn('[tracker] auto-save failed:', err.message);
  } finally {
    if (saveBtn) {
      saveBtn.disabled    = false;
      saveBtn.textContent = '✅ Save Set';
    }
    if (saveHint) saveHint.textContent = 'Complete some reps first';
  }
}

// Expose globally — PlanLoader and voice command dispatcher need this
window.saveSet = saveSet;

// ── Save Set button click ─────────────────────────────────────────────────────
if (saveBtn) {
  saveBtn.addEventListener('click', () => saveSet());
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
  const t = document.getElementById('save-toast');
  if (!t) return;
  t.textContent      = msg;
  t.style.background = isError ? '#ef4444' : '#10b981';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

// Expose globally so PlanLoader can call it
window.showToast = showToast;
