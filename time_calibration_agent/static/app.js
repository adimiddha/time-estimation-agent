'use strict';

// ── Constants ──────────────────────────────────────────────────
const PIXELS_PER_HOUR = 64;
const PIXELS_PER_MINUTE = PIXELS_PER_HOUR / 60;
const MIN_BLOCK_HEIGHT = 28;
const COMPACT_THRESHOLD_PX = 40; // below this height, hide the time label

// Regex to detect if the user's text already mentions a time (e.g. "9am", "2:30pm", "14:00")
const TIME_REF_RE = /\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b/i;

// ── State ──────────────────────────────────────────────────────
let currentPlanTime = null; // HH:MM string — the "as of" time from the last plan
let nowLineInterval = null;

// ── Utilities ──────────────────────────────────────────────────
function timeToMinutes(t) {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + (m || 0);
}

function nowMinutes() {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function padTwo(n) {
  return String(n).padStart(2, '0');
}

// ── Calendar Rendering ─────────────────────────────────────────
function computeRange(timeBlocks) {
  if (!timeBlocks || timeBlocks.length === 0) {
    const now = nowMinutes();
    const startH = Math.max(0, Math.floor((now - 60) / 60));
    const endH = Math.min(23, startH + 10);
    return { startHour: startH, endHour: endH };
  }

  const starts = timeBlocks.map(b => timeToMinutes(b.start));
  const ends = timeBlocks.map(b => timeToMinutes(b.end));
  let minMin = Math.min(...starts);
  let maxMin = Math.max(...ends);

  // Widen to include current time if nearby
  const now = nowMinutes();
  if (now >= minMin - 120 && now <= maxMin + 120) {
    minMin = Math.min(minMin, now);
    maxMin = Math.max(maxMin, now);
  }

  const startHour = Math.max(0, Math.floor(minMin / 60));
  const endHour = Math.min(24, Math.ceil(maxMin / 60));
  return { startHour, endHour };
}

function renderCalendar(timeBlocks) {
  const eventsEl = document.getElementById('calendar-events');
  const axisEl = document.getElementById('calendar-time-axis');
  const gridEl = document.getElementById('calendar-grid');

  if (!eventsEl || !axisEl) return;

  // Clear
  eventsEl.innerHTML = '';
  axisEl.innerHTML = '';

  if (!timeBlocks || timeBlocks.length === 0) {
    showCalendarEmpty();
    return;
  }

  const { startHour, endHour } = computeRange(timeBlocks);
  const rangeStartMin = startHour * 60;
  const totalMinutes = (endHour - startHour) * 60;
  const totalHeight = totalMinutes * PIXELS_PER_MINUTE;

  eventsEl.style.height = totalHeight + 'px';
  axisEl.style.height = totalHeight + 'px';

  // Store range for refreshNowLine
  eventsEl.dataset.rangeStart = rangeStartMin;
  eventsEl.dataset.rangeMinutes = totalMinutes;

  // Hour tick marks and labels
  for (let h = startHour; h <= endHour; h++) {
    const topPx = (h * 60 - rangeStartMin) * PIXELS_PER_MINUTE;

    // Tick line in events area
    const tick = document.createElement('div');
    tick.className = 'hour-tick';
    tick.style.top = topPx + 'px';
    eventsEl.appendChild(tick);

    // Half-hour tick
    if (h < endHour) {
      const halfTick = document.createElement('div');
      halfTick.className = 'hour-tick hour-tick--half';
      halfTick.style.top = (topPx + PIXELS_PER_HOUR / 2) + 'px';
      eventsEl.appendChild(halfTick);
    }

    // Hour label in axis
    if (h < endHour) {
      const label = document.createElement('div');
      label.className = 'hour-label';
      label.style.top = topPx + 'px';
      label.textContent = padTwo(h) + ':00';
      axisEl.appendChild(label);
    }
  }

  // Calendar blocks (sorted by start time)
  const sorted = [...timeBlocks].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
  sorted.forEach((block, idx) => {
    const startMin = timeToMinutes(block.start) - rangeStartMin;
    const endMin = timeToMinutes(block.end) - rangeStartMin;
    const durationMin = Math.max(0, endMin - startMin);

    const top = startMin * PIXELS_PER_MINUTE;
    const height = Math.max(MIN_BLOCK_HEIGHT, durationMin * PIXELS_PER_MINUTE);
    const kind = block.kind || 'task';

    const isCompact = height < COMPACT_THRESHOLD_PX;
    const div = document.createElement('div');
    div.className = `calendar-block calendar-block--${kind}${isCompact ? ' calendar-block--compact' : ''}`;
    div.style.top = top + 'px';
    div.style.height = height + 'px';
    div.title = `${block.start}–${block.end}: ${block.task}`;

    const timeLabel = `${block.start}–${block.end}`;
    div.style.animationDelay = `${idx * 0.055}s`;
    div.innerHTML = `
      <div class="block-time">${escHtml(timeLabel)}</div>
      <div class="block-task">${escHtml(block.task)}</div>
    `;
    eventsEl.appendChild(div);
  });

  // "Now" line
  drawNowLine(rangeStartMin, totalHeight, totalMinutes);

  // Auto-scroll to current time (or start of blocks)
  const scrollEl = document.getElementById('calendar-scroll');
  if (scrollEl) {
    const now = nowMinutes();
    if (now >= rangeStartMin && now <= rangeStartMin + totalMinutes) {
      const nowTop = (now - rangeStartMin) * PIXELS_PER_MINUTE;
      scrollEl.scrollTop = Math.max(0, nowTop - 80);
    }
  }
}

function drawNowLine(rangeStartMin, totalHeight, totalMinutes) {
  const eventsEl = document.getElementById('calendar-events');
  if (!eventsEl) return;

  // Remove existing now-line
  const existing = document.getElementById('now-line');
  if (existing) existing.remove();

  const now = nowMinutes();
  const offsetMin = now - rangeStartMin;
  if (offsetMin < 0 || offsetMin > totalMinutes) return;

  const top = offsetMin * PIXELS_PER_MINUTE;
  const line = document.createElement('div');
  line.className = 'now-line';
  line.id = 'now-line';
  line.style.top = top + 'px';
  eventsEl.appendChild(line);
}

function refreshNowLine() {
  const eventsEl = document.getElementById('calendar-events');
  if (!eventsEl || eventsEl.style.height === '') return;
  const totalHeight = parseInt(eventsEl.style.height, 10);
  // We need the rangeStartMin — store it as a data attribute
  const rangeStartMin = parseInt(eventsEl.dataset.rangeStart || '480', 10);
  const totalMinutes = parseInt(eventsEl.dataset.rangeMinutes || '600', 10);
  drawNowLine(rangeStartMin, totalHeight, totalMinutes);
}

// ── Calendar State Helpers ─────────────────────────────────────
function showCalendarEmpty() {
  const eventsEl = document.getElementById('calendar-events');
  const axisEl = document.getElementById('calendar-time-axis');
  if (eventsEl) {
    eventsEl.style.height = '';
    eventsEl.innerHTML = `
      <div class="calendar-empty">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
          <line x1="16" y1="2" x2="16" y2="6"></line>
          <line x1="8" y1="2" x2="8" y2="6"></line>
          <line x1="3" y1="10" x2="21" y2="10"></line>
        </svg>
        <div>Enter your plan to get started</div>
      </div>`;
  }
  if (axisEl) {
    axisEl.style.height = '';
    axisEl.innerHTML = '';
  }
}

function showCalendarLoading() {
  const eventsEl = document.getElementById('calendar-events');
  if (eventsEl) {
    // Fade out existing blocks
    eventsEl.querySelectorAll('.calendar-block').forEach(b => {
      b.style.opacity = '0.3';
    });
    // Overlay spinner
    let overlay = document.getElementById('calendar-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'calendar-overlay';
      overlay.className = 'calendar-loading';
      overlay.style.cssText = 'position:absolute;inset:0;background:rgba(255,255,255,0.7);z-index:20;';
      overlay.innerHTML = '<div class="spinner"></div><span>Replanning…</span>';
      eventsEl.style.position = 'relative';
      eventsEl.appendChild(overlay);
    }
  }
}

function removeCalendarOverlay() {
  const overlay = document.getElementById('calendar-overlay');
  if (overlay) overlay.remove();
}

// ── Summary Section ────────────────────────────────────────────
function renderSummary(planOutput) {
  const panel = document.getElementById('summary-panel');
  if (!panel) return;

  const nextActions = planOutput.next_actions || [];
  const dropDefer = planOutput.drop_or_defer || [];
  const rationale = planOutput.rationale || '';

  const nextEl = document.getElementById('summary-next-actions');
  const dropEl = document.getElementById('summary-dropped');
  const rationaleEl = document.getElementById('summary-rationale');

  if (nextEl) {
    if (nextActions.length) {
      nextEl.innerHTML = '<ul>' + nextActions.map(a => `<li>${escHtml(a)}</li>`).join('') + '</ul>';
    } else {
      nextEl.innerHTML = '<span class="empty-note">No next actions listed.</span>';
    }
  }

  if (dropEl) {
    if (dropDefer.length) {
      dropEl.innerHTML = '<ul>' + dropDefer.map(d => `<li>${escHtml(d)}</li>`).join('') + '</ul>';
    } else {
      dropEl.innerHTML = '<span class="empty-note">Nothing dropped.</span>';
    }
  }

  if (rationaleEl) {
    rationaleEl.textContent = rationale;
    rationaleEl.closest('.summary-section').style.display = rationale ? '' : 'none';
  }

  panel.classList.add('visible');
}

// ── Follow-up / Sidebar Updates ────────────────────────────────
function showFollowUp(sessionId, currentTime, planOutput) {
  const section = document.getElementById('followup-section');
  if (section) section.classList.add('visible');

  // Update meta row
  const metaRow = document.getElementById('meta-row');
  if (metaRow && sessionId) {
    metaRow.textContent = `Session: ${sessionId}  ·  As of: ${currentTime}`;
    metaRow.style.display = '';
  }

  // Update confidence
  const conf = planOutput.confidence || {};
  const low = conf.low != null ? Math.round(conf.low * 100) : null;
  const high = conf.high != null ? Math.round(conf.high * 100) : null;
  const confEl = document.getElementById('confidence-value');
  const confBar = document.getElementById('confidence-bar-fill');
  if (confEl && low != null) {
    confEl.textContent = `${low}–${high}%`;
    if (confBar) confBar.style.width = ((low + high) / 2) + '%';
  }
}

// ── API Calls ──────────────────────────────────────────────────
async function loadSession() {
  try {
    const res = await fetch('/api/session');
    const data = await res.json();
    if (data.plan_output && data.plan_output.time_blocks && data.plan_output.time_blocks.length) {
      currentPlanTime = data.current_time;
      renderCalendar(data.plan_output.time_blocks);
      renderSummary(data.plan_output);
      showFollowUp(data.session_id, data.current_time, data.plan_output);
    } else {
      showCalendarEmpty();
    }
  } catch (e) {
    showCalendarEmpty();
  }
}

async function submitPlan(mode) {
  const contextEl = document.getElementById('context');
  const followupEl = document.getElementById('followup-context');
  const currentTimeEl = document.getElementById('current_time_input');
  const sessionLabelEl = document.getElementById('session_label');
  const dateOverrideEl = document.getElementById('date_override');
  const planBtn = document.getElementById('plan-btn');
  const replanBtn = document.getElementById('replan-btn');
  const errBanner = document.getElementById('error-banner');

  let rawContext = mode === 'replan'
    ? (followupEl ? followupEl.value.trim() : '')
    : (contextEl ? contextEl.value.trim() : '');

  if (!rawContext) {
    if (errBanner) {
      errBanner.textContent = 'Please enter some context before planning.';
      errBanner.classList.add('visible');
    }
    return;
  }

  // Time validation: require a time reference for new plans
  if (mode === 'new' && !TIME_REF_RE.test(rawContext)) {
    const timeVal = currentTimeEl ? currentTimeEl.value.trim() : '';
    if (!timeVal) {
      if (errBanner) {
        errBanner.textContent = 'Please set a current time — enter it in the "Current time" field or write it in your context (e.g. "It\'s 9am.").';
        errBanner.classList.add('visible');
        if (currentTimeEl) currentTimeEl.focus();
      }
      return;
    }
    // Prepend the time from the field into the context
    const [h, m] = timeVal.split(':').map(Number);
    const ampm = h >= 12 ? 'pm' : 'am';
    const h12 = h % 12 || 12;
    const timeStr = m === 0 ? `${h12}${ampm}` : `${h12}:${String(m).padStart(2,'0')}${ampm}`;
    rawContext = `It's ${timeStr}. ${rawContext}`;
  }

  if (errBanner) errBanner.classList.remove('visible');

  // Disable buttons while loading
  if (planBtn) planBtn.disabled = true;
  if (replanBtn) replanBtn.disabled = true;

  showCalendarLoading();

  const body = {
    context: rawContext,
    mode,
    session_label: sessionLabelEl ? sessionLabelEl.value.trim() : '',
    date_override: dateOverrideEl ? dateOverrideEl.value.trim() : '',
  };

  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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

    currentPlanTime = data.current_time;
    renderCalendar(data.plan_output.time_blocks);
    renderSummary(data.plan_output);
    showFollowUp(data.session_id, data.current_time, data.plan_output);

    // Clear the textarea that was just used
    if (mode === 'new' && contextEl) contextEl.value = '';
    if (mode === 'replan' && followupEl) followupEl.value = '';

  } catch (e) {
    removeCalendarOverlay();
    if (errBanner) {
      errBanner.textContent = 'Network error. Is the server running?';
      errBanner.classList.add('visible');
    }
  } finally {
    if (planBtn) planBtn.disabled = false;
    if (replanBtn) replanBtn.disabled = false;
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
  const btn = document.getElementById('advanced-toggle-btn');
  if (!opts) return;
  const open = opts.classList.toggle('open');
  if (btn) btn.textContent = open ? 'Hide advanced options' : 'Show advanced options';
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Pre-fill current time field with browser's current time
  const timeInput = document.getElementById('current_time_input');
  if (timeInput && !timeInput.value) {
    const now = new Date();
    timeInput.value = `${padTwo(now.getHours())}:${padTwo(now.getMinutes())}`;
  }

  showCalendarEmpty();
  loadSession();

  // Update "now" line every minute
  nowLineInterval = setInterval(refreshNowLine, 60_000);

  // Plan button
  const planBtn = document.getElementById('plan-btn');
  if (planBtn) planBtn.addEventListener('click', () => submitPlan('new'));

  // Replan button
  const replanBtn = document.getElementById('replan-btn');
  if (replanBtn) replanBtn.addEventListener('click', () => submitPlan('replan'));

  // Allow Ctrl/Cmd+Enter in textareas
  document.querySelectorAll('textarea').forEach(ta => {
    ta.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        const isFollowup = ta.id === 'followup-context';
        submitPlan(isFollowup ? 'replan' : 'new');
      }
    });
  });

  // Advanced toggle
  const advBtn = document.getElementById('advanced-toggle-btn');
  if (advBtn) advBtn.addEventListener('click', toggleAdvanced);
});
