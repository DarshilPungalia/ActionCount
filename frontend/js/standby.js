/**
 * standby.js
 * ----------
 * Manages the Standby Mode for the Tracker App.
 * When active, hides the camera/controls and displays a To-Do list banner.
 * Auto-transitions to Workout Mode when the scheduled workout time arrives,
 * or when the user clicks the "Start Workout" button.
 */

(function () {
  'use strict';

  let _isWorkoutMode = false;
  let _pollInterval = null;
  let _workoutTime = null; // HH:MM
  let _hasWorkout = false;

  const StandbyMode = {
    isWorkoutMode() { return _isWorkoutMode; },

    async init() {
      // 1. Hide tracker elements immediately
      const elsToHide = ['fullscreen-camera-wrap', 'overlay-controls', 'fps-badge'];
      elsToHide.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          el.style.opacity = '0';
          el.style.pointerEvents = 'none';
        }
      });

      // 2. Add dark standby background
      const bg = document.createElement('div');
      bg.id = 'standby-bg';
      bg.style.cssText = 'position:fixed;inset:0;background:#080b16;z-index:5;transition:opacity 0.6s ease;';
      document.body.appendChild(bg);

      // 3. Fetch To-Dos and Plan
      const todayISO = new Date().toISOString().split('T')[0];
      let todos = [];
      try {
        if (window.ToDo) {
          const res = await ToDo.get(todayISO);
          todos = res.todos || [];
        }
      } catch (e) { console.warn("Failed to load To-Dos", e); }

      let plan = null;
      try {
        if (window.Plan) {
          plan = await Plan.today();
          if (plan && plan.has_plan) {
            _hasWorkout = true;
            _workoutTime = plan.workout_time;
          }
        }
      } catch (e) { console.warn("Failed to load Plan", e); }

      // If no workout plan AND no to-dos, just skip standby and go to workout mode
      if (!_hasWorkout && todos.length === 0) {
        _startWorkout(true);
        return;
      }

      // 4. Build Standby DOM
      _buildStandbyUI(todos, plan);

      // 5. Start time polling if there's a scheduled workout time
      if (_hasWorkout && _workoutTime) {
        _checkTime();
        _pollInterval = setInterval(_checkTime, 10000); // Check every 10 seconds
      }
    },

    startWorkout() {
      _startWorkout(false);
    }
  };

  function _buildStandbyUI(todos, planData) {
    const banner = document.createElement('div');
    banner.id = 'standby-todo-banner';
    // Style matches the plan_loader.js plan-banner
    banner.style.cssText =
      'position:fixed;top:165px;left:16px;z-index:65;' +
      'display:flex;flex-direction:column;align-items:stretch;' +
      'background:rgba(10,14,26,0.65);backdrop-filter:blur(10px);' +
      'border:1px solid rgba(100,200,255,0.15);border-radius:14px;' +
      'padding:14px 18px;min-width:300px;max-width:340px;' +
      'box-shadow:0 8px 32px rgba(0,0,0,0.3);' +
      'transition:opacity 0.4s ease, transform 0.4s ease;';

    // Header
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;';
    
    const title = document.createElement('div');
    title.style.cssText = 'font-size:0.75rem;font-weight:700;color:#60a5fa;text-transform:uppercase;letter-spacing:0.12em;display:flex;align-items:center;gap:6px;';
    title.innerHTML = '📋 Today\'s Schedule';
    
    header.appendChild(title);
    banner.appendChild(header);

    // List Container
    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:8px;';

    // Render To-Dos
    todos.forEach(todo => {
      const item = document.createElement('div');
      item.style.cssText = 'display:flex;align-items:flex-start;gap:10px;';
      
      const check = document.createElement('div');
      check.style.cssText = 'width:16px;height:16px;border-radius:4px;border:2px solid #4b5563;margin-top:2px;flex-shrink:0;cursor:pointer;transition:all 0.2s;';
      if (todo.completed) {
        check.style.background = '#6366f1';
        check.style.borderColor = '#6366f1';
        item.style.opacity = '0.5';
      }
      check.onclick = async () => {
        if (window.ToDo) {
          try {
            await ToDo.toggle(todo.todo_id);
            check.style.background = todo.completed ? 'transparent' : '#6366f1';
            check.style.borderColor = todo.completed ? '#4b5563' : '#6366f1';
            item.style.opacity = todo.completed ? '1' : '0.5';
            todo.completed = !todo.completed;
          } catch(e) {}
        }
      };

      const text = document.createElement('div');
      text.style.cssText = 'font-size:0.85rem;color:#e2e8f0;line-height:1.4;word-break:break-word;';
      text.textContent = todo.task;
      if (todo.time) {
        const timeBadge = document.createElement('span');
        timeBadge.style.cssText = 'font-size:0.65rem;color:#94a3b8;background:rgba(255,255,255,0.1);padding:1px 4px;border-radius:4px;margin-left:6px;';
        timeBadge.textContent = todo.time;
        text.appendChild(timeBadge);
      }

      item.appendChild(check);
      item.appendChild(text);
      list.appendChild(item);
    });

    // Render Workout Plan as a special task
    if (_hasWorkout) {
      if (todos.length > 0) {
        const divider = document.createElement('div');
        divider.style.cssText = 'height:1px;background:rgba(255,255,255,0.1);margin:4px 0;';
        list.appendChild(divider);
      }

      const workoutItem = document.createElement('div');
      workoutItem.style.cssText = 'display:flex;flex-direction:column;gap:6px;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.2);border-radius:8px;padding:10px;margin-top:4px;';
      
      const woHeader = document.createElement('div');
      woHeader.style.cssText = 'display:flex;align-items:center;justify-content:space-between;';
      
      const woTitle = document.createElement('div');
      woTitle.style.cssText = 'font-size:0.85rem;font-weight:700;color:#a5b4fc;display:flex;align-items:center;gap:6px;';
      woTitle.innerHTML = '🏋️ Workout Plan';
      
      const woTime = document.createElement('div');
      woTime.style.cssText = 'font-size:0.7rem;font-weight:600;color:#94a3b8;';
      woTime.textContent = _workoutTime ? `Starts at ${_workoutTime}` : 'Ready to start';

      woHeader.appendChild(woTitle);
      woHeader.appendChild(woTime);
      workoutItem.appendChild(woHeader);

      const woBtn = document.createElement('button');
      woBtn.style.cssText = 'background:#6366f1;color:white;border:none;border-radius:6px;padding:6px;font-size:0.8rem;font-weight:600;cursor:pointer;transition:opacity 0.2s;margin-top:4px;';
      woBtn.textContent = '▶ Start Workout Now';
      woBtn.onmouseover = () => woBtn.style.opacity = '0.8';
      woBtn.onmouseout = () => woBtn.style.opacity = '1';
      woBtn.onclick = () => _startWorkout(false);

      workoutItem.appendChild(woBtn);
      list.appendChild(workoutItem);
    }

    if (todos.length === 0 && !_hasWorkout) {
      const empty = document.createElement('div');
      empty.style.cssText = 'font-size:0.8rem;color:#94a3b8;font-style:italic;';
      empty.textContent = 'No tasks scheduled for today.';
      list.appendChild(empty);
    }

    banner.appendChild(list);
    document.body.appendChild(banner);
  }

  function _checkTime() {
    if (_isWorkoutMode || !_workoutTime) return;
    const now = new Date();
    const currentHHMM = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
    if (currentHHMM >= _workoutTime) {
       console.log(`[StandbyMode] Scheduled time (${_workoutTime}) reached. Auto-starting workout.`);
       _startWorkout(false);
    }
  }

  function _startWorkout(immediate) {
    if (_isWorkoutMode) return;
    _isWorkoutMode = true;
    if (_pollInterval) clearInterval(_pollInterval);

    // 1. Hide Standby DOM
    const banner = document.getElementById('standby-todo-banner');
    if (banner) {
      if (immediate) banner.style.display = 'none';
      else {
        banner.style.opacity = '0';
        banner.style.transform = 'translateY(-10px)';
      }
    }
    
    const bg = document.getElementById('standby-bg');
    if (bg) {
      if (immediate) bg.style.display = 'none';
      else bg.style.opacity = '0';
    }

    // 2. Show Tracker Elements
    const elsToReveal = ['fullscreen-camera-wrap', 'overlay-controls', 'fps-badge'];
    elsToReveal.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.style.opacity = '1';
        el.style.pointerEvents = 'auto';
      }
    });

    if (window.showHudStats) window.showHudStats();

    // 3. Start PlanLoader
    if (window.PlanLoader) {
       PlanLoader.init();
       if (PlanLoader.autoStart) PlanLoader.autoStart();
    }

    // 4. Cleanup
    setTimeout(() => {
      if (banner) banner.remove();
      if (bg) bg.remove();
    }, 600);
  }

  window.StandbyMode = StandbyMode;

})();
