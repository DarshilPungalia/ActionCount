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
      // Show 0 explicitly (not blank) so user sees the plan's target weight
      wEl.value = item.weightKg >= 0 ? item.weightKg : '';
      wEl.dispatchEvent(new Event('input'));
    }

    _renderBanner();
  }

  // ── Auto-start camera ────────────────────────────────────────────────────────
  function _autoStart() {
    // 800ms: gives live.js time to wire up the exercise-change handler
    // after _applyCurrentItem() dispatches the 'change' event on the select
    setTimeout(() => {
      const startBtn = document.getElementById('btn-start-camera');
      if (startBtn && !startBtn.disabled) startBtn.click();
    }, 800);
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

      // Block stopping the set with 0 reps — force user to actually do the exercise
      const repsNow = _getLiveReps();
      if (repsNow === 0) {
        if (window.showToast) window.showToast('⚠️ Do at least 1 rep before finishing the set!', true);
        return;  // do NOT stop camera or start rest timer
      }

      // Snapshot reps at camera-stop time
      _repsSnapshot = repsNow;
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
        _autoSaving = true;
        try {
          await window.saveSet(_repsSnapshot, /*silent=*/true);
          // saveSet → markSaved() (_pendingSave=true) + onSetSaved() (_advance())
          // onSetSaved skips the camera-stop click because _autoSaving=true
        } finally {
          _autoSaving = false;
        }
        // Fall through — _applyCurrentItem + _autoStart below handle restart
      }
    }

    // Check if all sets are now done (last set was just saved/skipped)
    if (_currentIdx >= _queue.length) {
      _renderBanner();
      if (window.showToast) window.showToast('🎉 Workout complete! Amazing work!');
      return;
    }

    // Advance queue if this set had 0 reps (no save happened)
    if (!_pendingSave) {
      _advance();
    }

    // Guard again after advance
    if (_currentIdx >= _queue.length) {
      _renderBanner();
      if (window.showToast) window.showToast('🎉 Workout complete! Amazing work!');
      return;
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
  let _dropdownOpen = false;

  function _buildBanner() {
    if (_bannerEl) return;

    // ── Outer wrapper (pill-like banner) ─────────────────────────────────────
    _bannerEl = document.createElement('div');
    _bannerEl.id = 'plan-banner';
    Object.assign(_bannerEl.style, {
      position:        'fixed',
      top:             '16px',
      left:            '50%',
      transform:       'translateX(-50%)',
      zIndex:          '65',
      display:         'none',
      flexDirection:   'column',
      alignItems:      'stretch',
      gap:             '0',
      background:      'rgba(10,14,26,0.88)',
      backdropFilter:  'blur(18px)',
      border:          '1px solid rgba(99,102,241,0.30)',
      borderRadius:    '14px',
      padding:         '0',
      fontFamily:      '\'Inter\', sans-serif',
      pointerEvents:   'auto',            // ← clickable now
      userSelect:      'none',
      minWidth:        '240px',
      maxWidth:        '360px',
      textAlign:       'center',
      boxShadow:       '0 6px 28px rgba(99,102,241,0.18)',
      cursor:          'pointer',
      overflow:        'hidden',
    });

    // ── Clickable header row ──────────────────────────────────────────────────
    const headerEl = document.createElement('div');
    headerEl.id = 'plan-banner-header';
    Object.assign(headerEl.style, {
      display:         'flex',
      flexDirection:   'column',
      alignItems:      'center',
      gap:             '2px',
      padding:         '9px 18px 8px',
    });

    const planTitle = document.createElement('div');
    planTitle.id = 'plan-banner-title';
    Object.assign(planTitle.style, {
      fontSize:      '9px',
      fontWeight:    '700',
      letterSpacing: '0.13em',
      textTransform: 'uppercase',
      color:         'rgba(165,180,252,0.65)',
    });

    const planBody = document.createElement('div');
    planBody.id = 'plan-banner-body';
    Object.assign(planBody.style, {
      fontSize:   '13px',
      fontWeight: '700',
      color:      'rgba(255,255,255,0.92)',
    });

    const planSub = document.createElement('div');
    planSub.id = 'plan-banner-sub';
    Object.assign(planSub.style, {
      fontSize:   '11px',
      fontWeight: '500',
      color:      'rgba(148,163,184,0.75)',
      marginTop:  '1px',
    });

    // Chevron hint
    const chevronEl = document.createElement('div');
    chevronEl.id = 'plan-banner-chevron';
    Object.assign(chevronEl.style, {
      fontSize:        '9px',
      color:           'rgba(99,102,241,0.55)',
      marginTop:       '4px',
      letterSpacing:   '0.05em',
      transition:      'transform 0.25s',
    });
    chevronEl.textContent = '▼ tap for full plan';

    headerEl.appendChild(planTitle);
    headerEl.appendChild(planBody);
    headerEl.appendChild(planSub);
    headerEl.appendChild(chevronEl);

    // ── Dropdown panel ────────────────────────────────────────────────────────
    const dropEl = document.createElement('div');
    dropEl.id = 'plan-banner-drop';
    Object.assign(dropEl.style, {
      maxHeight:        '0',
      overflow:         'hidden',
      transition:       'max-height 0.32s cubic-bezier(0.4,0,0.2,1), opacity 0.25s',
      opacity:          '0',
      borderTop:        '0px solid rgba(99,102,241,0.15)',
    });

    const dropInner = document.createElement('div');
    dropInner.id = 'plan-banner-drop-inner';
    Object.assign(dropInner.style, {
      padding:    '8px 12px 12px',
      display:    'flex',
      flexDirection: 'column',
      gap:        '5px',
    });

    dropEl.appendChild(dropInner);

    _bannerEl.appendChild(headerEl);
    _bannerEl.appendChild(dropEl);
    document.body.appendChild(_bannerEl);

    // ── Toggle handler ────────────────────────────────────────────────────────
    _bannerEl.addEventListener('click', () => {
      _dropdownOpen = !_dropdownOpen;
      const chevron = document.getElementById('plan-banner-chevron');
      if (_dropdownOpen) {
        dropEl.style.maxHeight     = '320px';
        dropEl.style.opacity       = '1';
        dropEl.style.borderTopWidth = '1px';
        if (chevron) {
          chevron.textContent = '▲ collapse';
          chevron.style.color = 'rgba(165,180,252,0.7)';
        }
        _renderDropdown();
      } else {
        dropEl.style.maxHeight     = '0';
        dropEl.style.opacity       = '0';
        dropEl.style.borderTopWidth = '0px';
        if (chevron) {
          chevron.textContent = '▼ tap for full plan';
          chevron.style.color = 'rgba(99,102,241,0.55)';
        }
      }
    });
  }

  // ── Dropdown content ──────────────────────────────────────────────────────────
  const EXERCISE_EMOJIS = {
    squat:'🦵', pushup:'💪', bicep_curl:'🏋️', pullup:'🤸',
    lateral_raise:'↔️', overhead_press:'⬆️', situp:'🧘',
    crunch:'⚡', leg_raise:'🦶', knee_raise:'🦵', knee_press:'🔽',
  };

  function _renderDropdown() {
    const inner = document.getElementById('plan-banner-drop-inner');
    if (!inner) return;
    inner.innerHTML = '';

    // Label row
    const label = document.createElement('div');
    Object.assign(label.style, {
      fontSize:      '9px',
      fontWeight:    '700',
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color:         'rgba(99,102,241,0.6)',
      marginBottom:  '4px',
      textAlign:     'left',
    });
    label.textContent = 'Remaining Sets';
    inner.appendChild(label);

    if (_currentIdx >= _queue.length) {
      const done = document.createElement('div');
      done.style.cssText = 'font-size:12px;color:rgba(52,211,153,0.9);text-align:center;padding:8px 0;';
      done.textContent = '🎉 All sets complete!';
      inner.appendChild(done);
      return;
    }

    // Render from currentIdx onward — group by exercise
    let lastKey = null;
    for (let i = _currentIdx; i < _queue.length; i++) {
      const q   = _queue[i];
      const isCurrent = i === _currentIdx;

      const row = document.createElement('div');
      Object.assign(row.style, {
        display:         'flex',
        alignItems:      'center',
        gap:             '8px',
        padding:         '5px 8px',
        borderRadius:    '8px',
        background:      isCurrent
          ? 'rgba(99,102,241,0.18)'
          : 'rgba(255,255,255,0.03)',
        border:          isCurrent
          ? '1px solid rgba(99,102,241,0.35)'
          : '1px solid rgba(255,255,255,0.05)',
        transition:      'background 0.15s',
      });

      // Emoji
      const emojiEl = document.createElement('span');
      emojiEl.style.cssText = 'font-size:14px;flex-shrink:0;';
      emojiEl.textContent = EXERCISE_EMOJIS[q.exercise_key] || '🏋️';

      // Info block
      const info = document.createElement('div');
      info.style.cssText = 'flex:1;min-width:0;text-align:left;';

      const nameLine = document.createElement('div');
      Object.assign(nameLine.style, {
        fontSize:   '11px',
        fontWeight: '700',
        color:      isCurrent ? 'rgba(165,180,252,0.95)' : 'rgba(255,255,255,0.75)',
        whiteSpace: 'nowrap',
        overflow:   'hidden',
        textOverflow: 'ellipsis',
      });
      nameLine.textContent = (isCurrent ? '▶ ' : '') + q.exerciseLabel;

      const metaLine = document.createElement('div');
      metaLine.style.cssText = 'font-size:9.5px;color:rgba(100,116,139,0.9);margin-top:1px;';
      const wt = q.weightKg > 0 ? ` · ${q.weightKg} kg` : '';
      metaLine.textContent = `Set ${q.setIndex}/${q.totalSets} · ${q.targetReps} reps${wt}`;

      info.appendChild(nameLine);
      info.appendChild(metaLine);

      // Set badge
      const badge = document.createElement('div');
      Object.assign(badge.style, {
        fontSize:      '9px',
        fontWeight:    '700',
        padding:       '2px 6px',
        borderRadius:  '999px',
        background:    isCurrent ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.06)',
        color:         isCurrent ? '#a5b4fc' : 'rgba(100,116,139,0.8)',
        flexShrink:    '0',
      });
      badge.textContent = `${q.exerciseIndex}/${q.totalExercises}`;

      row.appendChild(emojiEl);
      row.appendChild(info);
      row.appendChild(badge);
      inner.appendChild(row);

      lastKey = q.exercise_key;
    }
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
      if (_dropdownOpen) _renderDropdown();
      return;
    }

    if (titleEl) titleEl.textContent = _weekday + ' Plan';
    if (bodyEl)  bodyEl.textContent  = `Exercise ${item.exerciseIndex}/${item.totalExercises}: ${item.exerciseLabel}`;
    if (subEl) {
      const weightStr = item.weightKg > 0 ? `  ·  ${item.weightKg} kg` : '';
      subEl.textContent = `Set ${item.setIndex}/${item.totalSets}  ·  Target: ${item.targetReps} reps${weightStr}`;
    }
    _bannerEl.style.display = 'flex';

    // Refresh dropdown content if open
    if (_dropdownOpen) _renderDropdown();
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

    // Fetch plan + today's progress in parallel
    let data, progressData;
    try {
      [data, progressData] = await Promise.all([
        Plan.today(),
        Plan.progress().catch(() => ({ progress: {} })),  // non-fatal
      ]);
    } catch (err) {
      console.info('[PlanLoader] No plan for today (or fetch failed):', err.message);
      return;   // manual mode
    }

    if (!data.has_plan || !data.exercises || data.exercises.length === 0) {
      console.info('[PlanLoader] No plan set for today — manual mode.');
      return;
    }

    _weekday = data.weekday;
    _buildQueue(data.exercises);
    _active  = true;
    _resetSetState();

    // ── Resume: skip already-completed sets ───────────────────────────────────
    // progressData.progress = {exercise_key: sets_done_today}
    const done = (progressData && progressData.progress) || {};

    // Count total planned sets per exercise_key so we know when to skip
    const plannedSets = {};
    data.exercises.forEach(ex => { plannedSets[ex.exercise_key] = ex.sets || 1; });

    // Walk the queue and find the first set that hasn't been saved yet
    _currentIdx = 0;
    for (let i = 0; i < _queue.length; i++) {
      const item    = _queue[i];
      const key     = item.exercise_key;
      const setsDone = done[key] || 0;
      // setIndex is 1-based; if setsDone >= setIndex, this set is already done
      if (setsDone >= item.setIndex) {
        _currentIdx = i + 1;   // skip past this set
      } else {
        break;   // first incomplete set found
      }
    }

    if (_currentIdx >= _queue.length) {
      // All sets already completed for today
      console.info('[PlanLoader] Workout already complete for today — showing summary.');
      _renderBanner();   // shows "Workout Complete!"
      if (window.showToast) window.showToast('✅ Today\'s workout is already complete!');
      return;
    }

    if (_currentIdx > 0) {
      const resumeItem = _queue[_currentIdx];
      console.info(
        `[PlanLoader] Resuming ${_weekday} plan from Exercise ${resumeItem.exerciseIndex}` +
        ` "${resumeItem.exerciseLabel}" Set ${resumeItem.setIndex}/${resumeItem.totalSets}` +
        ` (${_currentIdx} sets already done today)`
      );
    } else {
      console.info(`[PlanLoader] Loaded ${_weekday} plan: ${_queue.length} sets across ${data.exercises.length} exercises.`);
    }

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
