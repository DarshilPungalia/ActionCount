/**
 * metrics.js
 * Body metrics page — log weight/height, render line/scatter charts.
 */

let weightChart = null;
let heightChart = null;

// Set max date on the date input to today
(function initDateInput() {
  const el = document.getElementById("metric-date");
  const today = new Date().toISOString().split("T")[0];
  if (el) { el.max = today; el.value = today; }
})();

// ── Save metrics ──────────────────────────────────────────────────────────────
async function saveMetrics() {
  const dateEl   = document.getElementById("metric-date");
  const weightEl = document.getElementById("metric-weight");
  const heightEl = document.getElementById("metric-height");
  const btn      = document.getElementById("save-metrics-btn");

  const date      = dateEl.value;
  const weight_kg = parseFloat(weightEl.value) || null;
  const height_cm = parseFloat(heightEl.value) || null;

  if (!date) { showToast("Please select a date.", true); return; }
  if (!weight_kg && !height_cm) { showToast("Enter at least weight or height.", true); return; }

  const today = new Date().toISOString().split("T")[0];
  if (date > today) { showToast("Cannot log metrics for a future date.", true); return; }

  btn.disabled = true; btn.textContent = "Saving…";
  try {
    await Metrics.log(date, weight_kg, height_cm);
    showToast("✅ Metrics saved!");
    weightEl.value = "";
    heightEl.value = "";
    await loadAndRender();
  } catch (err) {
    showToast(`⚠️ ${err.message}`, true);
  } finally {
    btn.disabled = false; btn.textContent = "💾 Save Metrics";
  }
}

// ── Load & render ─────────────────────────────────────────────────────────────
async function loadAndRender() {
  try {
    const res = await Metrics.get();
    const metrics = res.metrics || [];
    renderWeightChart(metrics);
    renderHeightChart(metrics);
    renderHistory(metrics);
  } catch (err) {
    console.error("Failed to load metrics:", err);
  }
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
/**
 * Build Chart.js datasets from a list of {date, value} pairs.
 * Points ≤7 days apart are connected with lines; larger gaps are isolated dots.
 */
function buildSegmentedDatasets(pairs, color) {
  if (!pairs.length) return [];
  const datasets = [];

  let seg = [pairs[0]];
  for (let i = 1; i < pairs.length; i++) {
    const prev = new Date(pairs[i-1].date), curr = new Date(pairs[i].date);
    const gap  = (curr - prev) / 86400000;
    if (gap <= 7) {
      seg.push(pairs[i]);
    } else {
      pushSegment(datasets, seg, color);
      seg = [pairs[i]];
    }
  }
  pushSegment(datasets, seg, color);
  return datasets;
}

function pushSegment(datasets, seg, color) {
  const isLine = seg.length > 1;
  datasets.push({
    data: seg.map(p => ({ x: p.date, y: p.value })),
    borderColor: color,
    backgroundColor: color,
    borderWidth: isLine ? 2.5 : 0,
    pointRadius: isLine ? 5 : 9,
    pointHoverRadius: 9,
    showLine: isLine,
    tension: 0.35,
  });
}

function makeChartConfig(datasets, ylabel) {
  return {
    type: "scatter",
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: {
          type: "time",
          time: { unit: "day", tooltipFormat: "MMM d, yyyy", displayFormats: { day: "MMM d" } },
          grid: { display: false },
          ticks: { color: "#9ca3af", maxRotation: 30, font: { size: 11 } },
        },
        y: {
          grid: { color: "rgba(255,255,255,0.06)" },
          ticks: { color: "#6b7280", font: { size: 11 } },
          title: { display: true, text: ylabel, color: "#6b7280" },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1e293b", titleColor: "#f1f5f9", bodyColor: "#94a3b8",
          callbacks: { label: ctx => `${ctx.parsed.y} ${ylabel.split(" ")[0]}` },
        },
      },
    },
  };
}

function renderWeightChart(metrics) {
  const pairs = metrics.filter(m => m.weight_kg != null).map(m => ({ date: m.date, value: m.weight_kg }));
  const canvas  = document.getElementById("weightChart");
  const noData  = document.getElementById("noWeightData");
  if (!pairs.length) {
    if (canvas) canvas.style.display = "none";
    if (noData) noData.classList.remove("hidden");
    return;
  }
  if (noData) noData.classList.add("hidden");
  if (canvas) canvas.style.display = "block";
  if (weightChart) weightChart.destroy();
  weightChart = new Chart(canvas, makeChartConfig(buildSegmentedDatasets(pairs, "#10b981"), "kg"));
}

function renderHeightChart(metrics) {
  const pairs  = metrics.filter(m => m.height_cm != null).map(m => ({ date: m.date, value: m.height_cm }));
  const canvas  = document.getElementById("heightChart");
  const noData  = document.getElementById("noHeightData");
  if (!pairs.length) {
    if (canvas) canvas.style.display = "none";
    if (noData) noData.classList.remove("hidden");
    return;
  }
  if (noData) noData.classList.add("hidden");
  if (canvas) canvas.style.display = "block";
  if (heightChart) heightChart.destroy();
  heightChart = new Chart(canvas, makeChartConfig(buildSegmentedDatasets(pairs, "#6366f1"), "cm"));
}

function renderHistory(metrics) {
  const section = document.getElementById("historySection");
  const list    = document.getElementById("historyList");
  if (!metrics.length) { if (section) section.style.display = "none"; return; }
  section.style.display = "block";
  list.innerHTML = [...metrics].reverse().map(m => {
    const d  = new Date(m.date + "T00:00:00").toLocaleDateString("en-US", { weekday:"short", year:"numeric", month:"short", day:"numeric" });
    const wt = m.weight_kg != null ? `<span style="color:#10b981;font-weight:600;font-size:0.82rem;">⚖️ ${m.weight_kg.toFixed(1)} kg</span>` : `<span style="color:#374151;font-size:0.82rem;">⚖️ —</span>`;
    const ht = m.height_cm != null ? `<span style="color:#6366f1;font-weight:600;font-size:0.82rem;">📐 ${m.height_cm.toFixed(1)} cm</span>` : `<span style="color:#374151;font-size:0.82rem;">📐 —</span>`;
    return `<div class="history-row"><span style="color:#9ca3af;font-size:0.82rem;">${d}</span>${wt}${ht}</div>`;
  }).join("");
}

// ── Toast ──────────────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.background = isError ? "#ef4444" : "#10b981";
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3500);
}

// Chart.js date adapter (needed for time scale)
const script = document.createElement("script");
script.src = "https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js";
script.onload = () => loadAndRender();
document.head.appendChild(script);
