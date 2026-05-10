/**
 * friday_client.js
 * ----------------
 * Lightweight shared Friday WebSocket client for non-tracker pages.
 *
 * Handles:
 *   - WS connection + auto-reconnect to /ws/friday
 *   - Site navigation frontend_commands (navigate_*)
 *   - Page-transition audio playback (voice channel only)
 *   - No waveform HUD — that stays on tracker/calorie pages
 *
 * Usage (add before </body>):
 *   <script src="/static/js/api.js"></script>
 *   <script src="/static/js/friday_client.js" data-channel="voice"></script>
 *
 * For chatbot page use data-channel="text".
 * Optionally set window.dispatchFridayCommand = function(cmd){...} before
 * this script loads to handle page-specific commands.
 */
(function () {
  'use strict';

  // Determine channel from the <script> tag's data-channel attribute (default: voice)
  const _scriptEl = document.currentScript;
  const _channel  = (_scriptEl && _scriptEl.getAttribute('data-channel')) || 'voice';

  // ── Navigation command dispatcher ────────────────────────────────────────────
  function _dispatchNavCommand(cmd) {
    console.log('[FridayClient] frontend_command:', cmd);
    switch (cmd) {

      // ── Site navigation ────────────────────────────────────────────────────
      case 'navigate_tracker':
        window.location.href = '/';
        break;
      case 'navigate_dashboard':
        window.location.href = '/dashboard';
        break;
      case 'navigate_chatbot':
        window.location.href = '/chatbot';
        break;
      case 'navigate_plans':
        window.location.href = '/plans';
        break;
      case 'navigate_metrics':
        window.location.href = '/metrics';
        break;
      case 'navigate_calorie':
      case 'open_calorie':
      case 'calorie_snapshot':
        window.location.href = '/calorie';
        break;
      case 'navigate_back':
        history.back();
        break;

      default:
        // Delegate to a page-specific handler if one has been registered
        if (typeof window.dispatchFridayCommand === 'function') {
          window.dispatchFridayCommand(cmd);
        } else {
          console.log('[FridayClient] unhandled command:', cmd);
        }
    }
  }

  // ── WebSocket ────────────────────────────────────────────────────────────────
  let _ws   = null;
  let _open = false;

  function _openWS() {
    const token = localStorage.getItem('access_token') || localStorage.getItem('ac_token');
    if (!token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    _ws = new WebSocket(
      `${proto}://${location.host}/ws/friday?token=${encodeURIComponent(token)}&channel=${_channel}`
    );

    _ws.onopen = function () {
      _open = true;
      _ws.send(JSON.stringify({ type: 'set_channel', data: { channel: _channel } }));
      console.log(`[FridayClient] connected — channel: ${_channel}`);
    };

    _ws.onmessage = function (evt) {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'frontend_command') {
          _dispatchNavCommand(msg.data?.command || '');
        }
        // friday_audio removed (TTS disabled — see docs/tts_integration_reference.md)
      } catch (_) {}
    };

    _ws.onclose = function () {
      _open = false;
      setTimeout(_openWS, 3000);   // auto-reconnect
    };
    _ws.onerror = function () { _ws.close(); };
  }

  // ── Public API ───────────────────────────────────────────────────────────────
  function _setChannel(channel) {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'set_channel', data: { channel } }));
    }
  }

  window.addEventListener('load', _openWS);

  window.FridayClient = {
    /** Switch the active channel ('voice' | 'text') on the fly. */
    setChannel: _setChannel,
    /** Returns true if the WebSocket is currently open. */
    isOpen:     () => _open,
  };

})();
