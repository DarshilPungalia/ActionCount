/**
 * session.js — SessionModule, HUD helpers, SkeletonDrawer.
 * Depends on: constants.js (loaded before this file).
 */

'use strict';

// ══════════════════════════════════════════════════════════════════════════════
// SessionModule — session lifecycle with backend
// ══════════════════════════════════════════════════════════════════════════════
const SessionModule = (() => {

  async function start(exercise) {
    try {
      const res = await fetch(`${API_BASE}/session/start`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ exercise }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      sessionId = data.session_id;
      return sessionId;
    } catch (err) {
      console.error('[Session] start failed:', err);
      setStatus('error', `Session error: ${err.message}`);
      return null;
    }
  }

  async function reset() {
    if (!sessionId) return;
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/reset`, { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
      updateHUD({ counter: 0, feedback: 'Get in Position', progress: 0, correct_form: false });
      _lastCount = 0;
    } catch (err) {
      console.warn('[Session] reset failed:', err);
      setStatus('error', `Reset failed: ${err.message}`);
      sessionId = null;
    }
  }

  function clearSession() {
    sessionId = null;
  }

  return { start, reset, clearSession };
})();

// ══════════════════════════════════════════════════════════════════════════════
// HUD helpers
// ══════════════════════════════════════════════════════════════════════════════
let _lastCount    = 0;
// Lerp targets — the values the RAF loop is currently animating toward
let _targetCount  = 0;
let _targetPct    = 0;
// Current display values (fractional for smooth animation)
let _displayCount = 0;
let _displayPct   = 0;
let _lerpRafId    = null;

const LERP_SPEED = 0.14;   // fraction of remaining distance per frame (~8 Hz feel at 60 fps)

/** Lerp interpolation helper: a → b at speed t */
function _lerp(a, b, t) { return a + (b - a) * t; }

/**
 * RAF loop — smoothly drives displayed values toward their targets.
 * Only runs while there is still distance to cover.
 */
function _lerpLoop() {
  let stillMoving = false;

  // Rep counter
  const cdiff = Math.abs(_targetCount - _displayCount);
  if (cdiff > 0.05) {
    _displayCount = _lerp(_displayCount, _targetCount, LERP_SPEED);
    stillMoving   = true;
  } else {
    _displayCount = _targetCount;
  }
  repCount.textContent = Math.round(_displayCount);

  // Progress bar
  const pdiff = Math.abs(_targetPct - _displayPct);
  if (pdiff > 0.1) {
    _displayPct = _lerp(_displayPct, _targetPct, LERP_SPEED);
    stillMoving = true;
  } else {
    _displayPct = _targetPct;
  }
  if (progressFill) {
    progressFill.style.width = `${_displayPct}%`;
    const track = progressFill.closest('[role="progressbar"]');
    if (track) track.setAttribute('aria-valuenow', Math.round(_displayPct));
  }
  if (progressPctLabel) progressPctLabel.textContent = `${Math.round(_displayPct)}% complete`;

  if (stillMoving) {
    _lerpRafId = requestAnimationFrame(_lerpLoop);
  } else {
    _lerpRafId = null;
  }
}

function _startLerp() {
  if (!_lerpRafId) _lerpRafId = requestAnimationFrame(_lerpLoop);
}

const FEEDBACK_COLOUR = {
  'Up':              '#10b981',
  'Down':            '#3b82f6',
  'Fix Form':        '#ef4444',
  'Get in Position': '#9ca3af',
};

const FEEDBACK_EMOJI = {
  'Up':              '\u2b06\ufe0f',
  'Down':            '\u2b07\ufe0f',
  'Fix Form':        '\u26a0\ufe0f',
  'Get in Position': '\ud83d\udccd',
};

// ── Posture correction banner ─────────────────────────────────────────────────
let _postureEl = null;
function _getPostureEl() {
  if (_postureEl) return _postureEl;
  _postureEl = document.createElement('div');
  _postureEl.id = 'posture-correction-banner';
  Object.assign(_postureEl.style, {
    display:         'none',
    position:        'fixed',
    bottom:          '90px',
    left:            '50%',
    transform:       'translateX(-50%)',
    zIndex:          '80',
    padding:         '10px 18px',
    borderRadius:    '10px',
    background:      'rgba(239,68,68,0.18)',
    border:          '1px solid rgba(239,68,68,0.5)',
    color:           '#fca5a5',
    fontSize:        '14px',
    fontWeight:      '700',
    fontFamily:      'Inter, sans-serif',
    letterSpacing:   '0.02em',
    backdropFilter:  'blur(10px)',
    whiteSpace:      'nowrap',
    pointerEvents:   'none',
    transition:      'opacity 0.3s ease',
  });
  document.body.appendChild(_postureEl);
  return _postureEl;
}

// ── HUD Feedback debounce ────────────────────────────────────────────────────────
const FEEDBACK_DEBOUNCE_MS = 400;   // ms: feedback text settles before committing
const POSTURE_DEBOUNCE_MS  = 600;   // ms: posture messages (less disruptive)

let _feedbackTimer   = null;
let _pendingFb       = null;
let _committedFb     = null;

let _postureTimer    = null;
let _pendingPosture  = null;
let _committedPosture = null;

function _commitFeedback(fb) {
  _committedFb = fb;
  const colour = FEEDBACK_COLOUR[fb] ?? '#9ca3af';
  const emoji  = FEEDBACK_EMOJI[fb]  ?? '\ud83d\udccd';
  if (feedbackEmoji) feedbackEmoji.textContent = emoji;
  if (feedbackText)  feedbackText.textContent  = fb;
  if (feedbackValue) feedbackValue.style.color = colour;
  if (feedbackCard)  feedbackCard.style.borderColor = colour + '44';
}

function _commitPosture(msg) {
  _committedPosture = msg;
  const banner = _getPostureEl();
  if (msg) {
    banner.textContent   = '\u26a0\ufe0f\u2002' + msg;
    banner.style.display = 'block';
    banner.style.opacity = '1';
  } else {
    banner.style.opacity = '0';
    setTimeout(() => { if (banner.style.opacity === '0') banner.style.display = 'none'; }, 300);
  }
}

/**
 * Update all stat-card DOM elements.
 * Accepts: { counter, feedback, progress, correct_form, posture_msg, velocity, skipped }
 * Also handles legacy: { count, angle, stage }
 */
function updateHUD(data) {
  // Rep count — set target, let lerp loop animate
  const count = data.counter ?? data.count ?? 0;
  if (count !== _lastCount) {
    repCount.classList.remove('pop');
    void repCount.offsetWidth;    // force reflow to re-trigger
    repCount.classList.add('pop');
    _lastCount = count;
  }
  _targetCount = count;
  _startLerp();

  // Feedback badge — debounced 400 ms to prevent rapid Up↔Down flicker
  const fb = data.feedback ?? 'Get in Position';
  if (fb !== _committedFb) {
    clearTimeout(_feedbackTimer);
    _pendingFb    = fb;
    _feedbackTimer = setTimeout(() => _commitFeedback(_pendingFb), FEEDBACK_DEBOUNCE_MS);
  }

  // Progress bar — set target, lerp loop handles animation
  _targetPct = Math.round(data.progress ?? 0);
  _startLerp();

  // Form status badge
  const unlocked = data.correct_form ?? false;
  if (formStatus)     formStatus.classList.toggle('unlocked', unlocked);
  if (formStatusText) formStatusText.textContent = unlocked ? '\u2705 Form Unlocked' : '\ud83d\udccd Get in Position';

  // Posture correction banner — debounced 600 ms (HUD waits, not too jumpy)
  const postureMsg = data.posture_msg || null;
  if (postureMsg !== _committedPosture) {
    clearTimeout(_postureTimer);
    _pendingPosture = postureMsg;
    _postureTimer   = setTimeout(() => _commitPosture(_pendingPosture), POSTURE_DEBOUNCE_MS);
  }

  // Legacy angle arc
  const angle = data.angle ?? null;
  if (arcFill) {
    arcFill.style.strokeDashoffset = (angle !== null)
      ? 172 * (1 - Math.min(angle / 180, 1))
      : 172;
  }
}

function setStatus(state, label) {
  statusText.textContent = label;
  statusDot.className    = 'status-dot';
  if (state === 'active') statusDot.classList.add('active');
  if (state === 'error')  statusDot.classList.add('error');
}

// ══════════════════════════════════════════════════════════════════════════════
// SkeletonDrawer — COCO-17 keypoints + limbs on a canvas
// ══════════════════════════════════════════════════════════════════════════════
const SkeletonDrawer = (() => {

  /**
   * @param {CanvasRenderingContext2D} ctx
   * @param {Array<[number,number]>}   kps   keypoints at processing resolution
   * @param {number} scaleX  displayW / PROCESS_W
   * @param {number} scaleY  displayH / PROCESS_H
   */
  function draw(ctx, kps, scaleX, scaleY) {
    if (!kps || kps.length === 0) return;

    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);

    // Limb connections
    ctx.lineWidth   = 2.5;
    ctx.strokeStyle = 'rgba(6, 182, 212, 0.85)';
    ctx.lineCap     = 'round';

    for (const [i, j] of SKELETON_PAIRS) {
      const a = kps[i], b = kps[j];
      if (!a || !b) continue;
      const [ax, ay] = a;
      const [bx, by] = b;
      if ((ax === 0 && ay === 0) || (bx === 0 && by === 0)) continue;
      ctx.beginPath();
      ctx.moveTo(ax * scaleX, ay * scaleY);
      ctx.lineTo(bx * scaleX, by * scaleY);
      ctx.stroke();
    }

    // Keypoint circles
    for (const [x, y] of kps) {
      if (x === 0 && y === 0) continue;
      ctx.beginPath();
      ctx.arc(x * scaleX, y * scaleY, 5, 0, Math.PI * 2);
      ctx.fillStyle   = 'rgba(99, 102, 241, 0.9)';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth   = 1.5;
      ctx.stroke();
    }
  }

  return { draw };
})();
