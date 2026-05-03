/**
 * app.js — ActionCount orchestrator (thin entry point).
 *
 * Architecture overview
 * ─────────────────────
 * - Display resolution  : whatever the browser/camera provides (720p+)
 * - Processing res      : PROCESS_W × PROCESS_H (see constants.js)
 * - FPS cap             : client-side 30 FPS gate via requestAnimationFrame
 * - Keypoint skip       : server runs RTMPose every 3rd frame, interpolates rest
 * - Skeleton drawing    : keypoints at processing res, scaled to display res
 * - MJPEG upload        : response body consumed via ReadableStream frame-by-frame
 *
 * Load order in index.html (all plain <script> tags, no bundler):
 *   js/constants.js  → shared constants, DOM refs, mutable state
 *   js/session.js    → SessionModule, updateHUD, setStatus, SkeletonDrawer
 *   js/live.js       → LiveModule (WebRTC + WebSocket)
 *   js/upload.js     → UploadModule (drag-and-drop + MJPEG)
 *   app.js           → tab switching, button wiring, exercise init  ← YOU ARE HERE
 */

'use strict';

// ══════════════════════════════════════════════════════════════════════════════
// Tab switching
// ══════════════════════════════════════════════════════════════════════════════
function switchTab(mode) {
  currentMode = mode;

  const isCam = mode === 'camera';

  tabCamera.classList.toggle('nav-tab--active', isCam);
  tabCamera.setAttribute('aria-selected', String(isCam));
  tabUpload.classList.toggle('nav-tab--active', !isCam);
  tabUpload.setAttribute('aria-selected', String(!isCam));

  // Show/hide upload overlay; fullscreen camera wrap is always behind
  panelUpload.hidden = isCam;

  if (!isCam) {
    // Switching to upload tab — stop camera, text mode
    LiveModule.stop();
    if (window.setFridayChannel) setFridayChannel('text');
    // Make sure upload result img is hidden (in case it was left from previous analysis)
    if (uploadResultImg) uploadResultImg.style.display = 'none';
    if (cameraPlaceholder) cameraPlaceholder.classList.remove('hidden');
  } else {
    // Switching to camera tab — abort any in-progress upload
    if (window.uploadModuleReset) window.uploadModuleReset();
    setStatus('idle', 'Press Start to begin');
  }
}

tabCamera.addEventListener('click', () => switchTab('camera'));
tabUpload.addEventListener('click', () => switchTab('upload'));

// ══════════════════════════════════════════════════════════════════════════════
// Button wiring
// ══════════════════════════════════════════════════════════════════════════════
btnStartCamera.addEventListener('click', () => LiveModule.start());
btnStopCamera.addEventListener('click',  () => LiveModule.stop());
btnReset.addEventListener('click',       () => SessionModule.reset());

exerciseSelect.addEventListener('change', () => {
  if (currentMode === 'camera') {
    LiveModule.stop();
    setStatus('idle', 'Exercise changed — press Start Camera');
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// Init — fetch exercise list from backend to keep dropdown in sync
// ══════════════════════════════════════════════════════════════════════════════
const EXERCISE_LABELS = {
  squat:          '🦵 Squat',
  pushup:         '💪 Push-up',
  bicep_curl:     '🏋️ Bicep Curl',
  pullup:         '🤸 Pull-up',
  lateral_raise:  '↔️ Lateral Raise',
  overhead_press: '⬆️ Overhead Press',
  situp:          '🧘 Sit-up',
  crunch:         '⚡ Crunch',
  leg_raise:      '🦶 Leg Raise',
  knee_raise:     '🦵 Knee Raise',
  knee_press:     '🔽 Knee Press',
};

(async function init() {
  try {
    const res = await fetch(`${API_BASE}/exercises`);
    if (res.ok) {
      const { exercises } = await res.json();
      exerciseSelect.innerHTML = exercises
        .map((e) => `<option value="${e}">${EXERCISE_LABELS[e] ?? e}</option>`)
        .join('');
      setStatus('idle', 'Idle');
    } else {
      console.warn('[Init] /exercises returned', res.status, '— using hardcoded options');
      setStatus('idle', 'Idle (offline mode)');
    }
  } catch (err) {
    console.warn('[Init] Could not reach server:', err.message);
    setStatus('error', 'Server unreachable — check backend');
  }
})();

// ══════════════════════════════════════════════════════════════════════════════
// StateMachine — IDLE → ACTIVE → WORKOUT
// ══════════════════════════════════════════════════════════════════════════════
/**
 * Thin state machine that owns the camera lifecycle.
 * All code that wants to start/stop the camera MUST call StateMachine.transition()
 * rather than calling LiveModule directly, so state is always consistent.
 *
 * States:
 *   IDLE    — camera off, no session
 *   ACTIVE  — camera on, session created, counting reps
 *   WORKOUT — same as ACTIVE; set when auto-started from a daily plan
 *
 * Transitions:
 *   IDLE    → ACTIVE  : user presses Start Camera (or auto-start)
 *   ACTIVE  → IDLE    : user presses Stop Camera
 *   WORKOUT → IDLE    : user presses Stop Camera after auto-start
 */
const StateMachine = (() => {
  const STATES = Object.freeze({ IDLE: 'IDLE', ACTIVE: 'ACTIVE', WORKOUT: 'WORKOUT' });
  let _state = STATES.IDLE;

  const _listeners = [];

  function getState()       { return _state; }
  function onState(fn)      { _listeners.push(fn); }
  function _emit()          { _listeners.forEach(fn => fn(_state)); }

  function transition(next) {
    if (_state === next) return;
    console.log(`[StateMachine] ${_state} → ${next}`);
    const prev = _state;
    _state = next;

    if ((next === STATES.ACTIVE || next === STATES.WORKOUT) && prev === STATES.IDLE) {
      LiveModule.start();
    }
    if (next === STATES.IDLE && prev !== STATES.IDLE) {
      LiveModule.stop();
    }
    _emit();
  }

  return { getState, transition, onState, STATES };
})();

// Re-wire existing buttons through StateMachine
btnStartCamera.removeEventListener('click', btnStartCamera._smHandler);
btnStopCamera.removeEventListener('click',  btnStopCamera._smHandler);

btnStartCamera._smHandler = () => StateMachine.transition(StateMachine.STATES.ACTIVE);
btnStopCamera._smHandler  = () => StateMachine.transition(StateMachine.STATES.IDLE);
btnStartCamera.addEventListener('click', btnStartCamera._smHandler);
btnStopCamera.addEventListener('click',  btnStopCamera._smHandler);

// ── Auto-Start: check today's plan and show a prompted banner ─────────────────
(async function checkTodayPlan() {
  if (!Auth || !Auth.isLoggedIn()) return;   // only for authenticated users
  try {
    const token = Auth.token();
    if (!token) return;

    const DAY_ABBR = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    const today    = DAY_ABBR[new Date().getDay()];

    const res  = await fetch(`${API_BASE}/api/plans/today?day=${today}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return;
    const data = await res.json();
    if (!data.has_plan || !data.exercises?.length) return;

    // Show banner instead of silently starting — per design decision
    _showAutoStartBanner(today, data.exercises);
  } catch (err) {
    console.warn('[AutoStart] Could not load today\'s plan:', err.message);
  }
})();

function _showAutoStartBanner(day, exercises) {
  // Avoid duplicate banners
  if (document.getElementById('autostart-sm-banner')) return;

  const exNames = exercises.slice(0, 3).map(e =>
    (EXERCISE_LABELS[e.exercise_key] || e.exercise_key).replace(/^[^\s]+\s/, '')
  ).join(', ');
  const more = exercises.length > 3 ? ` +${exercises.length - 3} more` : '';

  const banner = document.createElement('div');
  banner.id = 'autostart-sm-banner';
  banner.style.cssText = [
    'position:fixed;top:70px;left:50%;transform:translateX(-50%);',
    'z-index:9999;background:rgba(8,11,22,.95);',
    'border:1px solid rgba(52,211,153,.4);border-radius:999px;',
    'padding:.55rem 1.25rem;display:flex;align-items:center;gap:.75rem;',
    'box-shadow:0 4px 24px rgba(52,211,153,.15);',
    'font-family:Inter,sans-serif;font-size:.84rem;color:#e2e8f0;',
    'animation:fadeInDown .35s ease;',
  ].join('');
  banner.innerHTML = `
    <style>@keyframes fadeInDown{from{opacity:0;transform:translateX(-50%) translateY(-12px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}</style>
    <span>🏃</span>
    <span>Today is <strong style="color:#34d399">${day}</strong>: ${exNames}${more}</span>
    <button id="autostart-go-btn"
      style="padding:.3rem .9rem;border-radius:999px;background:#6366f1;color:#fff;border:none;font-size:.8rem;font-weight:600;cursor:pointer;">
      Start Workout
    </button>
    <button onclick="this.closest('#autostart-sm-banner').remove()"
      style="background:none;border:none;color:#64748b;cursor:pointer;font-size:1rem;">✕</button>`;

  document.body.appendChild(banner);

  document.getElementById('autostart-go-btn').addEventListener('click', () => {
    banner.remove();
    switchTab('camera');
    StateMachine.transition(StateMachine.STATES.WORKOUT);
  });

  // Auto-dismiss after 12 seconds
  setTimeout(() => banner?.remove(), 12000);
}

