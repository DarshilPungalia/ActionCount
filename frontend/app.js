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
    LiveModule.stop();
    if (window.setFridayChannel) setFridayChannel('text');
  } else {
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
