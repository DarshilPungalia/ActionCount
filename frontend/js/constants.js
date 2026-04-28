/**
 * constants.js — ActionCount shared constants, DOM refs, and shared state.
 * Loaded first by index.html (plain <script>), before all other modules.
 */

'use strict';

// ── Processing constants ───────────────────────────────────────────────────────
// NOTE: API_BASE is declared in api.js (= window.location.origin) — do NOT re-declare here
const TARGET_FPS = 30;
const FRAME_MS   = 1000 / TARGET_FPS;   // ~33.33 ms
const PROCESS_W  = 640;
const PROCESS_H  = 360;

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

// ── DOM refs ───────────────────────────────────────────────────────────────────
const exerciseSelect    = document.getElementById('exercise-select');

// Stat-card panel elements
const repCount          = document.getElementById('rep-count');
const feedbackEmoji     = document.getElementById('feedback-emoji');
const feedbackText      = document.getElementById('feedback-text');
const feedbackCard      = document.getElementById('feedback-card');
const feedbackValue     = document.getElementById('feedback-value');
const progressFill      = document.getElementById('progress-fill');
const progressPctLabel  = document.getElementById('progress-pct-label');
const formStatus        = document.getElementById('form-status');
const formStatusText    = document.getElementById('form-status-text');

// Status arc + dot
const arcFill           = document.getElementById('angle-arc-fill');
const statusDot         = document.getElementById('status-dot');
const statusText        = document.getElementById('status-text');
const btnReset          = document.getElementById('btn-reset');

// Tab elements
const tabCamera         = document.getElementById('tab-camera');
const tabUpload         = document.getElementById('tab-upload');
const panelUpload       = document.getElementById('panel-upload');


// Camera panel
const localVideo        = document.getElementById('local-video');
const skeletonCanvas    = document.getElementById('skeleton-canvas');
const cameraPlaceholder = document.getElementById('camera-placeholder');
const btnStartCamera    = document.getElementById('btn-start-camera');
const btnStopCamera     = document.getElementById('btn-stop-camera');
const fpsBadge          = document.getElementById('fps-badge');

// Upload panel
const dropZone          = document.getElementById('drop-zone');
const fileInput         = document.getElementById('file-input');
const progressWrap      = document.getElementById('progress-wrap');
const progressBar       = document.getElementById('progress-bar');
const progressLabel     = document.getElementById('progress-label');
const uploadVideoWrap   = document.getElementById('upload-video-wrap');
const uploadResultImg   = document.getElementById('upload-result-img');

// ── Shared mutable state ───────────────────────────────────────────────────────
let sessionId   = null;
let currentMode = 'camera';   // 'camera' | 'upload'
