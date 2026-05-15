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

// Auto-save guard — prevents double-fire when target is hit
let _autoSaveFired = false;

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

// ── Auto-save hook: fires on every updateHUD call (same pattern as overlay.js) ─
// Hooks into updateHUD AFTER DOMContentLoaded so overlay.js's patch is already in
// place. Checks the raw counter value from the backend — no DOM/lerp race condition.
document.addEventListener('DOMContentLoaded', () => {
  const _origHUD = typeof updateHUD === 'function' ? updateHUD : null;
  if (!_origHUD) return;

  // Only patch once (idempotent guard)
  if (updateHUD._autoSavePatched) return;

  const _patchedHUD = function (data) {
    _origHUD(data);

    // ── Check target reps ───────────────────────────────────────────────────
    const count = data.counter ?? data.count ?? 0;
    if (
      !_autoSaveFired
      && count > 0
      && window.PlanLoader
      && PlanLoader.isActive()
      && !PlanLoader.isSaved()
    ) {
      const item = PlanLoader.getCurrentItem();
      if (item && item.targetReps > 0 && count >= item.targetReps) {
        _autoSaveFired = true;
        console.log(
          `[PlanLoader] Target reached: ${count}/${item.targetReps} reps — auto-saving set`
        );
        // 350 ms: lets the rep animation complete before stop-camera fires
        setTimeout(() => saveSet(), 350);
      }
    }
  };
  _patchedHUD._autoSavePatched = true;
  _patchedHUD._hudPatched = updateHUD._hudPatched;  // preserve overlay.js flag
  // eslint-disable-next-line no-global-assign
  updateHUD = _patchedHUD;
});

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

// ── Smart Auto-Fill — last used weight per exercise ───────────────────────────
const AUTOFILL_KEY = 'ac_last_weight';

function loadAutoFill(slug) {
  try {
    const store = JSON.parse(localStorage.getItem(AUTOFILL_KEY) || '{}');
    const w = store[slug];
    const weightEl = document.getElementById('weight-input');
    if (weightEl && w != null && w > 0) {
      weightEl.value = w;
      // Brief green flash to signal auto-fill
      weightEl.style.transition = 'box-shadow 0.3s';
      weightEl.style.boxShadow  = '0 0 0 2px rgba(16,185,129,0.6)';
      setTimeout(() => { weightEl.style.boxShadow = ''; }, 1200);
      const reps = parseInt(document.getElementById('rep-count')?.textContent || '0', 10);
      updateSaveBtn(reps);
    }
  } catch (_) {}
}

function saveAutoFill(slug, weight) {
  if (weight <= 0) return;
  try {
    const store = JSON.parse(localStorage.getItem(AUTOFILL_KEY) || '{}');
    store[slug] = weight;
    localStorage.setItem(AUTOFILL_KEY, JSON.stringify(store));
  } catch (_) {}
}

// Pre-fill on page load for the currently selected exercise
document.addEventListener('DOMContentLoaded', () => {
  const exSelect = document.getElementById('exercise-select');
  if (exSelect) loadAutoFill(exSelect.value);
});

// Update hint whenever weight changes
const weightInputEl = document.getElementById('weight-input');
if (weightInputEl) {
  weightInputEl.addEventListener('input', () => {
    const reps = parseInt(repCountEl?.textContent || '0', 10);
    updateSaveBtn(reps);
  });
}

// Auto-fill when exercise changes
const exerciseSelectEl = document.getElementById('exercise-select');
if (exerciseSelectEl) {
  exerciseSelectEl.addEventListener('change', () => {
    loadAutoFill(exerciseSelectEl.value);
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

    // Reset rep timestamps AND the auto-save guard for the next set
    _repTimestamps = [];
    _lastRepCount  = 0;
    _autoSaveFired = false;

    // Persist last used weight for this exercise (auto-fill next time)
    saveAutoFill(slug, weight);

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

// ── Stop Set — ends the current set + starts rest timer ──────────────────────
/**
 * Voice command: "stop set" / "end this set" / "finish set"
 *
 * - Clicks the Stop Camera button, which the PlanLoader's camera-stop listener
 *   is already monitoring. That listener snapshots reps and kicks off the rest
 *   timer → auto-advance → auto-start camera after rest.
 * - If no plan is active (manual mode), just stops the camera so the user can
 *   rest before clicking Start again manually.
 * - Guard: if no reps have been done yet, warn but still stop (unlike PlanLoader's
 *   strict 0-rep block on the stop button itself — voice users should be able to
 *   abort a set they haven't started).
 */
function stopSet() {
  const stopBtn = document.getElementById('btn-stop-camera');
  if (!stopBtn || stopBtn.hidden) {
    showToast('⚠️ Camera is not running — nothing to stop.', true);
    return;
  }
  // Click the stop button. The PlanLoader camera-stop listener fires automatically
  // and handles the 0-rep guard + rest timer start.
  stopBtn.click();
}

window.stopSet = stopSet;


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
