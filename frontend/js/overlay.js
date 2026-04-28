/**
 * overlay.js — Static HUD overlays for the fullscreen tracker.
 *
 * Renders a clock (top-left) and live stats panel (top-right) as plain
 * position:fixed DOM elements — no CSS2DRenderer needed for static overlays.
 *
 * Listens for the 'hud:stats' custom event fired by the updateHUD patch below.
 */

(function () {
  'use strict';

  // ── Clock — top-left ──────────────────────────────────────────────────────

  const clockEl = document.createElement('div');
  clockEl.id = 'hud-clock';
  clockEl.style.cssText =
    'position:fixed;top:16px;left:16px;z-index:60;' +
    'pointer-events:none;user-select:none;';

  const timeEl = document.createElement('div');
  timeEl.id = 'hud-time';
  timeEl.style.cssText =
    'font-family:\'Inter\',monospace;font-size:22px;font-weight:700;' +
    'color:rgba(255,255,255,0.95);' +
    'text-shadow:0 0 14px rgba(100,200,255,0.55);' +
    'letter-spacing:0.04em;';

  const dateEl = document.createElement('div');
  dateEl.id = 'hud-date';
  dateEl.style.cssText =
    'font-family:\'Inter\',monospace;font-size:11px;font-weight:300;' +
    'color:rgba(180,220,255,0.5);' +
    'letter-spacing:0.12em;text-transform:uppercase;margin-top:2px;';

  clockEl.appendChild(timeEl);
  clockEl.appendChild(dateEl);
  document.body.appendChild(clockEl);

  function tickClock() {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
    dateEl.textContent = now.toLocaleDateString('en-US', {
      weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
    });
  }
  tickClock();
  setInterval(tickClock, 1000);

  // ── Stats panel — top-right ───────────────────────────────────────────────

  const statsEl = document.createElement('div');
  statsEl.id = 'hud-stats';
  statsEl.style.cssText =
    'position:fixed;top:16px;right:16px;z-index:60;' +
    'width:180px;display:flex;flex-direction:column;gap:6px;' +
    'pointer-events:none;user-select:none;';

  function makeStatRow(label) {
    const row = document.createElement('div');
    row.style.cssText =
      'background:rgba(10,14,26,0.65);' +
      'border:1px solid rgba(100,200,255,0.12);' +
      'border-radius:8px;padding:7px 12px;' +
      'backdrop-filter:blur(10px);';

    const lbl = document.createElement('div');
    lbl.style.cssText =
      'font-family:\'Inter\',sans-serif;font-size:9px;font-weight:600;' +
      'color:rgba(180,220,255,0.5);' +
      'text-transform:uppercase;letter-spacing:0.12em;';
    lbl.textContent = label;

    const val = document.createElement('div');
    val.style.cssText =
      'font-family:\'Inter\',sans-serif;font-size:15px;font-weight:700;' +
      'color:rgba(255,255,255,0.92);margin-top:2px;';
    val.textContent = '—';

    row.appendChild(lbl);
    row.appendChild(val);
    statsEl.appendChild(row);
    return val;
  }

  const repVal      = makeStatRow('Reps');
  const formVal     = makeStatRow('Feedback');
  const progressVal = makeStatRow('Progress');
  const angleVal    = makeStatRow('Angle');

  document.body.appendChild(statsEl);

  // ── Listen for HUD updates ────────────────────────────────────────────────

  document.addEventListener('hud:stats', function (e) {
    const d = e.detail || {};
    repVal.textContent      = d.counter ?? d.count ?? 0;
    formVal.textContent     = d.feedback ?? 'Get in Position';
    progressVal.textContent = Math.round(d.progress ?? 0) + '%';
    const angle = d.angle ?? null;
    angleVal.textContent    = angle !== null ? Math.round(angle) + '°' : '—';
  });

  // ── Patch updateHUD to fire hud:stats event ───────────────────────────────

  window.addEventListener('load', function () {
    if (typeof updateHUD === 'function' && !updateHUD._hudPatched) {
      const _orig = updateHUD;
      // eslint-disable-next-line no-global-assign
      updateHUD = function (data) {
        _orig(data);
        document.dispatchEvent(new CustomEvent('hud:stats', { detail: data }));
      };
      updateHUD._hudPatched = true;
    }
  });

})();
