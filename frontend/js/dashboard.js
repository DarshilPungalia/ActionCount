/**
 * dashboard.js
 * Workout calendar, monthly muscle stats, and workout detail modal.
 */

// ── Auth guard ────────────────────────────────────────────────────────────────
if (!requireAuth()) throw new Error("Unauthenticated");
document.getElementById("usernameTag").textContent = Auth.username();

// ── State ─────────────────────────────────────────────────────────────────────
let workoutHistory = {};   // { "YYYY-MM-DD": { "Exercise": {reps, sets} } }
let muscleStats    = {};   // { "Arms": 120, "Chest": 80, ... }
let currentDate    = new Date();
let muscleChart    = null;

const MUSCLE_COLORS = {
  Arms:      "#6366f1",
  Chest:     "#ef4444",
  Back:      "#f59e0b",
  Legs:      "#10b981",
  Shoulders: "#3b82f6",
  Core:      "#8b5cf6",
};

// ── Load data ─────────────────────────────────────────────────────────────────
async function loadAll() {
  try {
    const [histRes, statsRes] = await Promise.all([
      Workout.history(),
      Workout.stats(fmtYearMonth(currentDate)),
    ]);

    // Build a flat lookup: { "YYYY-MM-DD": {...exercises} }
    workoutHistory = {};
    (histRes.history || []).forEach((day) => {
      workoutHistory[day.date] = day.exercises;
    });

    // Muscle stats
    muscleStats = {};
    (statsRes.stats || []).forEach((s) => {
      muscleStats[s.muscle_group] = s.total_reps;
    });

    renderCalendar();
    renderMuscleStats();
    renderSummaryCards();
  } catch (err) {
    console.error("Failed to load dashboard data:", err);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtYearMonth(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function fmtDisplayDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
}

// ── Month navigation ──────────────────────────────────────────────────────────
function changeMonth(delta) {
  currentDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + delta, 1);
  loadAll();
}

// ── Calendar ──────────────────────────────────────────────────────────────────
function renderCalendar() {
  const label = document.getElementById("calMonthLabel");
  const grid  = document.getElementById("calGrid");

  label.textContent = currentDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  grid.innerHTML = "";

  const year  = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const today = fmtDate(new Date());

  // First cell = first day of month; pad with previous month's days
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  // Prev month filler
  const prevDays = new Date(year, month, 0).getDate();
  for (let i = firstDay - 1; i >= 0; i--) {
    const d = makeCalDay(prevDays - i, false, true);
    grid.appendChild(d);
  }

  // Current month days
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr   = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const hasData   = !!workoutHistory[dateStr];
    const isToday   = dateStr === today;
    const el        = makeCalDay(day, isToday, false, hasData, dateStr);
    grid.appendChild(el);
  }

  // Next month filler
  const totalCells = firstDay + daysInMonth;
  const remainder  = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
  for (let i = 1; i <= remainder; i++) {
    grid.appendChild(makeCalDay(i, false, true));
  }
}

function makeCalDay(num, isToday, isOther, hasWorkout = false, dateStr = null) {
  const el = document.createElement("div");
  el.className = "cal-day";
  if (isToday)    el.classList.add("today");
  if (isOther)    el.classList.add("other-month");
  if (hasWorkout) el.classList.add("has-workout");

  el.innerHTML = `<span>${num}</span>${hasWorkout ? '<span class="dot"></span>' : ""}`;

  if (dateStr && hasWorkout) {
    el.addEventListener("click", () => openModal(dateStr));
    el.title = "Click to see workout";
  }
  return el;
}

// ── Muscle stats sidebar ──────────────────────────────────────────────────────
function renderMuscleStats() {
  const container = document.getElementById("muscleStats");
  const hasData   = Object.values(muscleStats).some((v) => v > 0);
  const maxReps   = Math.max(...Object.values(muscleStats), 1);

  container.innerHTML = "";

  const order = ["Arms", "Chest", "Back", "Legs", "Shoulders", "Core"];
  order.forEach((muscle) => {
    const reps  = muscleStats[muscle] || 0;
    const pct   = Math.round((reps / maxReps) * 100);
    const color = MUSCLE_COLORS[muscle] || "#6366f1";

    container.insertAdjacentHTML("beforeend", `
      <div>
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-slate-300">${muscle}</span>
          <span class="text-xs text-slate-500">${reps} reps</span>
        </div>
        <div class="stat-bar-track">
          <div class="stat-bar-fill" style="width:0%;background:${color}" data-target="${pct}"></div>
        </div>
      </div>
    `);
  });

  // Animate bars after insert
  requestAnimationFrame(() => {
    container.querySelectorAll(".stat-bar-fill").forEach((bar) => {
      bar.style.width = bar.dataset.target + "%";
    });
  });

  // Doughnut chart
  renderDoughnut(hasData);
}

function renderDoughnut(hasData) {
  const noData = document.getElementById("noChartData");
  const canvas = document.getElementById("muscleChart");

  if (!hasData) {
    canvas.style.display = "none";
    noData.classList.remove("hidden");
    return;
  }

  canvas.style.display = "block";
  noData.classList.add("hidden");

  const labels = Object.keys(muscleStats).filter((k) => muscleStats[k] > 0);
  const values = labels.map((k) => muscleStats[k]);
  const colors = labels.map((k) => MUSCLE_COLORS[k] || "#6366f1");

  if (muscleChart) muscleChart.destroy();

  muscleChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: "#111827", hoverOffset: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: "#94a3b8", font: { size: 11, family: "Inter" }, padding: 10, boxWidth: 10 } },
        tooltip: { backgroundColor: "#1e293b", titleColor: "#f1f5f9", bodyColor: "#94a3b8" },
      },
      cutout: "65%",
    },
  });
}

// ── Summary cards ─────────────────────────────────────────────────────────────
function renderSummaryCards() {
  const ym = fmtYearMonth(currentDate);
  const daysThisMonth = Object.keys(workoutHistory).filter((d) => d.startsWith(ym));
  const totalReps = Object.values(muscleStats).reduce((a, b) => a + b, 0);
  const topMuscle = Object.entries(muscleStats).sort((a, b) => b[1] - a[1])[0];

  document.getElementById("totalWorkoutDays").textContent = daysThisMonth.length;
  document.getElementById("totalRepsMonth").textContent  = totalReps.toLocaleString();
  document.getElementById("topMuscle").textContent       = topMuscle && topMuscle[1] > 0 ? topMuscle[0] : "—";
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(dateStr) {
  const exercises = workoutHistory[dateStr] || {};
  const modal     = document.getElementById("workoutModal");

  document.getElementById("modalDate").textContent = fmtDisplayDate(dateStr);
  const count = Object.keys(exercises).length;
  document.getElementById("modalSubtitle").textContent =
    `${count} exercise${count !== 1 ? "s" : ""} performed`;

  const list = document.getElementById("modalExercises");
  list.innerHTML = "";

  if (count === 0) {
    list.innerHTML = `<p class="text-slate-500 text-sm text-center py-4">No exercises recorded.</p>`;
  } else {
    Object.entries(exercises).forEach(([ex, data], idx) => {
      list.insertAdjacentHTML("beforeend", `
        <div class="flex items-center justify-between p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]"
             style="animation:fadeInUp 0.3s ease ${idx * 0.06}s both;">
          <div>
            <div class="text-sm font-semibold text-white">${ex}</div>
            <div class="text-xs text-slate-500 mt-0.5">${data.sets} set${data.sets !== 1 ? "s" : ""}</div>
          </div>
          <div class="text-right">
            <div class="text-lg font-extrabold text-emerald-400">${data.reps}</div>
            <div class="text-xs text-slate-500">reps</div>
          </div>
        </div>
      `);
    });
  }

  modal.classList.add("open");
}

function closeModal(event) {
  if (!event || event.target === document.getElementById("workoutModal")) {
    document.getElementById("workoutModal").classList.remove("open");
  }
}

// Close modal on Escape key
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// ── Init ──────────────────────────────────────────────────────────────────────
loadAll();
