/**
 * dashboard.js — radar chart, SVG muscle heatmap, volume bar chart, updated modal with volume.
 */

let workoutHistory = {};
let muscleStats    = {};
let prevMuscleStats = {};
let volumeData     = {};
let currentDate    = new Date();
let radarChart     = null;
let volumeChart    = null;

const MUSCLE_COLORS = {
  Arms:"#6366f1", Chest:"#ef4444", Back:"#f59e0b",
  Legs:"#10b981", Shoulders:"#3b82f6", Core:"#8b5cf6",
};
const MUSCLE_ORDER = ["Arms","Chest","Back","Legs","Shoulders","Core"];

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
    const [histRes, statsRes, prevStatsRes, volRes] = await Promise.all([
      Workout.history(),
      Workout.stats(ym),
      Workout.stats(prevYm),
      Workout.volume(ym),
    ]);
    workoutHistory = {};
    (histRes.history || []).forEach(d => { workoutHistory[d.date] = d.exercises; });
    muscleStats    = {};
    (statsRes.stats || []).forEach(s => { muscleStats[s.muscle_group] = s.total_sets; });
    prevMuscleStats = {};
    (prevStatsRes.stats || []).forEach(s => { prevMuscleStats[s.muscle_group] = s.total_sets; });
    volumeData = {};
    (volRes.volumes || []).forEach(v => { volumeData[v.exercise] = v.total_volume_kg; });

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
  const container=document.getElementById("muscleHeatmap");
  if(!container) return;
  const maxSets=Math.max(...MUSCLE_ORDER.map(g=>muscleStats[g]||0),1);
  function col(muscle){
    const v=muscleStats[muscle]||0;
    if(!v) return "rgba(255,255,255,0.06)";
    const alpha=(0.25+0.65*(v/maxSets)).toFixed(2);
    const hex=MUSCLE_COLORS[muscle]||"#6366f1";
    const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  const arms=col("Arms"),chest=col("Chest"),back=col("Back"),legs=col("Legs"),shold=col("Shoulders"),core=col("Core");
  container.innerHTML=`
<div style="display:flex;justify-content:center;gap:20px;">
<div style="text-align:center;"><div style="font-size:0.6rem;color:#4b5563;margin-bottom:4px;letter-spacing:.08em;">FRONT</div>
<svg viewBox="0 0 120 260" width="90" height="200" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="22" rx="16" ry="19" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
  <ellipse cx="30" cy="58" rx="16" ry="10" fill="${shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <ellipse cx="90" cy="58" rx="16" ry="10" fill="${shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="38" y="48" width="44" height="38" rx="6" fill="${chest}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="40" y="88" width="40" height="44" rx="5" fill="${core}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="13" y="55" width="15" height="42" rx="7" fill="${arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="92" y="55" width="15" height="42" rx="7" fill="${arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="10" y="99" width="13" height="36" rx="6" fill="${arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
  <rect x="97" y="99" width="13" height="36" rx="6" fill="${arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
  <rect x="40" y="134" width="17" height="58" rx="8" fill="${legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="63" y="134" width="17" height="58" rx="8" fill="${legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="41" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  <rect x="65" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
</svg></div>
<div style="text-align:center;"><div style="font-size:0.6rem;color:#4b5563;margin-bottom:4px;letter-spacing:.08em;">BACK</div>
<svg viewBox="0 0 120 260" width="90" height="200" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="22" rx="16" ry="19" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
  <ellipse cx="30" cy="58" rx="16" ry="10" fill="${shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <ellipse cx="90" cy="58" rx="16" ry="10" fill="${shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="34" y="48" width="52" height="50" rx="6" fill="${back}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="40" y="98" width="40" height="34" rx="5" fill="${back}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="13" y="55" width="15" height="42" rx="7" fill="${arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="92" y="55" width="15" height="42" rx="7" fill="${arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="10" y="99" width="13" height="36" rx="6" fill="${arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
  <rect x="97" y="99" width="13" height="36" rx="6" fill="${arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
  <rect x="40" y="134" width="17" height="58" rx="8" fill="${legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="63" y="134" width="17" height="58" rx="8" fill="${legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
  <rect x="41" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  <rect x="65" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
</svg></div></div>
<div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:8px;">
${MUSCLE_ORDER.map(g=>`<span style="font-size:0.68rem;color:#9ca3af;display:flex;align-items:center;gap:3px;"><span style="width:7px;height:7px;border-radius:50%;background:${MUSCLE_COLORS[g]};display:inline-block;"></span>${g}: ${muscleStats[g]||0}</span>`).join("")}
</div>`;
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
      const setRows=setsArr.map((r,i)=>{
        const w=weightsArr[i]||0;
        const ws=w>0?` @ ${w.toFixed(1)}kg`:"";
        const vs=w>0?` = ${(r*w).toFixed(1)}kg vol`:"";
        return `<div class="flex justify-between text-xs px-2 py-1 rounded bg-white/[0.02] mt-1">
          <span class="text-slate-500">Set ${i+1}</span>
          <span class="text-slate-300 font-semibold">${r} reps${ws}${vs}</span></div>`;
      }).join("");
      list.insertAdjacentHTML("beforeend",`
        <div class="p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]" style="animation:fadeInUp 0.3s ease ${idx*0.06}s both;">
          <div class="flex items-center justify-between mb-2">
            <div class="text-sm font-semibold text-white">${ex}</div>
            <div class="text-right">
              <span class="text-xs font-bold text-emerald-400">${nSets} set${nSets!==1?"s":""}</span>
              <span class="text-xs text-slate-500 ml-1">· ${totalReps} reps${volStr}</span>
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