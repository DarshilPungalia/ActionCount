/**
 * rest_timer.js — RestTimer Module
 * ---------------------------------
 * Renders a centered glassmorphic SVG ring countdown overlay between sets.
 *
 * API:
 *   RestTimer.start(seconds, onComplete, nextLabel)
 *   RestTimer.skip()
 *   RestTimer.DEFAULT_SECONDS  (default: 120)
 *
 * The overlay is built lazily on first call and reused.
 * Camera is stopped BEFORE the timer starts and restarted inside onComplete.
 */

'use strict';

const RestTimer = (() => {

  const DEFAULT_SECONDS = 120;

  // SVG ring circumference for r=54: 2π×54 ≈ 339.292
  const CIRCUMFERENCE = 2 * Math.PI * 54;

  let _overlayEl   = null;   // root overlay div
  let _ringEl      = null;   // the animated SVG circle
  let _timeEl      = null;   // MM:SS text inside ring
  let _nextLabelEl = null;   // "Next: Push-up  Set 2/3" label
  let _skipBtn     = null;   // Skip button

  let _interval    = null;   // setInterval handle
  let _total       = 0;
  let _elapsed     = 0;
  let _onComplete  = null;

  // ── Build overlay DOM (once) ────────────────────────────────────────────────
  function _build() {
    if (_overlayEl) return;

    _overlayEl = document.createElement('div');
    _overlayEl.id = 'rest-timer-overlay';
    Object.assign(_overlayEl.style, {
      display:         'none',
      position:        'fixed',
      inset:           '0',
      zIndex:          '200',
      alignItems:      'center',
      justifyContent:  'center',
      background:      'rgba(6,8,16,0.72)',
      backdropFilter:  'blur(18px)',
      fontFamily:      '\'Inter\', sans-serif',
    });

    // Card
    const card = document.createElement('div');
    Object.assign(card.style, {
      display:         'flex',
      flexDirection:   'column',
      alignItems:      'center',
      gap:             '20px',
      background:      'rgba(14,18,32,0.88)',
      border:          '1px solid rgba(99,102,241,0.25)',
      borderRadius:    '24px',
      padding:         '40px 48px',
      boxShadow:       '0 24px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)',
      minWidth:        '300px',
      textAlign:       'center',
    });

    // Title
    const title = document.createElement('div');
    title.textContent = '\uD83C\uDFCB\uFE0F  Rest Period';
    Object.assign(title.style, {
      fontSize:      '1rem',
      fontWeight:    '700',
      color:         'rgba(165,180,252,0.9)',
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
    });

    // SVG ring
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 120 120');
    svg.setAttribute('width', '160');
    svg.setAttribute('height', '160');
    svg.style.overflow = 'visible';

    // Gradient def
    const defs = document.createElementNS(svgNS, 'defs');
    const grad = document.createElementNS(svgNS, 'linearGradient');
    grad.setAttribute('id', 'restGrad');
    grad.setAttribute('x1', '0%'); grad.setAttribute('y1', '0%');
    grad.setAttribute('x2', '100%'); grad.setAttribute('y2', '100%');
    const s1 = document.createElementNS(svgNS, 'stop');
    s1.setAttribute('offset', '0%'); s1.setAttribute('stop-color', '#818cf8');
    const s2 = document.createElementNS(svgNS, 'stop');
    s2.setAttribute('offset', '100%'); s2.setAttribute('stop-color', '#6366f1');
    grad.appendChild(s1); grad.appendChild(s2);
    defs.appendChild(grad);
    svg.appendChild(defs);

    // Track ring (background)
    const track = document.createElementNS(svgNS, 'circle');
    track.setAttribute('cx', '60'); track.setAttribute('cy', '60');
    track.setAttribute('r', '54'); track.setAttribute('fill', 'none');
    track.setAttribute('stroke', 'rgba(99,102,241,0.12)');
    track.setAttribute('stroke-width', '8');
    svg.appendChild(track);

    // Progress ring
    _ringEl = document.createElementNS(svgNS, 'circle');
    _ringEl.setAttribute('cx', '60'); _ringEl.setAttribute('cy', '60');
    _ringEl.setAttribute('r', '54'); _ringEl.setAttribute('fill', 'none');
    _ringEl.setAttribute('stroke', 'url(#restGrad)');
    _ringEl.setAttribute('stroke-width', '8');
    _ringEl.setAttribute('stroke-linecap', 'round');
    _ringEl.setAttribute('stroke-dasharray', String(CIRCUMFERENCE));
    _ringEl.setAttribute('stroke-dashoffset', '0');
    _ringEl.setAttribute('transform', 'rotate(-90 60 60)');
    _ringEl.style.transition = 'stroke-dashoffset 0.9s ease';
    svg.appendChild(_ringEl);

    // Time text inside ring
    _timeEl = document.createElementNS(svgNS, 'text');
    _timeEl.setAttribute('x', '60'); _timeEl.setAttribute('y', '66');
    _timeEl.setAttribute('text-anchor', 'middle');
    _timeEl.setAttribute('fill', 'rgba(255,255,255,0.92)');
    _timeEl.setAttribute('font-size', '20');
    _timeEl.setAttribute('font-weight', '700');
    _timeEl.setAttribute('font-family', 'Inter, monospace');
    _timeEl.textContent = '2:00';
    svg.appendChild(_timeEl);

    // Next exercise label
    _nextLabelEl = document.createElement('div');
    Object.assign(_nextLabelEl.style, {
      fontSize:    '0.88rem',
      fontWeight:  '600',
      color:       'rgba(226,232,240,0.75)',
      lineHeight:  '1.5',
    });

    // Skip button
    _skipBtn = document.createElement('button');
    _skipBtn.id = 'rest-skip-btn';
    _skipBtn.textContent = 'Skip Rest';
    Object.assign(_skipBtn.style, {
      marginTop:     '4px',
      padding:       '9px 24px',
      borderRadius:  '999px',
      border:        '1px solid rgba(99,102,241,0.35)',
      background:    'transparent',
      color:         '#a5b4fc',
      fontSize:      '0.82rem',
      fontWeight:    '600',
      cursor:        'pointer',
      fontFamily:    '\'Inter\', sans-serif',
      letterSpacing: '0.04em',
      transition:    'background 0.15s, color 0.15s',
    });
    _skipBtn.addEventListener('mouseover',  () => { _skipBtn.style.background = 'rgba(99,102,241,0.18)'; _skipBtn.style.color = '#c7d2fe'; });
    _skipBtn.addEventListener('mouseout',   () => { _skipBtn.style.background = 'transparent'; _skipBtn.style.color = '#a5b4fc'; });
    _skipBtn.addEventListener('click', skip);

    card.appendChild(title);
    card.appendChild(svg);
    card.appendChild(_nextLabelEl);
    card.appendChild(_skipBtn);
    _overlayEl.appendChild(card);
    document.body.appendChild(_overlayEl);
  }

  // ── Time formatting ──────────────────────────────────────────────────────────
  function _fmt(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  // ── Update ring progress ─────────────────────────────────────────────────────
  function _updateRing(remaining, total) {
    const pct    = remaining / total;
    const offset = CIRCUMFERENCE * (1 - pct);
    _ringEl.setAttribute('stroke-dashoffset', String(offset));
    _timeEl.textContent = _fmt(remaining);

    // Colour shift: indigo → amber → red as time runs out
    if (pct > 0.5) {
      _ringEl.setAttribute('stroke', 'url(#restGrad)');
    } else if (pct > 0.2) {
      _ringEl.setAttribute('stroke', '#f59e0b');
    } else {
      _ringEl.setAttribute('stroke', '#ef4444');
    }
  }

  // ── Start ────────────────────────────────────────────────────────────────────
  /**
   * Start the rest timer.
   * @param {number}   seconds    - duration in seconds (default 120)
   * @param {Function} onComplete - called when timer finishes or is skipped
   * @param {string}   nextLabel  - text shown below the ring, e.g. "Next: Squat  Set 2/3  ·  12 reps"
   */
  function start(seconds = DEFAULT_SECONDS, onComplete = null, nextLabel = '') {
    _build();
    clearInterval(_interval);

    _total      = seconds;
    _elapsed    = 0;
    _onComplete = onComplete;

    _nextLabelEl.innerHTML = nextLabel || '';
    _updateRing(_total, _total);

    // Show overlay (flex)
    _overlayEl.style.display = 'flex';

    _interval = setInterval(() => {
      _elapsed++;
      const remaining = _total - _elapsed;
      _updateRing(remaining, _total);

      if (remaining <= 0) {
        _finish();
      }
    }, 1000);
  }

  // ── Skip ─────────────────────────────────────────────────────────────────────
  function skip() {
    _finish();
  }

  // ── Internal finish ──────────────────────────────────────────────────────────
  function _finish() {
    clearInterval(_interval);
    _interval = null;
    if (_overlayEl) _overlayEl.style.display = 'none';
    const cb = _onComplete;
    _onComplete = null;
    if (typeof cb === 'function') cb();
  }

  // ── Public API ───────────────────────────────────────────────────────────────
  return { start, skip, DEFAULT_SECONDS };

})();
