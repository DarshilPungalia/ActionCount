/**
 * plan_loader.js — PlanLoader Module
 * ------------------------------------
 * Fetches today's weekly workout plan, builds an ordered set queue,
 * auto-selects exercise, auto-fills weight, and orchestrates automatic
 * exercise progression with the RestTimer.
 *
 * Auto-plan flow (when plan is active):
 *   1. init() loads plan → auto-starts camera for first set
 *   2. User does reps
 *   3. User stops camera (or Save Set is clicked which stops camera)
 *      → rest timer starts automatically (2 min)
 *   4. During rest: user may save manually via button/voice → markSaved()
 *   5. Timer expires:
 *      - If not saved yet AND reps > 0 → auto-save silently
 *      - Then advance queue + auto-start camera for next set
 *
 * API:
 *   PlanLoader.init()           — fetch plan, build queue, render banner
 *   PlanLoader.onSetSaved(reps) — called after a successful API save
 *   PlanLoader.markSaved()      — marks current set as saved (no-op if already)
 *   PlanLoader.isSaved()        — true if current set has been saved
 *   PlanLoader.getCurrentItem() — current queue item or null
 *   PlanLoader.isActive()       — true if plan loaded for today
 *
 * Depends on: api.js, rest_timer.js
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
  let _queue        = [];
  let _currentIdx   = -1;
  let _weekday      = '';
  let _active       = false;
  let _bannerEl     = null;
  let _weightManuallyChanged = false;

  // Auto-plan autopilot state
  let _pendingSave     = false;  // true once current set has been saved
  let _timerRunning    = false;  // true while RestTimer is active
  let _repsSnapshot    = 0;      // rep count captured when camera stops
  let _autoSaving      = false;  // true during programmatic auto-save (blocks re-entry)

  // ── Build queue ──────────────────────────────────────────────────────────────
  function _buildQueue(exercises) {
    _queue = [];
    const totalExercises = exercises.length;
    exercises.forEach((ex, exerciseIndex) => {
      const label = DISPLAY[ex.exercise_key] || ex.exercise_key;
      for (let s = 1; s <= (ex.sets || 1); s++) {
        _queue.push({
          exercise_key:   ex.exercise_key,
          targetReps:     ex.reps     || 0,
          weightKg:       ex.weight_kg || 0,
          setIndex:       s,
          totalSets:      ex.sets || 1,
          exerciseLabel:  label,
          exerciseIndex:  exerciseIndex + 1,
          totalExercises,
        });
      }
    });
  }

  // ── Apply current item to UI ─────────────────────────────────────────────────
  function _applyCurrentItem() {
    const item = getCurrentItem();
    if (!item) return;

    const sel = document.getElementById('exercise-select');
    if (sel && sel.value !== item.exercise_key) {
      sel.value = item.exercise_key;
      sel.dispatchEvent(new Event('change'));
    }

    const wEl = document.getElementById('weight-input');
    if (wEl && !_weightManuallyChanged) {
      wEl.value = item.weightKg > 0 ? item.weightKg : '';
    }

    _renderBanner();
  }

  // ── Auto-start camera ────────────────────────────────────────────────────────
  function _autoStart() {
    setTimeout(() => {
      const startBtn = document.getElementById('btn-start-camera');
      if (startBtn && !startBtn.disabled) startBtn.click();
    }, 400);
  }

  // ── Reset per-set state ──────────────────────────────────────────────────────
  function _resetSetState() {
    _pendingSave  = false;
    _timerRunning = false;
    _repsSnapshot = 0;
  }

  // ── Get live rep count from DOM ──────────────────────────────────────────────
  function _getLiveReps() {
    const el = document.getElementById('rep-count');
    return parseInt(el?.textContent || '0', 10);
  }

  // ── Camera-stop listener ─────────────────────────────────────────────────────
  // Attached once in init(). Fires whenever the Stop button is clicked.
  function _monitorCameraStop() {
    const stopBtn = document.getElementById('btn-stop-camera');
    if (!stopBtn) return;

    stopBtn.addEventListener('click', () => {
      // Ignore if plan not active, timer already running, or auto-save in progress
      if (!_active || _timerRunning || _autoSaving) return;

      // Snapshot reps at camera-stop time
      _repsSnapshot = _getLiveReps();
      _timerRunning = true;

      // Small delay so live.js can process the stop first
      setTimeout(_startRestTimer, 150);
    });
  }

  // ── Start rest timer ─────────────────────────────────────────────────────────
  function _startRestTimer() {
    const isLast = _currentIdx >= _queue.length - 1;

    // If already saved and this is the last set, workout is complete
    if (_pendingSave && isLast) {
      _timerRunning = false;
      _renderBanner();
      if (window.showToast) window.showToast('🎉 Workout complete! Amazing work!');
      return;
    }

    RestTimer.start(
      RestTimer.DEFAULT_SECONDS,
      _onTimerComplete,
      _nextLabel(),
    );
  }

  // ── Timer complete callback ──────────────────────────────────────────────────
  async function _onTimerComplete() {
    _timerRunning = false;

    // Auto-save if user didn't explicitly save and there are reps to save
    if (!_pendingSave && _repsSnapshot > 0) {
      if (typeof window.saveSet === 'function') {
        _autoSaving = true;   // block camera-stop listener during auto-save
        try {
          await window.saveSet(_repsSnapshot, /*silent=*/true);
          // saveSet → markSaved() + onSetSaved() → stops camera + advances
          // onSetSaved() detects _autoSaving and skips re-starting a timer
        } finally {
          _autoSaving = false;
        }
        return;   // onSetSaved handles the advance + camera restart
      }
    }

    // Already saved (onSetSaved already incremented _currentIdx) or 0 reps
    if (!_pendingSave) {
      // 0 reps — just advance without saving
      _advance();
    }
    _applyCurrentItem();
    _resetSetState();
    _autoStart();
  }

  // ── Advance queue index ──────────────────────────────────────────────────────
  function _advance() {
    const prev = getCurrentItem();
    _currentIdx++;
    const next = getCurrentItem();
    if (prev && next && next.exercise_key !== prev.exercise_key) {
      _weightManuallyChanged = false;
    }
  }

  // ── Next set label for rest timer ────────────────────────────────────────────
  function _nextLabel() {
    const nextIdx = _currentIdx + (_pendingSave ? 0 : 1);
    const next    = _queue[nextIdx];
    if (!next) return '🎉 Last set — finish strong!';
    const weightStr = next.weightKg > 0 ? `  ·  ${next.weightKg} kg` : '';
    return `Next: <strong>${next.exerciseLabel}</strong>  ·  Set ${next.setIndex}/${next.totalSets}  ·  ${next.targetReps} reps${weightStr}`;
  }

  // ── Banner DOM ───────────────────────────────────────────────────────────────
  function _buildBanner() {
    if (_bannerEl) return;
    _bannerEl = document.createElement('div');
    _bannerEl.id = 'plan-banner';
    Object.assign(_bannerEl.style, {
      position:       'fixed',
      top:            '58px',
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
    const item    = getCurrentItem();
    const titleEl = document.getElementById('plan-banner-title');
    const bodyEl  = document.getElementById('plan-banner-body');
    const subEl   = document.getElementById('plan-banner-sub');

    if (!item) {
      if (titleEl) titleEl.textContent = _weekday + ' Plan';
      if (bodyEl)  bodyEl.textContent  = '✅ Workout Complete!';
      if (subEl)   subEl.textContent   = 'Great job today!';
      _bannerEl.style.display = 'flex';
      return;
    }

    if (titleEl) titleEl.textContent = _weekday + ' Plan';
    if (bodyEl)  bodyEl.textContent  = `Exercise ${item.exerciseIndex}/${item.totalExercises}: ${item.exerciseLabel}`;
    if (subEl) {
      const weightStr = item.weightKg > 0 ? `  ·  ${item.weightKg} kg` : '';
      subEl.textContent = `Set ${item.setIndex}/${item.totalSets}  ·  Target: ${item.targetReps} reps${weightStr}`;
    }
    _bannerEl.style.display = 'flex';
  }

  // ── Weight input watcher ─────────────────────────────────────────────────────
  function _watchWeightInput() {
    const wEl = document.getElementById('weight-input');
    if (!wEl) return;
    wEl.addEventListener('input', () => { _weightManuallyChanged = true; });
  }

  // ── Public: onSetSaved — called by tracker.js after successful Workout.save() ─
  function onSetSaved(reps) {
    if (!_active) return;
    _pendingSave = true;

    // Advance queue index
    _advance();

    const isLast = _currentIdx >= _queue.length;

    if (_autoSaving) {
      // Camera is already stopped. Skip the stop click so we don't re-trigger
      // the camera-stop listener. _onTimerComplete will handle restart.
      if (isLast) {
        _resetSetState();
        _renderBanner();  // shows "Workout Complete!"
        if (window.showToast) window.showToast('\uD83C\uDF89 Workout complete! Amazing work!');
        return;
      }
      _renderBanner();
      return;
    }

    // Normal flow (user-triggered save): stop camera → listener starts rest timer
    const stopBtn = document.getElementById('btn-stop-camera');
    if (stopBtn && !stopBtn.hidden) stopBtn.click();

    if (isLast) return;   // camera-stop listener handles the complete state

    _renderBanner();
  }

  // ── Public: markSaved ────────────────────────────────────────────────────────
  function markSaved() {
    _pendingSave = true;
  }

  // ── Public: isSaved ─────────────────────────────────────────────────────────
  function isSaved() {
    return _pendingSave;
  }

  // ── init ─────────────────────────────────────────────────────────────────────
  async function init() {
    _buildBanner();
    _watchWeightInput();
    _monitorCameraStop();

    let data;
    try {
      data = await Plan.today();
    } catch (err) {
      console.info('[PlanLoader] No plan for today (or fetch failed):', err.message);
      return;
    }

    if (!data.has_plan || !data.exercises || data.exercises.length === 0) {
      console.info('[PlanLoader] No plan set for today — manual mode.');
      return;
    }

    _weekday    = data.weekday;
    _buildQueue(data.exercises);
    _currentIdx = 0;
    _active     = true;
    _resetSetState();

    console.info(`[PlanLoader] Loaded ${_weekday} plan: ${_queue.length} sets across ${data.exercises.length} exercises.`);

    _applyCurrentItem();
    _autoStart();
  }

  // ── Public: getCurrentItem ───────────────────────────────────────────────────
  function getCurrentItem() {
    if (_currentIdx < 0 || _currentIdx >= _queue.length) return null;
    return _queue[_currentIdx];
  }

  function isActive() { return _active; }

  return { init, onSetSaved, markSaved, isSaved, getCurrentItem, isActive };

})();
