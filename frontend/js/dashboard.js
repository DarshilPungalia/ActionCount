/**
 * dashboard.js — radar chart, SVG muscle heatmap, volume bar chart, updated modal with volume.
 */

let workoutHistory = {};
let muscleStats    = {};
let prevMuscleStats = {};
let volumeData     = {};
let caloriesTotalMonth = 0;
let currentDate    = new Date();
let radarChart     = null;
let volumeChart    = null;
let _svgText       = null;   // cached SVG markup
let _pathsMap      = null;   // cached paths.json {pathId: muscleName}

// ── Colour palette ─────────────────────────────────────────────────────────────
// Broad-group colours (radar + stat bars)
const MUSCLE_COLORS = {
  Arms:"#6366f1", Chest:"#ef4444", Back:"#f59e0b",
  Legs:"#10b981", Shoulders:"#3b82f6", Core:"#8b5cf6",
};
const MUSCLE_ORDER = ["Arms","Chest","Back","Legs","Shoulders","Core"];

// Single accent colour for the SVG heatmap — opacity varies with frequency
const HEATMAP_COLOR = { r: 249, g: 115, b: 22 };  // vibrant orange (#f97316)

// Fine-grained muscle names that are mapped in paths.json
const FINE_MUSCLE_NAMES = [
  "Bicep","Triceps","Forearms","Chest","Delts","Lats",
  "Traps","Rhomboids","Core","Quads","Hamstrings","Calfs","Glutes","Adductors"
];

// ── Streak helpers ──────────────────────────────────────────────────────────────
/**
 * Returns a Set of date strings ("YYYY-MM-DD") that form the current
 * active streak — the longest unbroken run of workout days ending on
 * today or yesterday (to account for users who haven't worked out yet today).
 */
function computeStreakDates(history) {
  const allDates = Object.keys(history).sort(); // ascending
  if (!allDates.length) return new Set();

  const todayMs  = new Date(fmtDate(new Date())).getTime();
  const DAY_MS   = 86400000;

  // Walk backward from today to find the streak
  let streakDates = [];
  let cursor = todayMs;

  // Allow starting from yesterday if there's no workout today
  if (!history[fmtDate(new Date(cursor))]) cursor -= DAY_MS;

  while (history[fmtDate(new Date(cursor))]) {
    streakDates.push(fmtDate(new Date(cursor)));
    cursor -= DAY_MS;
  }
  return new Set(streakDates);
}

const EXERCISE_MUSCLE_MAP = {
  "Bicep Curl":"Arms","Push-Up":"Chest","Push Up":"Chest",
  "Pull-Up":"Back","Pull Up":"Back","Squat":"Legs","Knee Press":"Legs",
  "Lateral Raise":"Shoulders","Overhead Press":"Shoulders",
  "Sit-Up":"Core","Sit Up":"Core","Crunch":"Core","Leg Raise":"Core","Knee Raise":"Core",
};

// ── Load data ─────────────────────────────────────────────────────────────────
async function loadAll() {
  const ym     = fmtYearMonth(currentDate);
  const prevDt = new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1);
  const prevYm = fmtYearMonth(prevDt);
  try {
    const [histRes, statsRes, prevStatsRes, volRes, calRes, svgRes, pathsRes] = await Promise.all([
      Workout.history(),
      Workout.stats(ym),
      Workout.stats(prevYm),
      Workout.volume(ym),
      Workout.calories(ym),
      // Fetch SVG and paths.json only once (cached after first load)
      _svgText  ? Promise.resolve({text:_svgText})  : fetch('/static/img/muscle_map.svg').then(r=>r.text()).then(t=>({text:t})),
      _pathsMap ? Promise.resolve({map:_pathsMap})  : fetch('/static/data/paths.json').then(r=>r.json()).then(m=>({map:m})),
    ]);
    workoutHistory = {};
    (histRes.history || []).forEach(d => { workoutHistory[d.date] = d.exercises; });
    muscleStats    = {};
    (statsRes.stats || []).forEach(s => { muscleStats[s.muscle_group] = s.total_sets; });
    prevMuscleStats = {};
    (prevStatsRes.stats || []).forEach(s => { prevMuscleStats[s.muscle_group] = s.total_sets; });
    volumeData = {};
    (volRes.volumes || []).forEach(v => { volumeData[v.exercise] = v.total_volume_kg; });
    caloriesTotalMonth = calRes.total_calories || 0;

    // Cache SVG and paths
    if (!_svgText)  _svgText  = svgRes.text || svgRes;
    if (!_pathsMap) _pathsMap = pathsRes.map || pathsRes;

    renderCalendar();
    renderMuscleStats();
    renderSummaryCards();
    renderRadar();
    renderHeatmap();
    renderVolumeChart();
    renderBadges();
    checkRestDayWarning();
  } catch (err) {
    console.error("Dashboard load failed:", err);
  }
}

function fmtYearMonth(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
}
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function fmtDisplayDate(s) {
  const [y,m,d] = s.split("-").map(Number);
  return new Date(y,m-1,d).toLocaleDateString("en-US",{weekday:"long",year:"numeric",month:"long",day:"numeric"});
}
function changeMonth(delta) {
  currentDate = new Date(currentDate.getFullYear(), currentDate.getMonth()+delta, 1);
  loadAll();
}

// ── Calendar ──────────────────────────────────────────────────────────────────
let _streakDates = new Set();

function renderCalendar() {
  const label = document.getElementById("calMonthLabel");
  const grid  = document.getElementById("calGrid");
  label.textContent = currentDate.toLocaleDateString("en-US",{month:"long",year:"numeric"});
  grid.innerHTML = "";

  // Compute streak from the full workout history (all-time, not month-scoped)
  _streakDates = computeStreakDates(workoutHistory);
  renderStreakBanner(_streakDates.size);

  const year=currentDate.getFullYear(), month=currentDate.getMonth(), today=fmtDate(new Date());
  const firstDay=new Date(year,month,1).getDay(), daysInMonth=new Date(year,month+1,0).getDate();
  const prevDays=new Date(year,month,0).getDate();
  for(let i=firstDay-1;i>=0;i--) grid.appendChild(makeCalDay(prevDays-i,false,true));
  for(let day=1;day<=daysInMonth;day++){
    const ds=`${year}-${String(month+1).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    grid.appendChild(makeCalDay(day,ds===today,false,!!workoutHistory[ds],ds));
  }
  const rem=(firstDay+daysInMonth)%7===0?0:7-(firstDay+daysInMonth)%7;
  for(let i=1;i<=rem;i++) grid.appendChild(makeCalDay(i,false,true));
}

function renderStreakBanner(streakLen) {
  const existing = document.getElementById("streakBanner");
  if (existing) existing.remove();
  if (streakLen < 2) return;
  const calCard = document.querySelector(".glass.p-6.anim-up.d200");
  if (!calCard) return;
  const banner = document.createElement("div");
  banner.id = "streakBanner";
  banner.style.cssText = [
    "display:flex;align-items:center;justify-content:center;gap:10px;",
    "background:linear-gradient(135deg,rgba(249,115,22,0.15),rgba(239,68,68,0.10));",
    "border:1px solid rgba(249,115,22,0.35);border-radius:0.75rem;",
    "padding:10px 16px;margin-bottom:16px;",
    "animation:fadeInUp 0.4s ease both;",
  ].join("");
  banner.innerHTML = `
    <span style="font-size:1.5rem;display:inline-block;animation:firePulse 0.75s ease-in-out infinite alternate;">🔥</span>
    <span style="font-weight:800;color:#fb923c;font-size:1rem;">${streakLen}-Day Streak!</span>
    <span style="color:#9ca3af;font-size:0.78rem;">Keep the fire alive!</span>`;
  calCard.insertBefore(banner, calCard.firstChild);
}

function makeCalDay(num, isToday, isOther, hasWorkout=false, dateStr=null) {
  const el = document.createElement("div");
  el.className = "cal-day";
  if (isToday)   el.classList.add("today");
  if (isOther)   el.classList.add("other-month");
  if (hasWorkout) el.classList.add("has-workout");

  const onStreak = !isOther && dateStr && _streakDates.has(dateStr);
  if (onStreak) el.classList.add("on-streak");

  if (onStreak) {
    el.innerHTML = `<span class="cal-day-num">${num}</span><span class="fire-emoji">🔥</span>`;
  } else {
    el.innerHTML = `<span>${num}</span>${hasWorkout ? '<span class="dot"></span>' : ""}`;
  }

  if (dateStr && hasWorkout) {
    el.addEventListener("click", () => openModal(dateStr));
    el.title = onStreak ? "🔥 Streak day! Click to see workout" : "Click to see workout";
  }
  return el;
}

// ── Muscle bars ───────────────────────────────────────────────────────────────
function renderMuscleStats() {
  const container=document.getElementById("muscleStats");
  const maxSets=Math.max(...Object.values(muscleStats),1);
  container.innerHTML="";
  MUSCLE_ORDER.forEach(muscle=>{
    const sets=muscleStats[muscle]||0, pct=Math.round((sets/maxSets)*100), color=MUSCLE_COLORS[muscle];
    container.insertAdjacentHTML("beforeend",`
      <div>
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-slate-300">${muscle}</span>
          <span class="text-xs text-slate-500">${sets} set${sets!==1?'s':''}</span>
        </div>
        <div class="stat-bar-track"><div class="stat-bar-fill" style="width:0%;background:${color}" data-target="${pct}"></div></div>
      </div>`);
  });
  requestAnimationFrame(()=>{
    container.querySelectorAll(".stat-bar-fill").forEach(b=>{ b.style.width=b.dataset.target+"%"; });
  });
}

// ── Summary cards ─────────────────────────────────────────────────────────────
function renderSummaryCards() {
  const ym=fmtYearMonth(currentDate);
  const days=Object.keys(workoutHistory).filter(d=>d.startsWith(ym));
  const totalSets=Object.values(muscleStats).reduce((a,b)=>a+b,0);
  const top=Object.entries(muscleStats).sort((a,b)=>b[1]-a[1])[0];
  const totalVol=Object.values(volumeData).reduce((a,b)=>a+b,0);
  document.getElementById("totalWorkoutDays").textContent=days.length;
  document.getElementById("totalRepsMonth").textContent=totalSets.toLocaleString();
  document.getElementById("topMuscle").textContent=top&&top[1]>0?top[0]:"—";
  // Volume card (add if element exists)
  const volEl=document.getElementById("totalVolume");
  if(volEl) volEl.textContent=totalVol.toLocaleString(undefined,{maximumFractionDigits:0})+" kg";
  // Calories card
  const calEl=document.getElementById("totalCalories");
  if(calEl) calEl.textContent=Math.round(caloriesTotalMonth).toLocaleString()+" kcal";
}

// ── Radar chart ───────────────────────────────────────────────────────────────
function renderRadar() {
  const canvas=document.getElementById("radarChart");
  const noData=document.getElementById("noRadarData");
  const hasData=MUSCLE_ORDER.some(g=>(muscleStats[g]||0)>0||(prevMuscleStats[g]||0)>0);
  if(!hasData){
    if(canvas) canvas.style.display="none";
    if(noData) noData.classList.remove("hidden");
    return;
  }
  if(noData) noData.classList.add("hidden");
  if(canvas) canvas.style.display="block";
  if(radarChart) radarChart.destroy();
  radarChart=new Chart(canvas,{
    type:"radar",
    data:{
      labels:MUSCLE_ORDER,
      datasets:[
        {label:"Previous",data:MUSCLE_ORDER.map(g=>prevMuscleStats[g]||0),
          backgroundColor:"rgba(107,114,128,0.12)",borderColor:"#6b7280",borderWidth:1.5,
          pointBackgroundColor:"#6b7280",pointRadius:3},
        {label:"Current",data:MUSCLE_ORDER.map(g=>muscleStats[g]||0),
          backgroundColor:"rgba(99,102,241,0.18)",borderColor:"#6366f1",borderWidth:2.5,
          pointBackgroundColor:"#6366f1",pointRadius:4},
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      scales:{r:{
        grid:{color:"rgba(255,255,255,0.08)"},
        angleLines:{color:"rgba(255,255,255,0.08)"},
        pointLabels:{color:"#9ca3af",font:{size:11,family:"Inter"}},
        ticks:{display:false},
      }},
      plugins:{
        legend:{position:"bottom",labels:{color:"#9ca3af",font:{size:11,family:"Inter"},boxWidth:10,padding:10}},
        tooltip:{backgroundColor:"#1e293b",titleColor:"#f1f5f9",bodyColor:"#94a3b8"},
      },
    }
  });
}

// ── SVG Muscle Heatmap ────────────────────────────────────────────────────────
function renderHeatmap() {
  const container = document.getElementById("muscleHeatmap");
  if (!container) return;

  // ── Fallback: if SVG/paths haven't loaded yet, show placeholder ──
  if (!_svgText || !_pathsMap) {
    container.innerHTML = `<div style="color:#4b5563;font-size:0.8rem;text-align:center;padding:20px;">Loading heatmap…</div>`;
    return;
  }

  // ── Compute max sets across all fine-grained muscles ──
  const maxSets = Math.max(...FINE_MUSCLE_NAMES.map(g => muscleStats[g] || 0), 1);
  const { r: hr, g: hg, b: hb } = HEATMAP_COLOR;

  // ── Inject SVG inline ──
  container.innerHTML = `
    <div id="svgWrap" style="width:100%;overflow:hidden;border-radius:10px;"></div>
    <div id="heatLegend" style="margin-top:12px;"></div>`;

  const svgWrap = document.getElementById("svgWrap");
  svgWrap.innerHTML = _svgText;
  const svgEl = svgWrap.querySelector("svg");
  if (!svgEl) return;

  svgEl.setAttribute("width", "100%");
  svgEl.removeAttribute("height");
  svgEl.setAttribute("style", "background:transparent;display:block;");

  // Silence background silhouette paths
  svgEl.querySelectorAll("path").forEach(path => {
    const fill = path.getAttribute("fill") || "";
    if (/^#F[EF][EF][A-F0-9]{2}$/i.test(fill) || fill === "none" || fill === "") {
      path.style.fill = "transparent";
    }
  });

  const REST_COLOR = "rgba(255,255,255,0.07)";

  // Apply single-colour + opacity approach
  Object.entries(_pathsMap).forEach(([pathId, muscleName]) => {
    const el = svgEl.getElementById(pathId);
    if (!el) return;
    const sets = muscleStats[muscleName] || 0;
    if (sets === 0) {
      el.style.fill = REST_COLOR;
      el.style.cursor = "default";
    } else {
      // Opacity: low-frequency = 0.20, high-frequency = 0.90
      const alpha = (0.20 + 0.70 * (sets / maxSets)).toFixed(2);
      el.style.fill = `rgba(${hr},${hg},${hb},${alpha})`;
      el.style.cursor = "pointer";
      el.addEventListener("mouseenter", function() {
        this.style.filter = `drop-shadow(0 0 6px rgba(${hr},${hg},${hb},0.8))`;
        this.style.fill   = `rgba(${hr},${hg},${hb},${Math.min(parseFloat(alpha)+0.15,1).toFixed(2)})`;
      });
      el.addEventListener("mouseleave", function() {
        this.style.filter = "";
        this.style.fill   = `rgba(${hr},${hg},${hb},${alpha})`;
      });
    }
    el.style.stroke      = "rgba(255,255,255,0.06)";
    el.style.strokeWidth = "0.5";
    el.setAttribute("title", `${muscleName}: ${sets} set${sets!==1?"s":""}`);
  });

  // ── Legend: opacity scale bar ──
  const legend = document.getElementById("heatLegend");
  const active = FINE_MUSCLE_NAMES.filter(g => (muscleStats[g] || 0) > 0);
  if (active.length === 0) {
    legend.innerHTML = `<span style="font-size:0.7rem;color:#4b5563;display:block;text-align:center;">No workouts this month</span>`;
  } else {
    // Opacity scale bar
    const scaleBar = `
      <div style="display:flex;align-items:center;gap:8px;justify-content:center;margin-bottom:8px;">
        <span style="font-size:0.65rem;color:#6b7280;">Low</span>
        <div style="width:80px;height:8px;border-radius:4px;
          background:linear-gradient(to right,
            rgba(${hr},${hg},${hb},0.20),
            rgba(${hr},${hg},${hb},0.90));"></div>
        <span style="font-size:0.65rem;color:#6b7280;">High</span>
      </div>`;
    // Active muscle chips
    const chips = active.map(g => {
      const sets = muscleStats[g] || 0;
      const alpha = (0.20 + 0.70 * (sets / maxSets)).toFixed(2);
      return `<span style="
        font-size:0.67rem;color:#d1d5db;
        background:rgba(${hr},${hg},${hb},${alpha});
        border:1px solid rgba(${hr},${hg},${hb},0.3);
        padding:2px 7px;border-radius:999px;">${g} <strong>${sets}</strong></span>`;
    }).join("");
    legend.innerHTML = scaleBar +
      `<div style="display:flex;flex-wrap:wrap;gap:5px;justify-content:center;">${chips}</div>`;
  }
}


// ── Volume bar chart ──────────────────────────────────────────────────────────
function renderVolumeChart() {
  const section=document.getElementById("volumeSection");
  const canvas=document.getElementById("volumeChart");
  if(!canvas||!section) return;
  const entries=Object.entries(volumeData).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
  if(!entries.length){ section.style.display="none"; return; }
  section.style.display="block";
  if(volumeChart) volumeChart.destroy();
  volumeChart=new Chart(canvas,{
    type:"bar",
    data:{
      labels:entries.map(([e])=>e),
      datasets:[{
        data:entries.map(([,v])=>v),
        backgroundColor:entries.map(([e])=>MUSCLE_COLORS[EXERCISE_MUSCLE_MAP[e]]||"#6366f1"),
        borderRadius:6, borderSkipped:false,
      }]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        tooltip:{backgroundColor:"#1e293b",titleColor:"#f1f5f9",bodyColor:"#94a3b8",
          callbacks:{label:ctx=>`${ctx.parsed.y.toLocaleString(undefined,{maximumFractionDigits:1})} kg`}},
      },
      scales:{
        x:{grid:{display:false},ticks:{color:"#9ca3af",font:{size:11}}},
        y:{grid:{color:"rgba(255,255,255,0.06)"},ticks:{color:"#6b7280"},
          title:{display:true,text:"Volume (kg)",color:"#6b7280"}},
      },
    }
  });
}

// ── Achievement Badges ────────────────────────────────────────────────────────
const BADGES_KEY = 'ac_earned_badges';

const BADGES = [
  {
    id:        "streak7",
    icon:      "🔥",
    label:     "On Fire",
    desc:      "7-day streak",
    fullDesc:  "Work out 7 days in a row",
    color:     "#f97316",
    glow:      "rgba(249,115,22,0.4)",
    check:     () => _streakDates.size >= 7,
    progress:  () => ({ val: Math.min(_streakDates.size, 7), max: 7 }),
  },
  {
    id:        "sets100",
    icon:      "💪",
    label:     "Iron Will",
    desc:      "100 total sets",
    fullDesc:  "Complete 100+ sets this month",
    color:     "#6366f1",
    glow:      "rgba(99,102,241,0.4)",
    check:     () => Object.values(muscleStats).reduce((a,b) => a+b, 0) >= 100,
    progress:  () => ({
      val: Math.min(Object.values(muscleStats).reduce((a,b) => a+b, 0), 100),
      max: 100,
    }),
  },
  {
    id:        "variety5",
    icon:      "🌐",
    label:     "All-Round",
    desc:      "5 muscle groups/week",
    fullDesc:  "Train 5+ muscle groups in one week",
    color:     "#10b981",
    glow:      "rgba(16,185,129,0.4)",
    check:     () => {
      const DAY_MS = 86400000;
      const todayMs = new Date(fmtDate(new Date())).getTime();
      const groups = new Set();
      for (let i = 0; i < 7; i++) {
        const ds = fmtDate(new Date(todayMs - i * DAY_MS));
        const exs = workoutHistory[ds];
        if (!exs) continue;
        Object.keys(exs).forEach(ex => {
          const g = EXERCISE_MUSCLE_MAP[ex];
          if (g) groups.add(g);
        });
      }
      return groups.size >= 5;
    },
    progress: () => {
      const DAY_MS = 86400000;
      const todayMs = new Date(fmtDate(new Date())).getTime();
      const groups = new Set();
      for (let i = 0; i < 7; i++) {
        const ds = fmtDate(new Date(todayMs - i * DAY_MS));
        const exs = workoutHistory[ds];
        if (!exs) continue;
        Object.keys(exs).forEach(ex => {
          const g = EXERCISE_MUSCLE_MAP[ex];
          if (g) groups.add(g);
        });
      }
      return { val: Math.min(groups.size, 5), max: 5 };
    },
  },
  {
    id:        "days14",
    icon:      "⚡",
    label:     "Unstoppable",
    desc:      "14-day streak",
    fullDesc:  "Work out 14 days in a row",
    color:     "#f59e0b",
    glow:      "rgba(245,158,11,0.4)",
    check:     () => _streakDates.size >= 14,
    progress:  () => ({ val: Math.min(_streakDates.size, 14), max: 14 }),
  },
];

// ── Confetti burst ────────────────────────────────────────────────────────────
function launchConfetti() {
  let canvas = document.getElementById('confetti-canvas');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.id = 'confetti-canvas';
    document.body.appendChild(canvas);
  }
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;

  const ctx      = canvas.getContext('2d');
  const COLORS   = ['#6366f1','#8b5cf6','#f97316','#10b981','#f59e0b','#ec4899','#34d399','#a5b4fc'];
  const TOTAL    = 160;
  const particles = [];

  for (let i = 0; i < TOTAL; i++) {
    particles.push({
      x:    Math.random() * canvas.width,
      y:    Math.random() * canvas.height * 0.4 - canvas.height * 0.1,
      vx:   (Math.random() - 0.5) * 6,
      vy:   Math.random() * -8 - 4,
      size: Math.random() * 8 + 4,
      rot:  Math.random() * 360,
      rspd: (Math.random() - 0.5) * 8,
      clr:  COLORS[Math.floor(Math.random() * COLORS.length)],
      life: 1,
      shape: Math.random() > 0.5 ? 'rect' : 'circle',
    });
  }

  let frame;
  function tick() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = false;
    for (const p of particles) {
      p.x  += p.vx;
      p.y  += p.vy;
      p.vy += 0.22;
      p.rot += p.rspd;
      p.life -= 0.012;
      if (p.life <= 0) continue;
      alive = true;
      ctx.globalAlpha = Math.max(0, p.life);
      ctx.fillStyle = p.clr;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot * Math.PI / 180);
      if (p.shape === 'rect') {
        ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      } else {
        ctx.beginPath();
        ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }
    ctx.globalAlpha = 1;
    if (alive) { frame = requestAnimationFrame(tick); }
    else { ctx.clearRect(0, 0, canvas.width, canvas.height); }
  }
  frame = requestAnimationFrame(tick);
  // Safety cleanup after 5s
  setTimeout(() => { cancelAnimationFrame(frame); ctx.clearRect(0, 0, canvas.width, canvas.height); }, 5000);
}

// ── Render badges ─────────────────────────────────────────────────────────────
function renderBadges() {
  const strip = document.getElementById("badgeStrip");
  if (!strip) return;

  // Load previously earned IDs from localStorage
  let prevEarned;
  try { prevEarned = new Set(JSON.parse(localStorage.getItem(BADGES_KEY) || '[]')); }
  catch (_) { prevEarned = new Set(); }

  const nowEarned = new Set();
  const newlyEarned = [];

  strip.innerHTML = '';

  BADGES.forEach((b, idx) => {
    const earned = b.check();
    if (earned) nowEarned.add(b.id);

    const prog = b.progress();
    const pct  = Math.round((prog.val / prog.max) * 100);

    const card = document.createElement('div');
    card.className = 'badge-card ' + (earned ? 'earned' : 'locked');
    card.title = b.fullDesc;

    // Unique glow color per badge when earned
    if (earned) {
      card.style.setProperty('--badge-glow', b.glow);
      card.style.borderColor = earned ? b.color.replace(')', ',0.35)').replace('rgb', 'rgba') : '';
      card.style.animation = `badgePulse 3s ease-in-out infinite`;
    }

    card.innerHTML = `
      <div class="badge-icon-wrap" style="${earned ? `filter:drop-shadow(0 0 10px ${b.glow})` : ''}">${b.icon}</div>
      <div class="badge-name" style="${earned ? `color:${b.color}` : ''}">${b.label}</div>
      <div class="badge-desc">${b.desc}</div>
      ${!earned ? `
        <div class="badge-progress" style="width:100%;">
          <div class="badge-progress-fill" id="bpf-${b.id}" style="width:0%;background:linear-gradient(90deg,${b.color},${b.glow.replace('0.4','0.8')})"></div>
        </div>
        <div class="badge-pct">${prog.val}/${prog.max}</div>
      ` : `
        <div style="font-size:0.6rem;font-weight:700;letter-spacing:0.08em;color:${b.color};opacity:0.8;text-transform:uppercase;">Unlocked ✓</div>
      `}
    `;
    strip.appendChild(card);

    // Animate progress bar fill after paint
    if (!earned) {
      requestAnimationFrame(() => {
        setTimeout(() => {
          const fill = document.getElementById(`bpf-${b.id}`);
          if (fill) fill.style.width = pct + '%';
        }, 200 + idx * 80);
      });
    }

    // Detect newly earned
    if (earned && !prevEarned.has(b.id)) {
      newlyEarned.push({ card, b });
    }
  });

  // Update count label
  const countEl = document.getElementById('badgeEarnedCount');
  if (countEl) {
    const n = nowEarned.size;
    countEl.textContent = n === 0
      ? 'None earned yet — keep going!'
      : `${n} / ${BADGES.length} earned`;
  }

  // Persist earned state
  try { localStorage.setItem(BADGES_KEY, JSON.stringify([...nowEarned])); } catch (_) {}

  // Fire confetti + pop animation for newly earned badges
  if (newlyEarned.length > 0) {
    setTimeout(() => {
      newlyEarned.forEach(({ card }) => {
        card.classList.add('new-earn');
        card.addEventListener('animationend', () => card.classList.remove('new-earn'), { once: true });
      });
      launchConfetti();
      // Toast for each new badge
      newlyEarned.forEach(({ b }) => {
        if (window.showDashboardToast) window.showDashboardToast(`🏆 Badge unlocked: ${b.label}!`);
      });
    }, 600);
  }
}

// ── Rest-Day Warning ───────────────────────────────────────────────────────────
/**
 * Check if any muscle group has been trained on 3+ consecutive days
 * ending today or yesterday. If so, show a warning popup.
 * Only shows once per dashboard load (not on month navigation).
 */
let _restDayShown = false;
function checkRestDayWarning() {
  if (_restDayShown) return;

  const MUSCLE_TO_EXERCISE = {};
  Object.entries(EXERCISE_MUSCLE_MAP).forEach(([ex, grp]) => {
    if (!MUSCLE_TO_EXERCISE[grp]) MUSCLE_TO_EXERCISE[grp] = [];
    MUSCLE_TO_EXERCISE[grp].push(ex);
  });

  const DAY_MS = 86400000;
  const todayMs = new Date(fmtDate(new Date())).getTime();
  const warned = [];

  Object.keys(MUSCLE_TO_EXERCISE).forEach(group => {
    const exNames = MUSCLE_TO_EXERCISE[group];
    let consecutive = 0;
    // Check last 4 days: if 3+ consecutive days have this group → warn
    for (let i = 0; i < 4; i++) {
      const ds = fmtDate(new Date(todayMs - i * DAY_MS));
      const exs = workoutHistory[ds];
      if (!exs) break;
      const hit = exNames.some(e => exs[e]);
      if (hit) consecutive++;
      else break;
    }
    if (consecutive >= 3) warned.push({ group, days: consecutive });
  });

  if (!warned.length) return;

  _restDayShown = true;
  const body = document.getElementById("restDayModalBody");
  const overlay = document.getElementById("rest-day-modal-overlay");
  if (!body || !overlay) return;

  body.innerHTML = warned.map(w =>
    `<div style="margin-bottom:8px;">
      <strong style="color:#f1f5f9;">${w.group}</strong> has been trained
      <strong style="color:#fb923c;">${w.days} days in a row</strong>.
      Consider giving it a rest today for optimal recovery and muscle growth.
    </div>`
  ).join("") +
  `<div style="margin-top:12px;padding:10px 14px;border-radius:8px;
    background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.18);font-size:0.8rem;color:#6b7280;">
    💡 <em>Rest days allow muscles to repair and grow stronger. Even light activity or stretching is fine.</em>
  </div>`;

  // Delay slightly so page animation plays first
  setTimeout(() => overlay.classList.add("open"), 800);
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(dateStr) {
  const exercises=workoutHistory[dateStr]||{};
  document.getElementById("modalDate").textContent=fmtDisplayDate(dateStr);
  const count=Object.keys(exercises).length;
  document.getElementById("modalSubtitle").textContent=`${count} exercise${count!==1?"s":""} performed`;
  const list=document.getElementById("modalExercises");
  list.innerHTML="";
  if(!count){
    list.innerHTML=`<p class="text-slate-500 text-sm text-center py-4">No exercises recorded.</p>`;
  } else {
    Object.entries(exercises).forEach(([ex,data],idx)=>{
      const setsArr=Array.isArray(data.sets)?data.sets:Array.from({length:data.sets||1},()=>Math.round((data.reps||0)/(data.sets||1)));
      const weightsArr=Array.isArray(data.weights)?data.weights:[];
      const totalReps=setsArr.reduce((a,b)=>a+b,0);
      const nSets=setsArr.length;
      const totalVol=setsArr.reduce((acc,r,i)=>acc+r*(weightsArr[i]||0),0);
      const volStr=totalVol>0?` · ${totalVol.toFixed(1)} kg vol`:"";
      // Per-set rows: only reps + total set volume (no formula string)
      const setRows=setsArr.map((r,i)=>{
        const w=weightsArr[i]||0;
        const setVol=w>0?` · ${(r*w).toFixed(1)} kg vol`:"";
        return `<div class="flex justify-between text-xs px-2 py-1 rounded bg-white/[0.02] mt-1">
          <span class="text-slate-500">Set ${i+1}</span>
          <span class="text-slate-300 font-semibold">${r} reps${setVol}</span></div>`;
      }).join("");
      list.insertAdjacentHTML("beforeend",`
        <div class="p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]" style="animation:fadeInUp 0.3s ease ${idx*0.06}s both;">
          <div class="flex items-center justify-between mb-2">
            <div class="text-sm font-semibold text-white">${ex}</div>
            <div class="text-right">
              <span class="text-xs font-bold text-emerald-400">${totalReps} reps</span>
            </div>
          </div>${setRows}
        </div>`);
    });
  }
  document.getElementById("workoutModal").classList.add("open");
}

function closeModal(event) {
  if(!event||event.target===document.getElementById("workoutModal"))
    document.getElementById("workoutModal").classList.remove("open");
}
document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeModal(); });

loadAll();