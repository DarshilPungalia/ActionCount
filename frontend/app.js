/**
 * app.js — ActionCount frontend
 * ==============================
 * ES6 module. Three logical sections:
 *   1. SessionModule  — session lifecycle with backend
 *   2. UploadModule   — drag-and-drop video upload + real-time MJPEG stream
 *   3. LiveModule     — WebRTC getUserMedia + WebSocket binary frames
 *
 * Architecture overview
 * ----------------------
 * - Display resolution  : whatever the browser/camera provides (720p+)
 * - Processing resolution: PROCESS_W × PROCESS_H downscaled before sending
 * - FPS cap             : client-side 30 FPS ticker via requestAnimationFrame
 * - Keypoint skip       : server runs RTMPose every 3rd frame, interpolates rest
 * - Skeleton drawing    : keypoints returned at processing res, scaled to display
 * - MJPEG upload        : response body consumed via ReadableStream frame-by-frame
 */

'use strict';

// ── Constants ──────────────────────────────────────────────────────────
const API_BASE   = '';              // same origin as FastAPI server
const TARGET_FPS = 30;
const FRAME_MS   = 1000 / TARGET_FPS;  // ~33.33 ms
const PROCESS_W  = 640;            // width of frames sent to server
const PROCESS_H  = 360;            // height of frames sent to server

// COCO-17 skeleton connectivity pairs
const SKELETON_PAIRS = [
  [0,1],[0,2],[1,3],[2,4],
  [5,6],
  [5,7],[7,9],
  [6,8],[8,10],
  [5,11],[6,12],
  [11,12],
  [11,13],[13,15],
  [12,14],[14,16],
];

// ── DOM refs ───────────────────────────────────────────────────────────
const exerciseSelect    = document.getElementById('exercise-select');
const repCount          = document.getElementById('rep-count');
const angleValue        = document.getElementById('angle-value');
const stageBadge        = document.getElementById('stage-badge');
const statusDot         = document.getElementById('status-dot');
const statusText        = document.getElementById('status-text');
const btnReset          = document.getElementById('btn-reset');
const arcFill           = document.getElementById('angle-arc-fill');

const tabCamera         = document.getElementById('tab-camera');
const tabUpload         = document.getElementById('tab-upload');
const panelCamera       = document.getElementById('panel-camera');
const panelUpload       = document.getElementById('panel-upload');

const localVideo        = document.getElementById('local-video');
const skeletonCanvas    = document.getElementById('skeleton-canvas');
const cameraPlaceholder = document.getElementById('camera-placeholder');
const btnStartCamera    = document.getElementById('btn-start-camera');
const btnStopCamera     = document.getElementById('btn-stop-camera');
const fpsBadge          = document.getElementById('fps-badge');

const dropZone          = document.getElementById('drop-zone');
const fileInput         = document.getElementById('file-input');
const progressWrap      = document.getElementById('progress-wrap');
const progressBar       = document.getElementById('progress-bar');
const progressLabel     = document.getElementById('progress-label');
const uploadVideoWrap   = document.getElementById('upload-video-wrap');
const uploadResultImg   = document.getElementById('upload-result-img');

// ── Shared state ───────────────────────────────────────────────────────
let sessionId   = null;
let currentMode = 'camera';   // 'camera' | 'upload'

// ══════════════════════════════════════════════════════════════════════
// SessionModule
// ══════════════════════════════════════════════════════════════════════
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
      await fetch(`${API_BASE}/session/${sessionId}/reset`, { method: 'POST' });
      updateHUD({ count: 0, angle: null, stage: null });
    } catch (err) {
      console.warn('[Session] reset failed:', err);
    }
  }

  return { start, reset };
})();

// ══════════════════════════════════════════════════════════════════════
// HUD helpers
// ══════════════════════════════════════════════════════════════════════
let _lastCount = 0;

function updateHUD({ count, angle, stage }) {
  // Rep count — pop animation on increment
  if (count !== undefined && count !== null) {
    if (count !== _lastCount) {
      repCount.classList.remove('pop');
      void repCount.offsetWidth;          // force reflow to re-trigger animation
      repCount.classList.add('pop');
      _lastCount = count;
    }
    repCount.textContent = count;
  }

  // Angle value + arc gauge
  if (angle !== null && angle !== undefined) {
    angleValue.textContent = Math.round(angle);
    const fraction = Math.min(angle / 180, 1);
    arcFill.style.strokeDashoffset = 172 * (1 - fraction);
  } else {
    angleValue.textContent = '—';
    arcFill.style.strokeDashoffset = 172;
  }

  // Stage badge
  stageBadge.className = 'stage-badge';
  if (stage === 'up') {
    stageBadge.textContent = 'UP';
    stageBadge.classList.add('stage-up');
  } else if (stage === 'down') {
    stageBadge.textContent = 'DOWN';
    stageBadge.classList.add('stage-down');
  } else {
    stageBadge.textContent = '—';
  }
}

function setStatus(state, label) {
  statusText.textContent = label;
  statusDot.className    = 'status-dot';
  if (state === 'active') statusDot.classList.add('active');
  if (state === 'error')  statusDot.classList.add('error');
}

// ══════════════════════════════════════════════════════════════════════
// SkeletonDrawer
// ══════════════════════════════════════════════════════════════════════
const SkeletonDrawer = (() => {

  /**
   * Draw COCO-17 keypoints + limbs on a canvas.
   * @param {CanvasRenderingContext2D} ctx
   * @param {Array<[number,number]>}   kps    keypoints at processing resolution
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

// ══════════════════════════════════════════════════════════════════════
// LiveModule — WebRTC camera + WebSocket
// ══════════════════════════════════════════════════════════════════════
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

    // 3. Off-screen canvas for capturing frames at processing resolution
    offCanvas        = document.createElement('canvas');
    offCanvas.width  = PROCESS_W;
    offCanvas.height = PROCESS_H;
    offCtx           = offCanvas.getContext('2d');

    // 4. Size the overlay canvas once metadata is available, and keep it synced
    _metaListener = () => _syncCanvasSize();
    localVideo.addEventListener('loadedmetadata', _metaListener);

    await localVideo.play();
    _syncCanvasSize();          // initial size (may be 0 if metadata not yet loaded — listener handles it)
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
      // Server closed — clean up gracefully
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
      // Fall back to CSS size
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

    // Update FPS badge every second
    fpsFrames++;
    if (ts - fpsLastTime >= 1000) {
      fpsBadge.textContent = `${fpsFrames} FPS`;
      fpsFrames   = 0;
      fpsLastTime = ts;
    }

    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (localVideo.readyState < 2) return;   // HAVE_CURRENT_DATA not yet available

    // Downscale video frame to processing resolution
    offCtx.drawImage(localVideo, 0, 0, PROCESS_W, PROCESS_H);

    // Encode as JPEG and send binary
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
    cameraPlaceholder.classList.remove('hidden');
    btnStartCamera.hidden   = false;
    btnStopCamera.hidden    = true;
    btnStartCamera.disabled = false;
    fpsBadge.textContent    = '— FPS';
    setStatus('idle', 'Idle');
    updateHUD({ count: 0, angle: null, stage: null });
    _lastCount = 0;
  }

  return { start, stop };
})();

// ══════════════════════════════════════════════════════════════════════
// UploadModule — drag-and-drop + real-time MJPEG stream display
// ══════════════════════════════════════════════════════════════════════
const UploadModule = (() => {

  // Boundary sentinel used to split MJPEG frames
  let _abortCtrl = null;   // AbortController for cancelling an in-flight upload

  async function processFile(file) {
    if (!file || !file.type.startsWith('video/')) {
      alert('Please select a video file (MP4, MOV, AVI, WebM).');
      return;
    }

    const exercise = exerciseSelect.value;

    // Reset UI
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();

    uploadVideoWrap.hidden    = true;
    progressWrap.hidden       = false;
    progressBar.style.width   = '5%';
    progressLabel.textContent = 'Uploading…';
    setStatus('active', 'Processing video…');

    const formData = new FormData();
    formData.append('file',     file);
    formData.append('exercise', exercise);

    try {
      // Animate fake upload progress
      let fakeProgress = 5;
      const ticker = setInterval(() => {
        fakeProgress = Math.min(fakeProgress + 2, 80);
        progressBar.style.width = `${fakeProgress}%`;
      }, 150);

      const res = await fetch(`${API_BASE}/upload/process`, {
        method: 'POST',
        body:   formData,
        signal: _abortCtrl.signal,
      });

      clearInterval(ticker);

      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg);
      }

      progressBar.style.width   = '90%';
      progressLabel.textContent = 'Streaming frames…';

      // Show the result container
      uploadVideoWrap.hidden = false;

      // Stream the MJPEG response body frame by frame
      await _streamMjpeg(res.body, _abortCtrl.signal);

      progressBar.style.width   = '100%';
      progressLabel.textContent = 'Done!';
      setStatus('idle', 'Done');

    } catch (err) {
      if (err.name === 'AbortError') return;
      console.error('[Upload] error:', err);
      setStatus('error', `Error: ${err.message}`);
      progressLabel.textContent = `Error: ${err.message}`;
    }
  }

  /**
   * Consume a multipart/x-mixed-replace body and render each JPEG frame
   * in uploadResultImg as it arrives — true streaming, zero buffering.
   *
   * WHY binary search: JPEG data is arbitrary bytes.  Using TextDecoder on
   * binary JPEG chunks produces corrupted strings where multi-byte UTF-8
   * replacements shift offsets, so text.indexOf() never finds the boundary.
   * We must search the raw Uint8Array bytes directly.
   *
   * MJPEG frame structure produced by the backend:
   *   --frame\r\n
   *   Content-Type: image/jpeg\r\n
   *   \r\n
   *   <JPEG bytes>
   *   \r\n
   *   --frame\r\n   (next boundary)
   *
   * @param {ReadableStream} body
   * @param {AbortSignal}    signal
   */
  async function _streamMjpeg(body, signal) {
    const reader = body.getReader();

    // Pre-encode the byte sequences we search for in the raw buffer
    const enc          = new TextEncoder();
    const SEQ_HDREND   = enc.encode('\r\n\r\n');   // end of MIME part headers
    const SEQ_BOUNDARY = enc.encode('--frame');     // MJPEG part boundary

    /** Find needle bytes inside haystack starting at `from`. Returns -1 if not found. */
    function bytesIndexOf(haystack, needle, from = 0) {
      const hLen = haystack.length;
      const nLen = needle.length;
      outer: for (let i = from; i <= hLen - nLen; i++) {
        for (let j = 0; j < nLen; j++) {
          if (haystack[i + j] !== needle[j]) continue outer;
        }
        return i;
      }
      return -1;
    }

    /** Concatenate two Uint8Arrays into a new one. */
    function concat(a, b) {
      const out = new Uint8Array(a.length + b.length);
      out.set(a, 0);
      out.set(b, a.length);
      return out;
    }

    let buffer     = new Uint8Array(0);
    let prevBlobUrl = null;

    try {
      while (true) {
        if (signal.aborted) break;

        const { value, done } = await reader.read();
        if (done) break;
        if (!value || value.length === 0) continue;

        buffer = concat(buffer, value);

        // Extract every complete JPEG frame that is now in the buffer
        while (true) {
          // 1. Find the end of the MIME part headers (\r\n\r\n)
          const hdrEnd = bytesIndexOf(buffer, SEQ_HDREND);
          if (hdrEnd === -1) break;                 // headers not fully received yet

          const dataStart = hdrEnd + SEQ_HDREND.length;

          // 2. Find the next --frame boundary that comes *after* the JPEG data
          const nextBound = bytesIndexOf(buffer, SEQ_BOUNDARY, dataStart);
          if (nextBound === -1) break;              // JPEG data not fully received yet

          // 3. JPEG bytes run from dataStart up to (but not including) the trailing
          //    \r\n that precedes the next boundary line.
          let dataEnd = nextBound;
          if (dataEnd >= 2
              && buffer[dataEnd - 2] === 0x0D  // \r
              && buffer[dataEnd - 1] === 0x0A) // \n
          {
            dataEnd -= 2;
          }

          // 4. Render the extracted frame
          const jpegBytes = buffer.slice(dataStart, dataEnd);
          const blob      = new Blob([jpegBytes], { type: 'image/jpeg' });
          const newUrl    = URL.createObjectURL(blob);

          uploadResultImg.src = newUrl;
          if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
          prevBlobUrl = newUrl;

          // 5. Advance buffer to the start of the next boundary
          buffer = buffer.slice(nextBound);
        }
      }
    } finally {
      reader.cancel().catch(() => {});
      // prevBlobUrl is intentionally kept — it holds the last rendered frame
    }
  }

  // ── Drag-and-drop wiring ──────────────────────────────────────────

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    processFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener('change', () => {
    processFile(fileInput.files[0]);
    fileInput.value = '';
  });

  // Keyboard accessibility for drop zone
  dropZone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });

  return { processFile };
})();

// ══════════════════════════════════════════════════════════════════════
// Tab switching
// ══════════════════════════════════════════════════════════════════════
function switchTab(mode) {
  currentMode = mode;

  const isCam = mode === 'camera';

  tabCamera.classList.toggle('tab--active', isCam);
  tabCamera.setAttribute('aria-selected', String(isCam));
  tabUpload.classList.toggle('tab--active', !isCam);
  tabUpload.setAttribute('aria-selected', String(!isCam));

  panelCamera.hidden = !isCam;
  panelUpload.hidden =  isCam;

  if (!isCam) LiveModule.stop();
}

tabCamera.addEventListener('click', () => switchTab('camera'));
tabUpload.addEventListener('click', () => switchTab('upload'));

// ══════════════════════════════════════════════════════════════════════
// Button wiring
// ══════════════════════════════════════════════════════════════════════
btnStartCamera.addEventListener('click', () => LiveModule.start());
btnStopCamera.addEventListener('click',  () => LiveModule.stop());
btnReset.addEventListener('click',       () => SessionModule.reset());

// Exercise change: stop current session so next Start picks the new exercise
exerciseSelect.addEventListener('change', () => {
  if (currentMode === 'camera') {
    LiveModule.stop();
    setStatus('idle', 'Exercise changed — press Start Camera');
  }
});

// ══════════════════════════════════════════════════════════════════════
// Init — fetch exercise list from server to keep dropdown in sync
// ══════════════════════════════════════════════════════════════════════
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
    }
  } catch (_) {
    // Server not up yet — use hardcoded HTML options, which is fine
  }

  setStatus('idle', 'Idle');
})();
