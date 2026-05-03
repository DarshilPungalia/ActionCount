/**
 * upload.js — UploadModule: drag-and-drop video upload + MJPEG stream display.
 * Depends on: constants.js, session.js (loaded before this file).
 */

'use strict';

// ══════════════════════════════════════════════════════════════════════════════
// UploadModule
// ══════════════════════════════════════════════════════════════════════════════
const UploadModule = (() => {

  let _abortCtrl = null;    // AbortController for in-flight upload
  let _pollTimer = null;    // setInterval handle for HUD polling
  let _uploadSid = null;    // session created for this upload

  /** Start polling /session/:id every 250 ms and push data to updateHUD. */
  function _startHudPolling(sid, signal) {
    _stopHudPolling();
    _pollTimer = setInterval(async () => {
      if (signal.aborted) { _stopHudPolling(); return; }
      try {
        const r = await fetch(`${API_BASE}/session/${sid}/state`, { signal });
        if (r.ok) updateHUD(await r.json());
      } catch (_) { /* ignore — stream may have ended */ }
    }, 250);
  }

  function _stopHudPolling() {
    if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  async function processFile(file) {
    if (!file || !file.type.startsWith('video/')) {
      alert('Please select a video file (MP4, MOV, AVI, WebM).');
      return;
    }

    const exercise = exerciseSelect.value;

    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    _stopHudPolling();

    // Show progress inside the upload panel (still visible at this stage)
    uploadResultImg.style.display = 'none';
    progressWrap.hidden           = false;
    progressBar.style.width       = '5%';
    progressLabel.textContent     = 'Uploading…';
    setStatus('active', 'Processing video…');
    updateHUD({ counter: 0, feedback: 'Get in Position', progress: 0, correct_form: false });

    _uploadSid = await SessionModule.start(exercise);
    if (!_uploadSid) {
      progressLabel.textContent = 'Failed to start session';
      setStatus('error', 'Session error');
      return;
    }

    const formData = new FormData();
    formData.append('file',       file);
    formData.append('exercise',   exercise);
    formData.append('session_id', _uploadSid);

    try {
      // Fake progress 5 → 80%
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
      if (!res.ok) throw new Error(await res.text());

      // ── Switch to fullscreen view ─────────────────────────────────────────
      // Hide the upload overlay → camera wrap (with HUD + controls) becomes visible
      panelUpload.hidden            = true;
      progressWrap.hidden           = true;
      uploadResultImg.style.display = 'block';   // img is inside camera wrap
      cameraPlaceholder.classList.add('hidden'); // hide camera placeholder
      setStatus('active', 'Streaming analysis…');

      _startHudPolling(_uploadSid, _abortCtrl.signal);
      await _streamMjpeg(res.body, _abortCtrl.signal);

      _stopHudPolling();
      // Analysis done — keep last frame + HUD visible so user can Save Set
      setStatus('idle', 'Done — save your set below ↓');

    } catch (err) {
      _stopHudPolling();
      if (err.name === 'AbortError') {
        // User aborted — go back to upload panel
        _exitUploadMode();
        return;
      }
      console.error('[Upload] error:', err);
      setStatus('error', `Error: ${err.message}`);
      _exitUploadMode();
    }
  }

  /** Hide the MJPEG result and restore the upload panel. */
  function _exitUploadMode() {
    uploadResultImg.style.display = 'none';
    cameraPlaceholder.classList.remove('hidden');
    progressWrap.hidden = true;
    panelUpload.hidden  = false;
  }

  /** Called by app.js switchTab when switching back to camera tab. */
  window.uploadModuleReset = function () {
    if (_abortCtrl) _abortCtrl.abort();
    _stopHudPolling();
    _exitUploadMode();
  };



  /**
   * Consume a multipart/x-mixed-replace body and render each JPEG frame
   * in uploadResultImg as it arrives — true streaming, zero buffering.
   *
   * WHY binary search: JPEG data is arbitrary bytes. Using TextDecoder on
   * binary JPEG chunks corrupts strings where multi-byte UTF-8 replacements
   * shift offsets, so text.indexOf() never finds the boundary. We search the
   * raw Uint8Array bytes directly.
   *
   * MJPEG frame structure:
   *   --frame\r\n
   *   Content-Type: image/jpeg\r\n
   *   \r\n
   *   <JPEG bytes>
   *   \r\n
   *   --frame\r\n  (next boundary)
   */
  async function _streamMjpeg(body, signal) {
    const reader = body.getReader();

    const enc          = new TextEncoder();
    const SEQ_HDREND   = enc.encode('\r\n\r\n');
    const SEQ_BOUNDARY = enc.encode('--frame');

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

    function concat(a, b) {
      const out = new Uint8Array(a.length + b.length);
      out.set(a, 0);
      out.set(b, a.length);
      return out;
    }

    let buffer      = new Uint8Array(0);
    let prevBlobUrl = null;

    try {
      while (true) {
        if (signal.aborted) break;

        const { value, done } = await reader.read();
        if (done) break;
        if (!value || value.length === 0) continue;

        buffer = concat(buffer, value);

        while (true) {
          const hdrEnd = bytesIndexOf(buffer, SEQ_HDREND);
          if (hdrEnd === -1) break;

          const dataStart  = hdrEnd + SEQ_HDREND.length;
          const nextBound  = bytesIndexOf(buffer, SEQ_BOUNDARY, dataStart);
          if (nextBound === -1) break;

          let dataEnd = nextBound;
          if (dataEnd >= 2
              && buffer[dataEnd - 2] === 0x0D   // \r
              && buffer[dataEnd - 1] === 0x0A)  // \n
          {
            dataEnd -= 2;
          }

          const jpegBytes = buffer.slice(dataStart, dataEnd);
          const blob      = new Blob([jpegBytes], { type: 'image/jpeg' });
          const newUrl    = URL.createObjectURL(blob);

          uploadResultImg.src = newUrl;
          if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
          prevBlobUrl = newUrl;

          buffer = buffer.slice(nextBound);
        }
      }
    } finally {
      reader.cancel().catch(() => {});
    }
  }

  // ── Drag-and-drop wiring ───────────────────────────────────────────────────
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

  dropZone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });

  return { processFile };
})();
