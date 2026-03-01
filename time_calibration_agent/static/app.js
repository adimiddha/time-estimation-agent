'use strict';

// ── Constants ──────────────────────────────────────────────────
const MIN_BLOCK_HEIGHT = 4;
const TIME_REF_RE = /\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b/i;

// ── State ──────────────────────────────────────────────────────
let nowLineInterval   = null;
let lastRangeStartMin = null;
let lastRangeEndMin   = null;
let lastTimeBlocks    = null;
let hasReplanned      = false; // show "Start fresh" after first replan

// ── Time Formatting ────────────────────────────────────────────
function padTwo(n) { return String(n).padStart(2, '0'); }

// Convert "HH:MM" to 12-hour display, with "Noon" / "Midnight" specials
function fmt12(hhmm) {
  const parts = hhmm.split(':');
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1] || '0', 10);
  if (h === 0  && m === 0) return 'Midnight';
  if (h === 12 && m === 0) return 'Noon';
  const period = h < 12 ? 'am' : 'pm';
  const h12    = h % 12 || 12;
  const mStr   = m === 0 ? '' : `:${padTwo(m)}`;
  return `${h12}${mStr}${period}`;
}

function timeToMinutes(t) {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + (m || 0);
}

function nowMinutes() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${padTwo(d.getMonth() + 1)}-${padTwo(d.getDate())}`;
}

function isTodaySession(sessionId) {
  return sessionId && sessionId.startsWith(todayStr());
}

// ── Screen Switching ───────────────────────────────────────────
function setMode(mode) {
  const shell = document.getElementById('app-shell');
  if (!shell) return;
  if (mode === 'planner') {
    shell.classList.add('mode-planner');
  } else {
    shell.classList.remove('mode-planner');
  }
}

// ── Adaptive Calendar ──────────────────────────────────────────
function computeRange(timeBlocks) {
  if (!timeBlocks || timeBlocks.length === 0) {
    const now = nowMinutes();
    return { startMin: now, endMin: now + 120 };
  }
  const starts = timeBlocks.map(b => timeToMinutes(b.start));
  const ends   = timeBlocks.map(b => timeToMinutes(b.end));
  return { startMin: Math.min(...starts), endMin: Math.max(...ends) };
}

function computeTickInterval(pixelsPerMinute) {
  for (const interval of [15, 30, 60, 120, 180, 240]) {
    if (interval * pixelsPerMinute >= 24) return interval;
  }
  return 240;
}

function getCalendarHeight() {
  const el = document.getElementById('calendar-scroll');
  return el ? Math.max(el.clientHeight, 100) : 400;
}

// ── Calendar Rendering ─────────────────────────────────────────
function renderCalendar(timeBlocks) {
  const eventsEl = document.getElementById('calendar-events');
  const axisEl   = document.getElementById('calendar-time-axis');
  const gridEl   = document.getElementById('calendar-grid');
  if (!eventsEl || !axisEl) return;

  eventsEl.innerHTML = '';
  axisEl.innerHTML   = '';

  if (!timeBlocks || timeBlocks.length === 0) {
    showCalendarEmpty();
    return;
  }

  const { startMin, endMin } = computeRange(timeBlocks);
  const totalMinutes    = Math.max(endMin - startMin, 1);
  const containerH      = getCalendarHeight();
  // Leave 20px at the bottom so the last tick label isn't clipped
  const pixelsPerMinute = (containerH - 20) / totalMinutes;

  lastRangeStartMin = startMin;
  lastRangeEndMin   = endMin;
  lastTimeBlocks    = timeBlocks;

  eventsEl.style.height = containerH + 'px';
  axisEl.style.height   = containerH + 'px';
  if (gridEl) gridEl.style.height = containerH + 'px';

  const tickInterval = computeTickInterval(pixelsPerMinute);

  // Ticks + axis labels — snapped to tick boundaries
  const firstTick = Math.ceil(startMin / tickInterval) * tickInterval;
  for (let t = firstTick; t <= endMin; t += tickInterval) {
    const topPx = (t - startMin) * pixelsPerMinute;

    const tick = document.createElement('div');
    tick.className = 'hour-tick';
    tick.style.top = topPx + 'px';
    eventsEl.appendChild(tick);

    // Minor half-tick
    if (tickInterval > 15) {
      const halfTop = topPx + (tickInterval / 2) * pixelsPerMinute;
      if (halfTop < containerH) {
        const half = document.createElement('div');
        half.className = 'hour-tick hour-tick--half';
        half.style.top = halfTop + 'px';
        eventsEl.appendChild(half);
      }
    }

    // Axis label in 12h format
    const h = Math.floor(t / 60) % 24;
    const m = t % 60;
    const label = document.createElement('div');
    label.className  = 'hour-label';
    label.style.top  = topPx + 'px';
    label.textContent = fmt12(`${padTwo(h)}:${padTwo(m)}`);
    axisEl.appendChild(label);
  }

  // Blocks
  const sorted = [...timeBlocks].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
  sorted.forEach((block, idx) => {
    const blockStartMin = timeToMinutes(block.start);
    const blockEndMin   = timeToMinutes(block.end);
    const durationMin   = Math.max(1, blockEndMin - blockStartMin);
    const top    = (blockStartMin - startMin) * pixelsPerMinute;
    const height = Math.max(MIN_BLOCK_HEIGHT, durationMin * pixelsPerMinute);
    const kind   = block.kind || 'task';

    let sizeClass = '';
    if (height < 16) sizeClass = 'calendar-block--nano';
    else if (height < 32) sizeClass = 'calendar-block--compact';

    const timeLabel = `${fmt12(block.start)}–${fmt12(block.end)}`;

    const div = document.createElement('div');
    div.className = `calendar-block calendar-block--${kind} ${sizeClass}`;
    div.style.top    = top + 'px';
    div.style.height = height + 'px';
    div.title = `${timeLabel}: ${block.task}`;
    div.style.animationDelay = `${idx * 0.045}s`;
    div.innerHTML = `
      <div class="block-time">${escHtml(timeLabel)}</div>
      <div class="block-task">${escHtml(block.task)}</div>
    `;
    eventsEl.appendChild(div);
  });

  drawNowLine(startMin, endMin, containerH, pixelsPerMinute);
}

function drawNowLine(startMin, endMin, totalHeight, ppm) {
  const eventsEl = document.getElementById('calendar-events');
  if (!eventsEl) return;
  const existing = document.getElementById('now-line');
  if (existing) existing.remove();
  const now = nowMinutes();
  if (now < startMin || now > endMin) return;
  const line = document.createElement('div');
  line.className = 'now-line';
  line.id        = 'now-line';
  line.style.top = ((now - startMin) * ppm) + 'px';
  eventsEl.appendChild(line);
}

function refreshNowLine() {
  if (lastRangeStartMin === null) return;
  const containerH   = getCalendarHeight();
  const totalMinutes = Math.max(lastRangeEndMin - lastRangeStartMin, 1);
  drawNowLine(lastRangeStartMin, lastRangeEndMin, containerH, containerH / totalMinutes);
}

// ── Calendar State Helpers ─────────────────────────────────────
function showCalendarEmpty() {
  const eventsEl = document.getElementById('calendar-events');
  const axisEl   = document.getElementById('calendar-time-axis');
  const gridEl   = document.getElementById('calendar-grid');
  if (eventsEl) {
    eventsEl.style.height = '';
    eventsEl.innerHTML = `
      <div class="calendar-empty">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
          <line x1="16" y1="2" x2="16" y2="6"></line>
          <line x1="8"  y1="2" x2="8"  y2="6"></line>
          <line x1="3"  y1="10" x2="21" y2="10"></line>
        </svg>
        <div>Planning…</div>
      </div>`;
  }
  if (axisEl) { axisEl.style.height = ''; axisEl.innerHTML = ''; }
  if (gridEl) gridEl.style.height = '';
}

function showCalendarLoading() {
  const eventsEl = document.getElementById('calendar-events');
  if (!eventsEl) return;
  eventsEl.querySelectorAll('.calendar-block').forEach(b => b.style.opacity = '0.3');
  if (!document.getElementById('calendar-overlay')) {
    const overlay = document.createElement('div');
    overlay.id = 'calendar-overlay';
    overlay.className = 'calendar-loading';
    overlay.style.cssText = 'position:absolute;inset:0;background:rgba(255,255,255,0.7);z-index:20;';
    overlay.innerHTML = '<div class="spinner"></div><span>Planning…</span>';
    eventsEl.style.position = 'relative';
    eventsEl.appendChild(overlay);
  }
}

function removeCalendarOverlay() {
  const o = document.getElementById('calendar-overlay');
  if (o) o.remove();
}

// ── Sidebar Updates ────────────────────────────────────────────
function updateSidebar(sessionId, currentTime, planOutput) {
  const metaRow = document.getElementById('meta-row');
  if (metaRow && sessionId) {
    metaRow.textContent = `${sessionId}  ·  ${fmt12(currentTime)}`;
    metaRow.style.display = '';
  }

  const conf    = planOutput.confidence || {};
  const low     = conf.low  != null ? Math.round(conf.low  * 100) : null;
  const high    = conf.high != null ? Math.round(conf.high * 100) : null;
  const confRow = document.getElementById('confidence-row');
  const confEl  = document.getElementById('confidence-value');
  const confBar = document.getElementById('confidence-bar-fill');
  if (low != null) {
    if (confRow) confRow.style.display = '';
    if (confEl)  confEl.textContent = `${low}–${high}%`;
    if (confBar) confBar.style.width = ((low + high) / 2) + '%';
  }

  const summaryEl   = document.getElementById('sidebar-summary');
  const nextEl      = document.getElementById('summary-next-actions');
  const dropEl      = document.getElementById('summary-dropped');
  const nextActions = planOutput.next_actions  || [];
  const dropDefer   = planOutput.drop_or_defer || [];

  if (nextEl) {
    nextEl.innerHTML = nextActions.length
      ? '<ul>' + nextActions.map(a => `<li>${escHtml(a)}</li>`).join('') + '</ul>'
      : '<span class="empty-note">None listed.</span>';
  }
  if (dropEl) {
    dropEl.innerHTML = dropDefer.length
      ? '<ul>' + dropDefer.map(d => `<li>${escHtml(d)}</li>`).join('') + '</ul>'
      : '<span class="empty-note">Nothing dropped.</span>';
  }
  if (summaryEl) summaryEl.style.display = '';
}

// ── Error Banners ──────────────────────────────────────────────
function showError(bannerId, msg) {
  const el = document.getElementById(bannerId);
  if (el) { el.textContent = msg; el.classList.add('visible'); }
}

function clearError(bannerId) {
  const el = document.getElementById(bannerId);
  if (el) el.classList.remove('visible');
}

// ── API: core submit ───────────────────────────────────────────
async function doSubmit({ rawContext, mode, sessionLabel, dateOverride, bannerId, submitBtn }) {
  clearError(bannerId);
  if (submitBtn) submitBtn.disabled = true;
  showCalendarLoading();

  const body = {
    context:       rawContext,
    mode:          mode,
    session_label: sessionLabel || '',
    date_override: dateOverride  || '',
  };

  try {
    const res  = await fetch('/api/plan', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    const data = await res.json();
    removeCalendarOverlay();

    if (!res.ok || data.error) {
      showError(bannerId, data.error || 'Planning failed. Please try again.');
      return null;
    }
    return data;
  } catch (e) {
    removeCalendarOverlay();
    showError(bannerId, 'Network error. Is the server running?');
    return null;
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

// ── Welcome screen submit ("Let's Plan") ──────────────────────
async function submitWelcomePlan() {
  const contextEl     = document.getElementById('context');
  const timeEl        = document.getElementById('current_time_input');
  const sessionLblEl  = document.getElementById('session_label');
  const dateOverEl    = document.getElementById('date_override');
  const planBtn       = document.getElementById('plan-btn');

  let rawContext = contextEl ? contextEl.value.trim() : '';
  if (!rawContext) {
    showError('welcome-error', 'Please enter what\'s on today.');
    return;
  }

  // Prepend current time so backend doesn't confuse deadline times with "now"
  const timeVal = timeEl ? timeEl.value.trim() : '';
  if (timeVal) {
    const [h, m] = timeVal.split(':').map(Number);
    const ampm   = h >= 12 ? 'pm' : 'am';
    const h12    = h % 12 || 12;
    const mStr   = m === 0 ? '' : `:${padTwo(m)}`;
    rawContext = `It's ${h12}${mStr}${ampm}. ${rawContext}`;
  } else if (!TIME_REF_RE.test(rawContext)) {
    showError('welcome-error', 'Please set your current time in the "Now" field or write it in your context.');
    if (timeEl) timeEl.focus();
    return;
  }

  const data = await doSubmit({
    rawContext,
    mode:          'new',
    sessionLabel:  sessionLblEl  ? sessionLblEl.value.trim()  : '',
    dateOverride:  dateOverEl    ? dateOverEl.value.trim()    : '',
    bannerId:      'welcome-error',
    submitBtn:     planBtn,
  });

  if (data) {
    setMode('planner');
    renderCalendar(data.plan_output.time_blocks);
    updateSidebar(data.session_id, data.current_time, data.plan_output);
    if (contextEl) contextEl.value = '';
  }
}

// ── Planner sidebar replan ─────────────────────────────────────
async function submitReplan() {
  const contextEl  = document.getElementById('replan-context');
  const replanBtn  = document.getElementById('replan-btn');
  const sessionEl  = document.getElementById('planner-session-label');

  const rawContext = contextEl ? contextEl.value.trim() : '';
  if (!rawContext) {
    showError('planner-error', 'Please describe what to adjust.');
    return;
  }

  const data = await doSubmit({
    rawContext,
    mode:         'replan',
    sessionLabel: sessionEl ? sessionEl.value.trim() : '',
    dateOverride: '',
    bannerId:     'planner-error',
    submitBtn:    replanBtn,
  });

  if (data) {
    renderCalendar(data.plan_output.time_blocks);
    updateSidebar(data.session_id, data.current_time, data.plan_output);
    if (contextEl) contextEl.value = '';
    // Show "Start fresh" after first successful replan
    if (!hasReplanned) {
      hasReplanned = true;
      const clearBtn = document.getElementById('clear-btn');
      if (clearBtn) clearBtn.style.display = '';
    }
  }
}

// ── Clear / Start fresh ────────────────────────────────────────
function clearDay() {
  if (!confirm('Start fresh? This will let you create a new plan for today.')) return;
  hasReplanned = false;
  const clearBtn = document.getElementById('clear-btn');
  if (clearBtn) clearBtn.style.display = 'none';
  setMode('welcome');
  // Pre-fill the time field again
  const timeInput = document.getElementById('current_time_input');
  if (timeInput) {
    const now = new Date();
    timeInput.value = `${padTwo(now.getHours())}:${padTwo(now.getMinutes())}`;
  }
}

// ── Session Load ───────────────────────────────────────────────
async function loadSession() {
  try {
    const res  = await fetch('/api/session');
    const data = await res.json();
    if (data.plan_output && data.plan_output.time_blocks && data.plan_output.time_blocks.length
        && isTodaySession(data.session_id)) {
      setMode('planner');
      renderCalendar(data.plan_output.time_blocks);
      updateSidebar(data.session_id, data.current_time, data.plan_output);
      // Show clear if multiple replans already exist
      const replans = (data.replans_count || 0);
      if (replans >= 2) {
        hasReplanned = true;
        const clearBtn = document.getElementById('clear-btn');
        if (clearBtn) clearBtn.style.display = '';
      }
    }
    // else: stay in welcome mode
  } catch (e) {
    // Stay in welcome mode on error
  }
}

// ── Escape HTML ────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Advanced Options Toggle ────────────────────────────────────
function makeAdvancedToggle(btnId, optsId) {
  const btn  = document.getElementById(btnId);
  const opts = document.getElementById(optsId);
  if (!btn || !opts) return;
  btn.addEventListener('click', () => {
    const open = opts.classList.toggle('open');
    btn.textContent = open ? 'Hide advanced options' : 'Advanced options';
  });
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Pre-fill current time
  const timeInput = document.getElementById('current_time_input');
  if (timeInput && !timeInput.value) {
    const now = new Date();
    timeInput.value = `${padTwo(now.getHours())}:${padTwo(now.getMinutes())}`;
  }

  // Load existing session (switches to planner mode if found)
  loadSession();

  // Refresh now-line every minute
  nowLineInterval = setInterval(refreshNowLine, 60_000);

  // Re-render on resize
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (lastTimeBlocks && lastTimeBlocks.length) renderCalendar(lastTimeBlocks);
    }, 150);
  });

  // Welcome screen
  const planBtn = document.getElementById('plan-btn');
  if (planBtn) planBtn.addEventListener('click', submitWelcomePlan);

  const ctxEl = document.getElementById('context');
  if (ctxEl) ctxEl.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); submitWelcomePlan(); }
  });

  makeAdvancedToggle('welcome-advanced-btn', 'welcome-advanced-opts');

  // Planner screen
  const replanBtn = document.getElementById('replan-btn');
  if (replanBtn) replanBtn.addEventListener('click', submitReplan);

  const replanCtx = document.getElementById('replan-context');
  if (replanCtx) replanCtx.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); submitReplan(); }
  });

  const clearBtn = document.getElementById('clear-btn');
  if (clearBtn) clearBtn.addEventListener('click', clearDay);

  makeAdvancedToggle('advanced-toggle-btn', 'advanced-options');
});
