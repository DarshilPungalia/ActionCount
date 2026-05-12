/**
 * friday_client.js
 * ----------------
 * Shared Friday WebSocket client for Dashboard App pages
 * (dashboard, plans, chatbot, metrics, welcome).
 *
 * This version is TEXT-MODE ONLY — voice navigation is not supported
 * in the Dashboard App. The WS connection is used solely to receive
 * friday_text agent responses (e.g. chatbot assistant messages).
 *
 * Navigation commands are intentionally stripped: the Dashboard App
 * uses REST API for chat and does not process frontend_command messages.
 *
 * Usage (add before </body>):
 *   <script src="/static/js/api.js"></script>
 *   <script src="/static/js/friday_client.js"></script>
 */
(function () {
  'use strict';

  // Always text mode — Dashboard App does not use voice navigation
  const _channel = 'text';

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
      console.log('[FridayClient] connected — channel: text (Dashboard App, navigation commands disabled)');
    };

    _ws.onmessage = function (evt) {
      try {
        const msg = JSON.parse(evt.data);
        // NOTE: frontend_command / navigation dispatch intentionally removed.
        // The Dashboard App does not handle voice navigation commands.
        // Only log text responses for debugging purposes.
        if (msg.type === 'friday_text') {
          console.log('[FridayClient] friday_text:', msg.data?.text);
        }
      } catch (_) {}
    };

    _ws.onclose = function () {
      _open = false;
      setTimeout(_openWS, 3000);   // auto-reconnect
    };
    _ws.onerror = function () { _ws.close(); };
  }

  // ── Public API ───────────────────────────────────────────────────────────────
  window.addEventListener('load', _openWS);

  window.FridayClient = {
    /** Returns true if the WebSocket is currently open. */
    isOpen: () => _open,
  };

})();
