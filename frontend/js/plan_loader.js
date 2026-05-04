/**
 * plan_loader.js — PlanLoader Module
 * ------------------------------------
 * Fetches today's weekly workout plan, builds an ordered set queue,
 * auto-selects the exercise, auto-fills the weight input, and orchestrates
 * automatic exercise progression with the RestTimer.
 *
 * API:
 *   PlanLoader.init()              — fetch plan, build queue, render banner
 *   PlanLoader.onSetSaved(reps)    — advance queue, start rest timer
 *   PlanLoader.getCurrentItem()    — {exercise_key, targetReps, weightKg, setIndex, totalSets, ...}
 *   PlanLoader.isActive()          — true if a plan was loaded for today
 *
 * Depends on: api.js (Plan.today), rest_timer.js (RestTimer), live.js (LiveModule)
 * Must be loaded AFTER all of those scripts.
 */

'use strict';

const PlanLoader = (() => {

  // ── Exercise display labels ──────────────────────────────────────────────────
  const DISPLAY = {
    squat:          'Squat',
    pushup:         'Push-up',
    bicep_curl:     'Bicep Curl',
    pullup:         'Pull-up',
    lateral_raise:  'Lateral Raise',
    overhead_press: 'Overhead Press',
    situp:          'Sit-up',
    crunch:         'Crunch',
    leg_raise:      'Leg Raise',
    knee_raise:     'Knee Raise',
    knee_press:     'Knee Press',
  };

  // ── State ────────────────────────────────────────────────────────────────────
  let _queue        = [];    // flat list of {exercise_key, targetReps, weightKg, setIndex, totalSets, exerciseLabel, exerciseIndex, totalExercises}
  let _currentIdx   = -1;   // index into _queue
  let _weekday      = '';
  let _active       = false; // true after successful plan load
  let _bannerEl     = null;
  let _weightManuallyChanged = false;   // user touched weight input manually

  // ── Build queue from plan exercises ─────────────────────────────────────────
  function _buildQueue(exercises) {
    _queue = [];
    const totalExercises = exercises.length;
    exercises.forEach((ex, exerciseIndex) => {
      const label = DISPLAY[ex.exercise_key] || ex.exercise_key;
      for (let s = 1; s <= (ex.sets || 1); s++) {
        _queue.push({
          exercise_key:    ex.exercise_key,
          targetReps:      ex.reps    || 0,
          weightKg:        ex.weight_kg || 0,
          setIndex:        s,
          totalSets:       ex.sets || 1,
          exerciseLabel:   label,
          exerciseIndex:   exerciseIndex + 1,
          totalExercises,
        });
      }
    });
  }

  // ── Update the exercise select + weight input for current queue item ─────────
  function _applyCurrentItem() {
    const item = getCurrentItem();
    if (!item) return;

    const sel = document.getElementById('exercise-select');
    if (sel && sel.value !== item.exercise_key) {
      sel.value = item.exercise_key;
      sel.dispatchEvent(new Event('change'));
    }

    // Auto-fill weight — but only if user hasn't manually overridden it
    const wEl = document.getElementById('weight-input');
    if (wEl && !_weightManuallyChanged) {
      wEl.value = item.weightKg > 0 ? item.weightKg : '';
    }

    _renderBanner();
  }

  // ── Banner DOM ───────────────────────────────────────────────────────────────
  function _buildBanner() {
    if (_bannerEl) return;
    _bannerEl = document.createElement('div');
    _bannerEl.id = 'plan-banner';
    Object.assign(_bannerEl.style, {
      position:       'fixed',
      top:            '58px',      // below the HUD clock
      left:           '16px',
      zIndex:         '65',
      display:        'none',
      flexDirection:  'column',
      gap:            '3px',
      background:     'rgba(10,14,26,0.78)',
      backdropFilter: 'blur(12px)',
      border:         '1px solid rgba(99,102,241,0.22)',
      borderRadius:   '10px',
      padding:        '10px 14px',
      fontFamily:     '\'Inter\', sans-serif',
      pointerEvents:  'none',
      userSelect:     'none',
      maxWidth:       '260px',
    });

    const planTitle = document.createElement('div');
    planTitle.id = 'plan-banner-title';
    Object.assign(planTitle.style, {
      fontSize:      '9px',
      fontWeight:    '700',
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color:         'rgba(165,180,252,0.65)',
    });

    const planBody = document.createElement('div');
    planBody.id = 'plan-banner-body';
    Object.assign(planBody.style, {
      fontSize:   '13px',
      fontWeight: '700',
      color:      'rgba(255,255,255,0.9)',
    });

    const planSub = document.createElement('div');
    planSub.id = 'plan-banner-sub';
    Object.assign(planSub.style, {
      fontSize:   '11px',
      fontWeight: '500',
      color:      'rgba(148,163,184,0.75)',
      marginTop:  '1px',
    });

    _bannerEl.appendChild(planTitle);
    _bannerEl.appendChild(planBody);
    _bannerEl.appendChild(planSub);
    document.body.appendChild(_bannerEl);
  }

  function _renderBanner() {
    if (!_bannerEl) return;
    const item = getCurrentItem();
    const titleEl = document.getElementById('plan-banner-title');
    const bodyEl  = document.getElementById('plan-banner-body');
    const subEl   = document.getElementById('plan-banner-sub');

    if (!item) {
      // Workout complete!
      if (titleEl) titleEl.textContent = _weekday + ' Plan';
      if (bodyEl)  bodyEl.textContent  = '\u2705 Workout Complete!';
      if (subEl)   subEl.textContent   = 'Great job today!';
      _bannerEl.style.display = 'flex';
      return;
    }

    if (titleEl) titleEl.textContent = _weekday + ' Plan';
    if (bodyEl) {
      bodyEl.textContent = `Exercise ${item.exerciseIndex}/${item.totalExercises}: ${item.exerciseLabel}`;
    }
    if (subEl) {
      const weightStr = item.weightKg > 0 ? `  \u00b7  ${item.weightKg} kg` : '';
      subEl.textContent = `Set ${item.setIndex}/${item.totalSets}  \u00b7  Target: ${item.targetReps} reps${weightStr}`;
    }
    _bannerEl.style.display = 'flex';
  }

  // ── Watch weight input for manual changes ────────────────────────────────────
  function _watchWeightInput() {
    const wEl = document.getElementById('weight-input');
    if (!wEl) return;
    wEl.addEventListener('input', () => {
      _weightManuallyChanged = true;
    });
  }

  // ── Plan item complete label for rest timer ───────────────────────────────────
  function _nextLabel() {
    const next = _queue[_currentIdx + 1];
    if (!next) return '\uD83C\uDF89 Last set done!';
    const weightStr = next.weightKg > 0 ? `  \u00b7  ${next.weightKg} kg` : '';
    return `Next: <strong>${next.exerciseLabel}</strong>  \u00b7  Set ${next.setIndex}/${next.totalSets}  \u00b7  ${next.targetReps} reps${weightStr}`;
  }

  // ── onSetSaved — advance queue, start rest timer ─────────────────────────────
  function onSetSaved() {
    if (!_active || _currentIdx >= _queue.length) return;

    _currentIdx++;

    // Reset manual weight flag when moving to a new exercise
    const prev = _queue[_currentIdx - 1];
    const next = getCurrentItem();
    if (next && prev && next.exercise_key !== prev.exercise_key) {
      _weightManuallyChanged = false;
    }

    const isLast = _currentIdx >= _queue.length;

    // Stop current camera session
    const stopBtn = document.getElementById('btn-stop-camera');
    if (stopBtn && !stopBtn.hidden) stopBtn.click();

    if (isLast) {
      _renderBanner();   // shows "Workout Complete!"
      if (window.showToast) window.showToast('\uD83C\uDF89 Workout complete! Amazing work!');
      return;
    }

    // Start rest timer → on complete, switch exercise + start camera
    RestTimer.start(
      RestTimer.DEFAULT_SECONDS,
      () => {
        // Apply next item to UI
        _applyCurrentItem();
        // Wait a tick for the select change to propagate, then start camera
        setTimeout(() => {
          const startBtn = document.getElementById('btn-start-camera');
          if (startBtn && !startBtn.disabled) startBtn.click();
        }, 200);
      },
      _nextLabel(),
    );
  }

  // ── init ─────────────────────────────────────────────────────────────────────
  async function init() {
    _buildBanner();
    _watchWeightInput();

    let data;
    try {
      data = await Plan.today();
    } catch (err) {
      // No plan or network error — silent fallback to manual mode
      console.info('[PlanLoader] No plan for today (or fetch failed):', err.message);
      return;
    }

    if (!data.has_plan || !data.exercises || data.exercises.length === 0) {
      console.info('[PlanLoader] No plan set for today — manual mode.');
      return;
    }

    _weekday = data.weekday;
    _buildQueue(data.exercises);
    _currentIdx = 0;
    _active     = true;

    console.info(`[PlanLoader] Loaded ${_weekday} plan: ${_queue.length} sets across ${data.exercises.length} exercises.`);

    _applyCurrentItem();
  }

  // ── Public ───────────────────────────────────────────────────────────────────
  function getCurrentItem() {
    if (_currentIdx < 0 || _currentIdx >= _queue.length) return null;
    return _queue[_currentIdx];
  }

  function isActive() { return _active; }

  return { init, onSetSaved, getCurrentItem, isActive };

})();
