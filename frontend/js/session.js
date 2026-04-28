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
let _lastCount = 0;

const FEEDBACK_COLOUR = {
  'Up':              '#10b981',
  'Down':            '#3b82f6',
  'Fix Form':        '#ef4444',
  'Get in Position': '#9ca3af',
};

const FEEDBACK_EMOJI = {
  'Up':              '⬆️',
  'Down':            '⬇️',
  'Fix Form':        '⚠️',
  'Get in Position': '📍',
};

/**
 * Update all stat-card DOM elements.
 * Accepts: { counter, feedback, progress, correct_form, keypoints, skipped }
 * Also handles legacy: { count, angle, stage }
 */
function updateHUD(data) {
  // Rep count (pop animation on increment)
  const count = data.counter ?? data.count ?? 0;
  if (count !== _lastCount) {
    repCount.classList.remove('pop');
    void repCount.offsetWidth;    // force reflow to re-trigger
    repCount.classList.add('pop');
    _lastCount = count;
  }
  repCount.textContent = count;

  // Feedback badge
  const fb     = data.feedback ?? 'Get in Position';
  const colour = FEEDBACK_COLOUR[fb] ?? '#9ca3af';
  const emoji  = FEEDBACK_EMOJI[fb]  ?? '📍';

  if (feedbackEmoji) feedbackEmoji.textContent = emoji;
  if (feedbackText)  feedbackText.textContent  = fb;
  if (feedbackValue) feedbackValue.style.color = colour;
  if (feedbackCard)  feedbackCard.style.borderColor = colour + '44';

  // Progress bar
  const pct = Math.round(data.progress ?? 0);
  if (progressFill) {
    progressFill.style.width = `${pct}%`;
    const track = progressFill.closest('[role="progressbar"]');
    if (track) track.setAttribute('aria-valuenow', pct);
  }
  if (progressPctLabel) progressPctLabel.textContent = `${pct}% complete`;

  // Form status badge
  const unlocked = data.correct_form ?? false;
  if (formStatus)     formStatus.classList.toggle('unlocked', unlocked);
  if (formStatusText) formStatusText.textContent = unlocked ? '✅ Form Unlocked' : '📍 Get in Position';

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
