/**
 * hud.js
 * ------
 * Three.js WebGL renderer + EffectComposer mounted as a transparent overlay
 * over #camera-video-wrap.  Exposes window.HUD for overlay.js to consume.
 *
 * Shaders are defined inline — no .glsl files needed.
 * Load order: hud.js → overlay.js (after tracker.js in index.html)
 */

(function () {
  'use strict';

  // ── Shader definitions ────────────────────────────────────────────────────

  const ChromaticShader = {
    uniforms: {
      tDiffuse: { value: null },
      uOffset:  { value: 0.003 },  // 0.001–0.006 for intensity
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D tDiffuse;
      uniform float uOffset;
      varying vec2 vUv;
      void main() {
        float r = texture2D(tDiffuse, vUv + vec2( uOffset, 0.0)).r;
        float g = texture2D(tDiffuse, vUv                      ).g;
        float b = texture2D(tDiffuse, vUv - vec2( uOffset, 0.0)).b;
        gl_FragColor = vec4(r, g, b, 1.0);
      }`,
  };

  const VignetteShader = {
    uniforms: {
      tDiffuse:  { value: null },
      uStrength: { value: 0.5  },  // 0 = none, 1 = heavy
      uSoftness: { value: 0.45 },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D tDiffuse;
      uniform float uStrength;
      uniform float uSoftness;
      varying vec2 vUv;
      void main() {
        vec4 color = texture2D(tDiffuse, vUv);
        vec2 uv = vUv * (1.0 - vUv.yx);
        float vignette = uv.x * uv.y * 15.0;
        vignette = pow(vignette, uStrength * uSoftness);
        gl_FragColor = vec4(color.rgb * vignette, color.a);
      }`,
  };

  // ── Container & canvas setup ─────────────────────────────────────────────

  const container = document.querySelector('#fullscreen-camera-wrap');
  if (!container) {
    console.warn('[HUD] #fullscreen-camera-wrap not found — HUD disabled.');
    return;
  }

  // Ensure container is positioned so absolute children work correctly
  if (getComputedStyle(container).position === 'static') {
    container.style.position = 'relative';
  }

  const canvas = document.createElement('canvas');
  canvas.id = 'hud-canvas';
  canvas.style.cssText =
    'position:absolute;top:0;left:0;width:100%;height:100%;' +
    'pointer-events:none;z-index:10;';
  container.appendChild(canvas);

  // ── Three.js renderer ────────────────────────────────────────────────────

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(0x000000, 0);   // fully transparent — video shows through

  const scene = new THREE.Scene();

  let w = container.offsetWidth  || 640;
  let h = container.offsetHeight || 360;

  const camera = new THREE.OrthographicCamera(-w / 2, w / 2, h / 2, -h / 2, 0.1, 10);
  camera.position.z = 1;

  renderer.setSize(w, h);

  // ── Post-processing chain ────────────────────────────────────────────────

  const composer    = new THREE.EffectComposer(renderer);
  const renderPass  = new THREE.RenderPass(scene, camera);
  composer.addPass(renderPass);

  const chromaPass  = new THREE.ShaderPass(ChromaticShader);
  composer.addPass(chromaPass);

  const vignettePass = new THREE.ShaderPass(VignetteShader);
  vignettePass.renderToScreen = true;
  composer.addPass(vignettePass);

  // ── Resize handler ────────────────────────────────────────────────────────

  function resize() {
    w = container.offsetWidth  || 640;
    h = container.offsetHeight || 360;
    renderer.setSize(w, h);
    composer.setSize(w, h);
    camera.left   = -w / 2;
    camera.right  =  w / 2;
    camera.top    =  h / 2;
    camera.bottom = -h / 2;
    camera.updateProjectionMatrix();
  }

  new ResizeObserver(resize).observe(container);

  // ── Render loop ───────────────────────────────────────────────────────────

  function animate() {
    requestAnimationFrame(animate);
    composer.render();
  }
  animate();

  // ── Public API ────────────────────────────────────────────────────────────

  window.HUD = { scene, camera, renderer, composer, resize };

})();
