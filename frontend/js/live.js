/**
 * live.js — LiveModule: WebRTC camera capture + WebSocket binary frame streaming.
 * Depends on: constants.js, session.js (loaded before this file).
 */

'use strict';

// ══════════════════════════════════════════════════════════════════════════════
// LiveModule
// ══════════════════════════════════════════════════════════════════════════════
const LiveModule = (() => {

  let stream           = null;
  let ws               = null;
  let rafId            = null;
  let offCanvas        = null;
  let offCtx           = null;
  let lastSendTime     = 0;
  let _metaListener    = null;   // stored so we can remove it on stop()

  // FPS display tracking
  let fpsFrames   = 0;
  let fpsLastTime = performance.now();

  async function start() {
    const exercise = exerciseSelect.value;

    setStatus('active', 'Starting…');
    btnStartCamera.disabled = true;

    // 1. Create backend session
    const sid = await SessionModule.start(exercise);
    if (!sid) {
      btnStartCamera.disabled = false;
      setStatus('error', 'Failed to start session');
      return;
    }

    // 2. Get camera stream at display resolution (720p ideal)
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width:     { ideal: 1280 },
          height:    { ideal: 720 },
          frameRate: { ideal: 30 },
        },
        audio: false,
      });
    } catch (err) {
      setStatus('error', 'Camera access denied');
      btnStartCamera.disabled = false;
      return;
    }

    localVideo.srcObject = stream;

    // 3. Off-screen canvas for frames at processing resolution
    offCanvas        = document.createElement('canvas');
    offCanvas.width  = PROCESS_W;
    offCanvas.height = PROCESS_H;
    offCtx           = offCanvas.getContext('2d');

    // 4. Size the overlay canvas once metadata is available, keep in sync
    _metaListener = () => _syncCanvasSize();
    localVideo.addEventListener('loadedmetadata', _metaListener);

    // Fix: enforce muted programmatically — HTML attribute alone is unreliable
    // on element reuse across sessions in some browsers.
    localVideo.muted = true;
    await localVideo.play();

    // Fix: wait for the first decoded frame before starting the send loop.
    // Prevents blank/black JPEG blobs being dispatched to the backend.
    await new Promise(resolve => {
      if (localVideo.readyState >= 2) return resolve();
      localVideo.addEventListener('loadeddata', resolve, { once: true });
    });

    _syncCanvasSize();
    cameraPlaceholder.classList.add('hidden');

    // 5. Open WebSocket
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${location.host}/ws/stream/${sid}`;
    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      setStatus('active', 'Streaming…');
      btnStartCamera.hidden = true;
      btnStopCamera.hidden  = false;
      rafId = requestAnimationFrame(_sendLoop);
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        updateHUD(data);

        if (data.keypoints) {
          const ctx = skeletonCanvas.getContext('2d');
          SkeletonDrawer.draw(
            ctx,
            data.keypoints,
            skeletonCanvas.width  / PROCESS_W,
            skeletonCanvas.height / PROCESS_H,
          );
        }
      } catch (_) { /* ignore parse errors */ }
    };

    ws.onerror = (e) => {
      console.error('[WS] error', e);
      setStatus('error', 'WebSocket error');
    };

    ws.onclose = () => {
      if (stream) _cleanup();
    };
  }

  function _syncCanvasSize() {
    const vW = localVideo.videoWidth;
    const vH = localVideo.videoHeight;
    if (vW > 0 && vH > 0) {
      skeletonCanvas.width  = vW;
      skeletonCanvas.height = vH;
    } else {
      const rect = localVideo.getBoundingClientRect();
      skeletonCanvas.width  = Math.round(rect.width)  || PROCESS_W;
      skeletonCanvas.height = Math.round(rect.height) || PROCESS_H;
    }
  }

  function _sendLoop(ts) {
    rafId = requestAnimationFrame(_sendLoop);

    // 30 FPS gate
    if (ts - lastSendTime < FRAME_MS) return;
    lastSendTime = ts;

    // FPS badge — updated every second
    fpsFrames++;
    if (ts - fpsLastTime >= 1000) {
      if (fpsBadge) fpsBadge.textContent = `${fpsFrames} FPS`;
      fpsFrames   = 0;
      fpsLastTime = ts;
    }

    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (localVideo.readyState < 2) return;

    offCtx.drawImage(localVideo, 0, 0, PROCESS_W, PROCESS_H);

    offCanvas.toBlob((blob) => {
      if (!blob || !ws || ws.readyState !== WebSocket.OPEN) return;
      blob.arrayBuffer().then((buf) => ws.send(buf));
    }, 'image/jpeg', 0.70);
  }

  function _cleanup() {
    cancelAnimationFrame(rafId);
    rafId = null;

    if (_metaListener) {
      localVideo.removeEventListener('loadedmetadata', _metaListener);
      _metaListener = null;
    }
    if (ws) { try { ws.close(); } catch (_) {} ws = null; }
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }

    localVideo.srcObject = null;
    const ctx = skeletonCanvas.getContext('2d');
    ctx.clearRect(0, 0, skeletonCanvas.width, skeletonCanvas.height);
  }

  function stop() {
    _cleanup();
    SessionModule.clearSession();
    cameraPlaceholder.classList.remove('hidden');
    btnStartCamera.hidden   = false;
    btnStopCamera.hidden    = true;
    btnStartCamera.disabled = false;
    if (fpsBadge) fpsBadge.textContent = '— FPS';
    setStatus('idle', 'Idle');
    updateHUD({ counter: 0, feedback: 'Get in Position', progress: 0, correct_form: false });
    _lastCount = 0;
  }

  return { start, stop };
})();
