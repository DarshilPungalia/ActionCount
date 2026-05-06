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

// Fine-grained colours for the SVG heatmap paths
const FINE_MUSCLE_COLORS = {
  Bicep:     "#6366f1",  // indigo
  Triceps:   "#8b5cf6",  // violet
  Forearms:  "#a78bfa",  // light purple
  Chest:     "#ef4444",  // red
  Delts:     "#3b82f6",  // blue
  Lats:      "#f59e0b",  // amber
  Traps:     "#f97316",  // orange
  Rhomboids: "#fb923c",  // light orange
  Core:      "#8b5cf6",  // violet
  Quads:     "#10b981",  // emerald
  Hamstrings:"#059669",  // dark emerald
  Calfs:     "#34d399",  // light green
  Glutes:    "#06b6d4",  // cyan
  Adductors: "#0ea5e9",  // sky blue
};

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
function renderCalendar() {
  const label = document.getElementById("calMonthLabel");
  const grid  = document.getElementById("calGrid");
  label.textContent = currentDate.toLocaleDateString("en-US",{month:"long",year:"numeric"});
  grid.innerHTML = "";
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
function makeCalDay(num,isToday,isOther,hasWorkout=false,dateStr=null){
  const el=document.createElement("div"); el.className="cal-day";
  if(isToday) el.classList.add("today");
  if(isOther) el.classList.add("other-month");
  if(hasWorkout) el.classList.add("has-workout");
  el.innerHTML=`<span>${num}</span>${hasWorkout?'<span class="dot"></span>':""}`;
  if(dateStr&&hasWorkout){el.addEventListener("click",()=>openModal(dateStr)); el.title="Click to see workout";}
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
  const fineGroups = Object.keys(FINE_MUSCLE_COLORS);
  const maxSets = Math.max(...fineGroups.map(g => muscleStats[g] || 0), 1);

  // ── Inject SVG inline ──
  // Wrap in a positioned div so we can add the legend below
  container.innerHTML = `
    <div id="svgWrap" style="width:100%;overflow:hidden;border-radius:10px;"></div>
    <div id="heatLegend" style="display:flex;flex-wrap:wrap;gap:5px 10px;justify-content:center;margin-top:10px;"></div>`;

  const svgWrap = document.getElementById("svgWrap");
  svgWrap.innerHTML = _svgText;
  const svgEl = svgWrap.querySelector("svg");
  if (!svgEl) return;

  // Make SVG responsive and transparent
  svgEl.setAttribute("width", "100%");
  svgEl.removeAttribute("height");
  svgEl.style.display = "block";
  svgEl.style.background = "transparent";
  // Ensure no white page background rectangle
  svgEl.setAttribute("style", "background:transparent;display:block;");

  // ── Color each mapped path ──
  const REST_COLOR = "rgba(255,255,255,0.07)";  // dim glass look for unused muscles

  // First: set all named paths (those in paths.json) to rest color,
  //        and override any white near-white fills on non-mapped paths too
  svgEl.querySelectorAll("path").forEach(path => {
    const fill = path.getAttribute("fill") || "";
    // White/near-white fills are the background silhouette — make transparent
    if (/^#F[EF][EF][A-F0-9]{2}$/i.test(fill) || fill === "none" || fill === "") {
      path.style.fill = "transparent";
    }
  });

  // Then: apply fine-grained muscle colors
  Object.entries(_pathsMap).forEach(([pathId, muscleName]) => {
    const el = svgEl.getElementById(pathId);
    if (!el) return;
    const sets  = muscleStats[muscleName] || 0;
    const color = FINE_MUSCLE_COLORS[muscleName];
    if (!color) { el.style.fill = REST_COLOR; return; }
    if (sets === 0) {
      el.style.fill = REST_COLOR;
    } else {
      const alpha = (0.25 + 0.70 * (sets / maxSets)).toFixed(2);
      const r = parseInt(color.slice(1,3),16);
      const g = parseInt(color.slice(3,5),16);
      const b = parseInt(color.slice(5,7),16);
      el.style.fill = `rgba(${r},${g},${b},${alpha})`;
    }
    // Subtle stroke for definition
    el.style.stroke = "rgba(255,255,255,0.08)";
    el.style.strokeWidth = "0.5";
    // Tooltip on hover
    el.style.cursor = sets > 0 ? "pointer" : "default";
    el.setAttribute("title", `${muscleName}: ${sets} set${sets!==1?"s":""}`);
    if (sets > 0) {
      el.addEventListener("mouseenter", function() {
        this.style.filter = "brightness(1.4) drop-shadow(0 0 4px currentColor)";
      });
      el.addEventListener("mouseleave", function() {
        this.style.filter = "";
      });
    }
  });

  // ── Legend: only muscles with activity ──
  const legend = document.getElementById("heatLegend");
  const active = fineGroups.filter(g => (muscleStats[g] || 0) > 0);
  if (active.length === 0) {
    legend.innerHTML = `<span style="font-size:0.7rem;color:#4b5563;">No workouts this month</span>`;
  } else {
    legend.innerHTML = active.map(g => {
      const c = FINE_MUSCLE_COLORS[g] || "#6366f1";
      return `<span style="font-size:0.68rem;color:#9ca3af;display:flex;align-items:center;gap:3px;">
        <span style="width:7px;height:7px;border-radius:50%;background:${c};display:inline-block;"></span>
        ${g}: ${muscleStats[g]||0}
      </span>`;
    }).join("");
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