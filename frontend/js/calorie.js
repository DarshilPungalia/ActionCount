/**
 * calorie.js — Standalone calorie scanner page logic.
 * Handles: camera init, snapshot, POST /api/calorie/scan, result popup,
 * voice command trigger via Friday WS.
 */

'use strict';

// ── DOM refs ────────────────────────────────────────────────────────────────
const calVideo          = document.getElementById('cal-video');
const btnSnapshot       = document.getElementById('btn-snapshot');
const calResultPopup    = document.getElementById('cal-result-popup');
const calFoodsList      = document.getElementById('cal-foods-list');
const calTotalValue     = document.getElementById('cal-total-value');
const calPopupClose     = document.getElementById('cal-popup-close');
const calScanningOverlay = document.getElementById('cal-scanning-overlay');
const calNoFood         = document.getElementById('cal-no-food');
const foodGuideBox      = document.getElementById('food-guide-box');
const waveHud           = document.getElementById('friday-wave-hud');
const waveIcon          = document.getElementById('friday-wave-icon');
const waveLabel         = document.getElementById('friday-wave-label');

// ── State ───────────────────────────────────────────────────────────────────
let _cameraStream = null;
let _scanning     = false;
let _noFoodTimer  = null;
let _fridayWs     = null;

// ── Camera init ─────────────────────────────────────────────────────────────
async function initCamera() {
  try {
    _cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'environment' },
      audio: false,
    });
    calVideo.srcObject = _cameraStream;
    await calVideo.play();
  } catch (err) {
    console.error('[CaloriePage] Camera error:', err);
    alert('Camera access denied. Please allow camera permission and reload.');
  }
}

// ── Snapshot → scan ─────────────────────────────────────────────────────────
async function takeSnapshot() {
  if (_scanning) return;
  _scanning = true;

  // Flash guide box
  foodGuideBox.classList.add('scanning');
  btnSnapshot.classList.add('scanning');
  btnSnapshot.textContent = '⏳';
  showScanningOverlay(true);
  hidePopup();
  hideNoFood();

  // Draw frame to offscreen canvas
  const canvas = document.createElement('canvas');
  canvas.width  = calVideo.videoWidth  || 640;
  canvas.height = calVideo.videoHeight || 480;
  canvas.getContext('2d').drawImage(calVideo, 0, 0, canvas.width, canvas.height);
  const dataUrl  = canvas.toDataURL('image/jpeg', 0.85);
  const image_b64 = dataUrl.split(',')[1];  // strip prefix

  try {
    const result = await apiFetch('/api/calorie/scan', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ image_b64 }),
    });

    if (result.error || !result.foods || result.foods.length === 0) {
      showNoFood();
    } else {
      showResult(result);
    }
  } catch (err) {
    console.error('[CaloriePage] Scan error:', err);
    showNoFood();
  } finally {
    _scanning = false;
    foodGuideBox.classList.remove('scanning');
    btnSnapshot.classList.remove('scanning');
    btnSnapshot.textContent = '📸';
    showScanningOverlay(false);
  }
}

// ── Show result popup — calories + portion only ─────────────────────────────
function showResult(data) {
  const foods = data.foods || [];

  calFoodsList.innerHTML = foods.map(f => `
    <li>
      <span class="cal-food-name">
        ${escHtml(f.name)}
        <span class="cal-food-portion">${escHtml(f.portion || '')}</span>
      </span>
      <span class="cal-food-kcal">${f.calories} kcal</span>
    </li>
  `).join('');

  calTotalValue.textContent = data.total_calories || 0;

  calResultPopup.classList.add('visible');

  // Auto-dismiss after 10 s
  clearTimeout(calResultPopup._timer);
  calResultPopup._timer = setTimeout(hidePopup, 10000);
}

function hidePopup() {
  calResultPopup.classList.remove('visible');
  clearTimeout(calResultPopup._timer);
}

// ── No food state ────────────────────────────────────────────────────────────
function showNoFood() {
  calNoFood.classList.add('visible');
  clearTimeout(_noFoodTimer);
  _noFoodTimer = setTimeout(hideNoFood, 3500);
}
function hideNoFood() { calNoFood.classList.remove('visible'); }

// ── Scanning overlay ─────────────────────────────────────────────────────────
function showScanningOverlay(show) {
  calScanningOverlay.classList.toggle('visible', show);
}

// ── Friday WS (voice trigger) ────────────────────────────────────────────────
function openFridayWS() {
  const token = localStorage.getItem('access_token') || localStorage.getItem('ac_token');
  if (!token) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  _fridayWs = new WebSocket(`${proto}://${location.host}/ws/friday?token=${encodeURIComponent(token)}&channel=voice`);

  _fridayWs.onopen = () => {
    _fridayWs.send(JSON.stringify({ type: 'set_channel', data: { channel: 'voice' } }));
    setWaveMode('listening');
  };

  _fridayWs.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      // Voice command: "take snapshot" / "scan food"
      if (msg.type === 'frontend_command') {
        const cmd = msg.data?.command || '';
        if (cmd === 'calorie_snapshot' || cmd === 'take_snapshot') {
          takeSnapshot();
        } else {
          // Site navigation commands
          const _navMap = {
            navigate_tracker:   '/',
            navigate_dashboard: '/dashboard',
            navigate_chatbot:   '/chatbot',
            navigate_plans:     '/plans',
            navigate_metrics:   '/metrics',
            navigate_calorie:   '/calorie',
          };
          if (cmd in _navMap) {
            window.location.href = _navMap[cmd];
          } else if (cmd === 'navigate_back') {
            history.back();
          }
        }
      }
      if (msg.type === 'calorie_result' && msg.data?.foods?.length) {
        showResult(msg.data);
      }
      if (msg.type === 'friday_listening') {
        setWaveMode(msg.data?.active ? 'listening' : 'idle');
      }
      if (msg.type === 'friday_speaking') {
        setWaveMode(msg.data?.active ? 'responding' : 'idle');
      }
      if (msg.type === 'friday_audio' && msg.data?.audio_b64) {
        try { new Audio('data:audio/mp3;base64,' + msg.data.audio_b64).play().catch(() => {}); } catch(_) {}
      }
    } catch (_) {}
  };

  _fridayWs.onclose = () => {
    setWaveMode('idle');
    setTimeout(openFridayWS, 3000);
  };
  _fridayWs.onerror = () => _fridayWs.close();
}

function setWaveMode(mode) {
  if (!waveHud) return;
  waveHud.classList.remove('fw-listening', 'fw-responding');
  if (mode === 'listening') {
    waveHud.style.display = 'flex';
    waveHud.classList.add('fw-listening');
    if (waveIcon)  waveIcon.textContent  = '🎙️';
    if (waveLabel) waveLabel.textContent = 'Listening…';
  } else if (mode === 'responding') {
    waveHud.style.display = 'flex';
    waveHud.classList.add('fw-responding');
    if (waveIcon)  waveIcon.textContent  = '🤖';
    if (waveLabel) waveLabel.textContent = 'Friday';
  } else {
    waveHud.style.display = 'none';
  }
}

// ── Utils ────────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Event listeners ──────────────────────────────────────────────────────────
btnSnapshot.addEventListener('click', takeSnapshot);
calPopupClose.addEventListener('click', hidePopup);

// ── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener('load', () => {
  initCamera();
  openFridayWS();
});

// Clean up camera on page unload
window.addEventListener('beforeunload', () => {
  if (_cameraStream) _cameraStream.getTracks().forEach(t => t.stop());
  if (_fridayWs) try { _fridayWs.close(); } catch(_) {}
});
