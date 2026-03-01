'use strict';

// ── Constants ──────────────────────────────────────────────────
const MIN_BLOCK_HEIGHT = 4; // px — minimum visible strip

// Regex to detect current-time phrases in user text
const CURRENT_TIME_RE = /\b(it'?s|current(?:ly)?|right now|as of|now it'?s)\s+\d/i;
const TIME_REF_RE = /\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b/i;

// ── State ──────────────────────────────────────────────────────
let planMode = 'new';         // 'new' | 'replan'
let nowLineInterval = null;
let lastRangeStartMin = null; // for refreshNowLine
let lastRangeEndMin   = null;
let lastTimeBlocks    = null; // for re-render on resize

// ── Utilities ──────────────────────────────────────────────────
function timeToMinutes(t) {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + (m || 0);
}

function nowMinutes() {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function padTwo(n) { return String(n).padStart(2, '0'); }

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${padTwo(d.getMonth() + 1)}-${padTwo(d.getDate())}`;
}

function isTodaySession(sessionId) {
  return sessionId && sessionId.startsWith(todayStr());
}

// ── Adaptive Calendar Scaling ───────────────────────────────────
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
  // Choose the smallest interval whose ticks are >= 24px apart
  for (const interval of [15, 30, 60, 120, 180, 240]) {
    if (interval * pixelsPerMinute >= 24) return interval;
  }
  return 240;
}

function getCalendarHeight() {
  const el = document.getElementById('calendar-scroll');
  return el ? el.clientHeight : 400;
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

  // Time range — only scheduled time, no past
  const { startMin, endMin } = computeRange(timeBlocks);
  const totalMinutes = Math.max(endMin - startMin, 1);

  // Scale to fill the available container height
  const containerH      = getCalendarHeight();
  const pixelsPerMinute = containerH / totalMinutes;
  const totalHeight     = containerH;

  // Store for now-line refresh and resize re-render
  lastRangeStartMin = startMin;
  lastRangeEndMin   = endMin;
  lastTimeBlocks    = timeBlocks;

  // Set explicit height so the grid fills the scroll container
  eventsEl.style.height = totalHeight + 'px';
  axisEl.style.height   = totalHeight + 'px';
  if (gridEl) gridEl.style.height = totalHeight + 'px';

  // Adaptive tick interval
  const tickInterval = computeTickInterval(pixelsPerMinute);

  // Draw ticks + axis labels
  // Snap start to the nearest tick boundary
  const firstTick = Math.ceil(startMin / tickInterval) * tickInterval;
  for (let t = firstTick; t <= endMin; t += tickInterval) {
    const offsetMin = t - startMin;
    const topPx = offsetMin * pixelsPerMinute;

    // Tick line across events
    const tick = document.createElement('div');
    tick.className = 'hour-tick';
    tick.style.top = topPx + 'px';
    eventsEl.appendChild(tick);

    // Half-interval minor tick (if it fits)
    const halfInterval = tickInterval / 2;
    const halfTop = topPx + halfInterval * pixelsPerMinute;
    if (halfTop < totalHeight && tickInterval > 15) {
      const half = document.createElement('div');
      half.className = 'hour-tick hour-tick--half';
      half.style.top = halfTop + 'px';
      eventsEl.appendChild(half);
    }

    // Axis label
    const h = Math.floor(t / 60) % 24;
    const m = t % 60;
    const label = document.createElement('div');
    label.className = 'hour-label';
    label.style.top = topPx + 'px';
    label.textContent = `${padTwo(h)}:${padTwo(m)}`;
    axisEl.appendChild(label);
  }

  // Render blocks
  const sorted = [...timeBlocks].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
  sorted.forEach((block, idx) => {
    const blockStartMin = timeToMinutes(block.start);
    const blockEndMin   = timeToMinutes(block.end);
    const offsetMin     = blockStartMin - startMin;
    const durationMin   = Math.max(1, blockEndMin - blockStartMin);

    const top    = offsetMin * pixelsPerMinute;
    const height = Math.max(MIN_BLOCK_HEIGHT, durationMin * pixelsPerMinute);
    const kind   = block.kind || 'task';

    // Text visibility class based on computed height
    let sizeClass = '';
    if (height < 16) sizeClass = 'calendar-block--nano';
    else if (height < 32) sizeClass = 'calendar-block--compact';

    const div = document.createElement('div');
    div.className = `calendar-block calendar-block--${kind} ${sizeClass}`;
    div.style.top    = top + 'px';
    div.style.height = height + 'px';
    div.title = `${block.start}–${block.end}: ${block.task}`;
    div.style.animationDelay = `${idx * 0.045}s`;

    div.innerHTML = `
      <div class="block-time">${escHtml(block.start)}–${escHtml(block.end)}</div>
      <div class="block-task">${escHtml(block.task)}</div>
    `;
    eventsEl.appendChild(div);
  });

  // Now line
  drawNowLine(startMin, endMin, totalHeight, pixelsPerMinute);
}

function drawNowLine(startMin, endMin, totalHeight, pixelsPerMinute) {
  const eventsEl = document.getElementById('calendar-events');
  if (!eventsEl) return;

  const existing = document.getElementById('now-line');
  if (existing) existing.remove();

  const now = nowMinutes();
  if (now < startMin || now > endMin) return;

  const top = (now - startMin) * pixelsPerMinute;
  const line = document.createElement('div');
  line.className = 'now-line';
  line.id        = 'now-line';
  line.style.top = top + 'px';
  eventsEl.appendChild(line);
}

function refreshNowLine() {
  if (lastRangeStartMin === null) return;
  const containerH = getCalendarHeight();
  const totalMinutes = Math.max(lastRangeEndMin - lastRangeStartMin, 1);
  const ppm = containerH / totalMinutes;
  drawNowLine(lastRangeStartMin, lastRangeEndMin, containerH, ppm);
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
        <div>Enter your plan to get started</div>
      </div>`;
  }
  if (axisEl) { axisEl.style.height = ''; axisEl.innerHTML = ''; }
  if (gridEl) gridEl.style.height = '';
}

function showCalendarLoading() {
  const eventsEl = document.getElementById('calendar-events');
  if (eventsEl) {
    eventsEl.querySelectorAll('.calendar-block').forEach(b => b.style.opacity = '0.3');
    let overlay = document.getElementById('calendar-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'calendar-overlay';
      overlay.className = 'calendar-loading';
      overlay.style.cssText = 'position:absolute;inset:0;background:rgba(255,255,255,0.7);z-index:20;';
      overlay.innerHTML = '<div class="spinner"></div><span>Planning…</span>';
      eventsEl.style.position = 'relative';
      eventsEl.appendChild(overlay);
    }
  }
}

function removeCalendarOverlay() {
  const overlay = document.getElementById('calendar-overlay');
  if (overlay) overlay.remove();
}

// ── Sidebar Updates ────────────────────────────────────────────
function updateSidebar(sessionId, currentTime, planOutput) {
  // Meta badge in header
  const metaRow = document.getElementById('meta-row');
  if (metaRow && sessionId) {
    metaRow.textContent = `${sessionId}  ·  ${currentTime}`;
    metaRow.style.display = '';
  }

  // Feasibility
  const conf    = planOutput.confidence || {};
  const low     = conf.low  != null ? Math.round(conf.low  * 100) : null;
  const high    = conf.high != null ? Math.round(conf.high * 100) : null;
  const confRow = document.getElementById('confidence-row');
  const confEl  = document.getElementById('confidence-value');
  const confBar = document.getElementById('confidence-bar-fill');
  if (confEl && low != null) {
    if (confRow) confRow.style.display = '';
    confEl.textContent = `${low}–${high}%`;
    if (confBar) confBar.style.width = ((low + high) / 2) + '%';
  }

  // Summary
  const summaryEl    = document.getElementById('sidebar-summary');
  const nextEl       = document.getElementById('summary-next-actions');
  const dropEl       = document.getElementById('summary-dropped');
  const nextActions  = planOutput.next_actions  || [];
  const dropDefer    = planOutput.drop_or_defer || [];

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

// ── Button Label ───────────────────────────────────────────────
function setPlanBtnLabel(mode) {
  const labelEl = document.getElementById('plan-btn-label');
  const iconEl  = document.querySelector('#plan-btn .btn-icon');
  if (mode === 'replan') {
    if (labelEl) labelEl.textContent = 'Re-plan';
    if (iconEl)  iconEl.innerHTML = '&#8635;';
  } else {
    if (labelEl) labelEl.textContent = 'Plan my day';
    if (iconEl)  iconEl.innerHTML = '&#9654;';
  }
}

// ── API Calls ──────────────────────────────────────────────────
async function loadSession() {
  try {
    const res  = await fetch('/api/session');
    const data = await res.json();
    if (data.plan_output && data.plan_output.time_blocks && data.plan_output.time_blocks.length) {
      renderCalendar(data.plan_output.time_blocks);
      updateSidebar(data.session_id, data.current_time, data.plan_output);
      if (isTodaySession(data.session_id)) {
        planMode = 'replan';
        setPlanBtnLabel('replan');
      }
    } else {
      showCalendarEmpty();
    }
  } catch (e) {
    showCalendarEmpty();
  }
}

async function submitPlan() {
  const contextEl      = document.getElementById('context');
  const currentTimeEl  = document.getElementById('current_time_input');
  const sessionLabelEl = document.getElementById('session_label');
  const dateOverrideEl = document.getElementById('date_override');
  const planBtn        = document.getElementById('plan-btn');
  const errBanner      = document.getElementById('error-banner');

  let rawContext = contextEl ? contextEl.value.trim() : '';
  if (!rawContext) {
    if (errBanner) {
      errBanner.textContent = 'Please enter some context before planning.';
      errBanner.classList.add('visible');
    }
    return;
  }

  // For new plans, prepend current time from the input field so the backend
  // has an unambiguous anchor (deadline times in text would otherwise be mistaken for "now")
  if (planMode === 'new') {
    const timeVal = currentTimeEl ? currentTimeEl.value.trim() : '';
    if (timeVal) {
      const [h, m] = timeVal.split(':').map(Number);
      const ampm = h >= 12 ? 'pm' : 'am';
      const h12  = h % 12 || 12;
      const timeStr = m === 0 ? `${h12}${ampm}` : `${h12}:${padTwo(m)}${ampm}`;
      rawContext = `It's ${timeStr}. ${rawContext}`;
    } else if (!TIME_REF_RE.test(rawContext)) {
      if (errBanner) {
        errBanner.textContent = 'Please set a current time — use the "Now" field or write it in your context (e.g. "It\'s 9am.").';
        errBanner.classList.add('visible');
        if (currentTimeEl) currentTimeEl.focus();
      }
      return;
    }
  }

  if (errBanner) errBanner.classList.remove('visible');
  if (planBtn) planBtn.disabled = true;

  showCalendarLoading();

  const body = {
    context:       rawContext,
    mode:          planMode,
    session_label: sessionLabelEl ? sessionLabelEl.value.trim() : '',
    date_override: dateOverrideEl ? dateOverrideEl.value.trim() : '',
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
      if (errBanner) {
        errBanner.textContent = data.error || 'Planning failed. Please try again.';
        errBanner.classList.add('visible');
      }
      return;
    }

    renderCalendar(data.plan_output.time_blocks);
    updateSidebar(data.session_id, data.current_time, data.plan_output);

    // Switch to replan mode after first successful plan today
    if (isTodaySession(data.session_id)) {
      planMode = 'replan';
      setPlanBtnLabel('replan');
    }

    if (contextEl) contextEl.value = '';

  } catch (e) {
    removeCalendarOverlay();
    if (errBanner) {
      errBanner.textContent = 'Network error. Is the server running?';
      errBanner.classList.add('visible');
    }
  } finally {
    if (planBtn) planBtn.disabled = false;
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
function toggleAdvanced() {
  const opts = document.getElementById('advanced-options');
  const btn  = document.getElementById('advanced-toggle-btn');
  if (!opts) return;
  const open = opts.classList.toggle('open');
  if (btn) btn.textContent = open ? 'Hide advanced options' : 'Show advanced options';
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Pre-fill current time from browser
  const timeInput = document.getElementById('current_time_input');
  if (timeInput && !timeInput.value) {
    const now = new Date();
    timeInput.value = `${padTwo(now.getHours())}:${padTwo(now.getMinutes())}`;
  }

  showCalendarEmpty();
  loadSession();

  // Refresh now-line every minute
  nowLineInterval = setInterval(refreshNowLine, 60_000);

  // Re-render calendar on window resize so adaptive scale stays correct
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (lastTimeBlocks && lastTimeBlocks.length) {
        renderCalendar(lastTimeBlocks);
      }
    }, 150);
  });

  // Plan button
  const planBtn = document.getElementById('plan-btn');
  if (planBtn) planBtn.addEventListener('click', submitPlan);

  // Ctrl/Cmd+Enter in textarea
  const contextEl = document.getElementById('context');
  if (contextEl) {
    contextEl.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        submitPlan();
      }
    });
  }

  // Advanced toggle
  const advBtn = document.getElementById('advanced-toggle-btn');
  if (advBtn) advBtn.addEventListener('click', toggleAdvanced);
});
