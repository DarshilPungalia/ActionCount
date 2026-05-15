/**
 * overlay.js — Static HUD overlays for the fullscreen tracker.
 *
 * Renders a clock (top-left), weather widget (below clock), and live stats
 * panel (top-right) as plain position:fixed DOM elements.
 *
 * Listens for the 'hud:stats' custom event fired by the updateHUD patch below.
 */

(function () {
  'use strict';

  // ── Clock — top-left ──────────────────────────────────────────────────────

  const clockEl = document.createElement('div');
  clockEl.id = 'hud-clock';
  clockEl.style.cssText =
    'position:fixed;top:14px;left:16px;z-index:60;' +
    'pointer-events:none;user-select:none;' +
    'background:rgba(10,14,26,0.55);backdrop-filter:blur(10px);' +
    'border:1px solid rgba(255,255,255,0.07);border-radius:10px;' +
    'padding:8px 14px;';

  const timeEl = document.createElement('div');
  timeEl.id = 'hud-time';
  timeEl.style.cssText =
    'font-family:\'Inter\',monospace;font-size:30px;font-weight:800;' +
    'color:rgba(255,255,255,0.97);' +
    'text-shadow:0 0 18px rgba(100,200,255,0.6);' +
    'letter-spacing:0.04em;line-height:1.1;';

  const dateEl = document.createElement('div');
  dateEl.id = 'hud-date';
  dateEl.style.cssText =
    'font-family:\'Inter\',monospace;font-size:13px;font-weight:400;' +
    'color:rgba(180,220,255,0.55);' +
    'letter-spacing:0.1em;text-transform:uppercase;margin-top:3px;';

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

  // ── Weather widget — below clock (top: 96px) ──────────────────────────────
  // Clock: top:14px + ~74px height = ~88px. Weather sits at 96px with 8px gap.

  const weatherEl = document.createElement('div');
  weatherEl.id = 'hud-weather';
  weatherEl.style.cssText =
    'position:fixed;top:96px;left:16px;z-index:60;' +
    'pointer-events:none;user-select:none;' +
    'background:rgba(10,14,26,0.55);backdrop-filter:blur(10px);' +
    'border:1px solid rgba(255,255,255,0.07);border-radius:10px;' +
    'padding:7px 14px;' +
    'display:flex;align-items:center;gap:9px;' +
    'min-width:120px;';

  const weatherIconEl = document.createElement('span');
  weatherIconEl.id = 'hud-weather-icon';
  weatherIconEl.style.cssText = 'font-size:20px;flex-shrink:0;line-height:1;';
  weatherIconEl.textContent = '🌡️';

  const weatherInfoEl = document.createElement('div');
  weatherInfoEl.style.cssText = 'display:flex;flex-direction:column;gap:1px;';

  const weatherTempEl = document.createElement('div');
  weatherTempEl.id = 'hud-weather-temp';
  weatherTempEl.style.cssText =
    'font-family:\'Inter\',sans-serif;font-size:16px;font-weight:700;' +
    'color:rgba(255,255,255,0.90);line-height:1.1;';
  weatherTempEl.textContent = '—°C';

  const weatherDescEl = document.createElement('div');
  weatherDescEl.id = 'hud-weather-desc';
  weatherDescEl.style.cssText =
    'font-family:\'Inter\',sans-serif;font-size:9px;font-weight:600;' +
    'color:rgba(180,220,255,0.50);text-transform:uppercase;letter-spacing:0.1em;';
  weatherDescEl.textContent = 'Locating…';

  weatherInfoEl.appendChild(weatherTempEl);
  weatherInfoEl.appendChild(weatherDescEl);
  weatherEl.appendChild(weatherIconEl);
  weatherEl.appendChild(weatherInfoEl);
  document.body.appendChild(weatherEl);

  // WMO weather code → emoji + label
  const WMO = {
    0:  { icon:'☀️',  desc:'Clear'      },
    1:  { icon:'🌤️', desc:'Mostly Clear'},
    2:  { icon:'⛅',  desc:'Partly Cloudy'},
    3:  { icon:'☁️',  desc:'Overcast'   },
    45: { icon:'🌫️', desc:'Foggy'       },
    48: { icon:'🌫️', desc:'Icy Fog'     },
    51: { icon:'🌦️', desc:'Lt Drizzle'  },
    53: { icon:'🌦️', desc:'Drizzle'     },
    55: { icon:'🌧️', desc:'Hvy Drizzle' },
    61: { icon:'🌧️', desc:'Lt Rain'     },
    63: { icon:'🌧️', desc:'Rain'        },
    65: { icon:'🌧️', desc:'Heavy Rain'  },
    71: { icon:'🌨️', desc:'Lt Snow'     },
    73: { icon:'❄️',  desc:'Snow'        },
    75: { icon:'❄️',  desc:'Heavy Snow'  },
    80: { icon:'🌦️', desc:'Showers'     },
    81: { icon:'🌧️', desc:'Showers'     },
    82: { icon:'⛈️', desc:'Hvy Showers' },
    95: { icon:'⛈️', desc:'Thunderstorm'},
    99: { icon:'⛈️', desc:'Thunderstorm'},
  };

  function _applyWeather(temp, code) {
    const entry = WMO[code] || WMO[Math.floor(code / 10) * 10] || { icon:'🌡️', desc:'Unknown' };
    weatherIconEl.textContent  = entry.icon;
    weatherTempEl.textContent  = Math.round(temp) + '°C';
    weatherDescEl.textContent  = entry.desc;
  }

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        const { latitude: lat, longitude: lon } = pos.coords;
        const url = `https://api.open-meteo.com/v1/forecast` +
          `?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}` +
          `&current_weather=true`;
        fetch(url)
          .then(r => r.json())
          .then(data => {
            const cw = data.current_weather;
            _applyWeather(cw.temperature, cw.weathercode);
          })
          .catch(() => {
            weatherDescEl.textContent = 'Unavailable';
          });
      },
      function () {
        weatherIconEl.textContent = '📍';
        weatherDescEl.textContent = 'Denied';
      },
      { timeout: 8000, maximumAge: 600000 }
    );
  } else {
    weatherDescEl.textContent = 'N/A';
  }

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
  const postureVal  = makeStatRow('Posture');
  const progressVal = makeStatRow('Progress');
  const volumeVal   = makeStatRow('Session Vol.');

  // Style the volume row to stand out
  volumeVal.style.color = '#34d399';

  document.body.appendChild(statsEl);

  // ── Live Volume tracking ──────────────────────────────────────────────────

  let _sessionVolume = 0;  // kg
  let _lastRepCount  = 0;

  function getWeightKg() {
    const el = document.getElementById('weight-input');
    return el ? parseFloat(el.value) || 0 : 0;
  }

  function updateVolumeDisplay() {
    volumeVal.textContent = _sessionVolume > 0
      ? _sessionVolume.toFixed(1) + ' kg'
      : '— kg';
  }

  window.addEventListener('load', function () {
    const repCountEl = document.getElementById('rep-count');
    if (!repCountEl) return;

    new MutationObserver(function () {
      const count = parseInt(repCountEl.textContent || '0', 10);
      if (count > _lastRepCount) {
        const newReps = count - _lastRepCount;
        _sessionVolume += newReps * getWeightKg();
        _lastRepCount   = count;
        updateVolumeDisplay();
      } else if (count === 0 && _lastRepCount > 0) {
        _lastRepCount = 0;
      }
    }, { childList: true, subtree: true, characterData: true });

    const exSelect = document.getElementById('exercise-select');
    if (exSelect) {
      exSelect.addEventListener('change', () => {
        _sessionVolume = 0;
        _lastRepCount  = 0;
        updateVolumeDisplay();
      });
    }

    updateVolumeDisplay();
  });

  // ── Listen for HUD updates ────────────────────────────────────────────────

  document.addEventListener('hud:stats', function (e) {
    const d = e.detail || {};
    repVal.textContent      = d.counter ?? d.count ?? 0;
    formVal.textContent     = d.feedback ?? 'Get in Position';

    const pMsg = d.posture_msg || null;
    postureVal.textContent  = pMsg ? '\u26a0\ufe0f ' + pMsg : '\u2705 Good form';
    postureVal.style.color  = pMsg ? '#fca5a5' : 'rgba(255,255,255,0.92)';

    progressVal.textContent = Math.round(d.progress ?? 0) + '%';
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
