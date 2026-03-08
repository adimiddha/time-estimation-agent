'use strict';

// ── Constants ──────────────────────────────────────────────────
const PIXELS_PER_HOUR = 120;
const PIXELS_PER_MINUTE = PIXELS_PER_HOUR / 60;
const MIN_BLOCK_HEIGHT = 48;   // was 20 — enough for time + task label + padding
const COMPACT_THRESHOLD_PX = 0; // was 40 — disable compact mode; all blocks show both labels

// ── Debug Static Data (computed at call time so blocks start from now) ─
function makeDebugPlanData() {
  const p = n => String(n).padStart(2, '0');
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  // Round up to next 15-min boundary for a clean start
  const startMin = Math.ceil(nowMin / 15) * 15;
  const t = delta => {
    const m = startMin + delta;
    return `${p(Math.floor(m / 60) % 24)}:${p(m % 60)}`;
  };
  const dateStr = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
  return {
    session_id: dateStr,
    current_time: `${p(now.getHours())}:${p(now.getMinutes())}`,
    phase: 'draft',
    plan_output: {
      time_blocks: [
        { start: t(0),   end: t(30),  task: 'Kick-off sync',                  kind: 'task'  },
        { start: t(30),  end: t(40),  task: 'Break',                           kind: 'break' },
        { start: t(40),  end: t(130), task: 'Write quarterly review doc',       kind: 'task'  },
        { start: t(130), end: t(140), task: 'Short break',                      kind: 'break' },
        { start: t(140), end: t(200), task: 'Review pull requests',             kind: 'task'  },
        { start: t(200), end: t(260), task: 'Deep work: refactor auth module',  kind: 'task'  },
        { start: t(260), end: t(270), task: 'Break',                            kind: 'break' },
        { start: t(270), end: t(330), task: 'Respond to emails & Slack',        kind: 'task'  },
        { start: t(330), end: t(360), task: 'Wrap up & plan tomorrow',          kind: 'task'  },
      ],
      next_actions: [
        'Write quarterly review doc by EOD',
        'Merge the auth module PR after review',
        'Sync with Alex on API design',
      ],
      drop_or_defer: [
        'Update team wiki (defer to next week)',
        'Read v3 design specs (low priority today)',
      ],
      rationale: 'Prioritized deep work blocks with short breaks in between. Wiki update deferred — it can wait without blocking anything.',
      confidence: { low: 0.72, high: 0.88 },
    },
  };
}

// ── State ──────────────────────────────────────────────────────
let currentPlanTime = null;
let nowLineInterval = null;
let currentTimeHHMM = null;  // live clock value, updated every 30s
let brainDumpText = '';       // saved between screens
let currentFollowUpType = null;   // "end_time" | "ordering" | null
let currentFollowUpEndTime = null; // HH:MM from first clarify call, for "ordering" path
let currentSessionId = null;  // active session ID
let isDraftMode = false;       // true while phase=draft (pre-approve)
let currentTimeBlocks = [];   // latest rendered blocks (with steps)

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

function fmt12(totalMinutes) {
  const h = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  if (h === 0 && m === 0) return 'Midnight';
  if (h === 12 && m === 0) return 'Noon';
  const period = h >= 12 ? 'pm' : 'am';
  const h12 = h % 12 || 12;
  return m === 0 ? `${h12}${period}` : `${h12}:${padTwo(m)}${period}`;
}

function nowHHMM() {
  const now = new Date();
  return `${padTwo(now.getHours())}:${padTwo(now.getMinutes())}`;
}

// ── Live Clock ─────────────────────────────────────────────────
function initClock() {
  const el = document.getElementById('live-clock-time');
  function tick() {
    const now = new Date();
    currentTimeHHMM = `${padTwo(now.getHours())}:${padTwo(now.getMinutes())}`;
    const timeStr = fmt12(now.getHours() * 60 + now.getMinutes());
    if (el) el.textContent = timeStr;
    // Update in-calendar time display
    const calEl = document.getElementById('calendar-time-display');
    if (calEl) calEl.textContent = `it\u2019s ${timeStr}`;
  }
  tick();
  setInterval(tick, 30_000);
}

// ── Progress Bar ───────────────────────────────────────────────
let progressTimer = null;

function animateProgressBar(onComplete) {
  const bar = document.getElementById('progress-bar');
  const label = document.getElementById('progress-label');
  if (!bar || !label) return;

  const stages = [
    { pct: 20,  dur: 1000,  text: 'Untangling your day\u2026' },
    { pct: 70,  dur: 8000,  text: 'Estimating task durations\u2026' },
    { pct: 95,  dur: 4000,  text: 'Building your schedule\u2026' },
  ];

  let stageIdx = 0;

  function runStage() {
    if (stageIdx >= stages.length) return;
    const { pct, dur, text } = stages[stageIdx];
    bar.style.transition = `width ${dur}ms ease-in-out`;
    bar.style.width = pct + '%';
    label.textContent = text;
    stageIdx++;
    progressTimer = setTimeout(runStage, dur);
  }

  bar.style.transition = 'none';
  bar.style.width = '0%';
  // Tiny delay so the 0% reset renders before animation starts
  requestAnimationFrame(() => requestAnimationFrame(runStage));

  // Return a function to snap to 100% when done
  return function snapDone() {
    if (progressTimer) clearTimeout(progressTimer);
    bar.style.transition = 'width 0.4s ease-in-out';
    bar.style.width = '100%';
    if (label) label.textContent = 'Done!';
    if (onComplete) setTimeout(onComplete, 450);
  };
}

// ── Welcome Overlay Transitions ────────────────────────────────
function showScreen(id) {
  ['brain-dump-screen', 'followup-clarify-screen', 'loading-screen'].forEach(sid => {
    const el = document.getElementById(sid);
    if (el) el.style.display = sid === id ? '' : 'none';
  });
}

function hideOverlay() {
  const overlay = document.getElementById('welcome-overlay');
  const shell = document.getElementById('app-shell');
  if (overlay) {
    overlay.style.transition = 'opacity 0.4s ease';
    overlay.style.opacity = '0';
    setTimeout(() => { overlay.style.display = 'none'; }, 400);
  }
  if (shell) shell.style.display = '';
}

// ── Draft Scroll-to-Reveal ─────────────────────────────────────
function initDraftScrollVisibility() {
  const calScroll = document.getElementById('calendar-scroll');
  const scrollArea = document.querySelector('.draft-scroll-area');
  if (!calScroll || !scrollArea) return;

  function check() {
    const { scrollTop, clientHeight, scrollHeight } = calScroll;
    const atBottom = scrollTop + clientHeight >= scrollHeight - 4;
    if (atBottom) {
      scrollArea.classList.add('revealed');
      // One-way latch: once revealed, stop listening to avoid resize feedback loop
      calScroll.removeEventListener('scroll', calScroll._draftRevealHandler);
      calScroll._draftRevealHandler = null;
    }
  }

  // Clean up any prior listener before attaching a new one
  if (calScroll._draftRevealHandler) {
    calScroll.removeEventListener('scroll', calScroll._draftRevealHandler);
  }
  calScroll._draftRevealHandler = check;
  calScroll.addEventListener('scroll', check);
  check(); // reveal immediately if calendar fits without scrolling
}

// ── Draft Mode Helpers ─────────────────────────────────────────
function enterDraftMode() {
  isDraftMode = true;
  const shell = document.getElementById('app-shell');
  if (shell) shell.classList.add('draft-mode');
  const draftSection = document.getElementById('draft-section');
  if (draftSection) draftSection.style.display = '';
  // Hide right-now section in draft mode (CSS also handles this, belt+suspenders)
  const rightNow = document.getElementById('right-now-section');
  if (rightNow) rightNow.classList.remove('visible');
  // Attach scroll listener after DOM settles
  requestAnimationFrame(initDraftScrollVisibility);
}

function exitDraftMode() {
  isDraftMode = false;
  const shell = document.getElementById('app-shell');
  if (shell) shell.classList.remove('draft-mode');
  const draftSection = document.getElementById('draft-section');
  if (draftSection) draftSection.style.display = 'none';
  // Restore right-now section
  const rightNow = document.getElementById('right-now-section');
  if (rightNow) rightNow.classList.add('visible');
  // Clear draft input
  const draftInput = document.getElementById('draft-adjust-input');
  if (draftInput) draftInput.value = '';
  // Reset scroll-reveal state so next draft starts hidden
  const scrollArea = document.querySelector('.draft-scroll-area');
  if (scrollArea) scrollArea.classList.remove('revealed');
}

function showDraftScreen(data) {
  currentSessionId = data.session_id;
  currentPlanTime = data.current_time;
  hideOverlay();
  renderCalendar(data.plan_output.time_blocks);
  renderSummary(data.plan_output);
  updateSidebar(data.session_id, data.current_time, data.plan_output);
  enterDraftMode();
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

  // Always include current time so the now-line is always visible
  const now = nowMinutes();
  minMin = Math.min(minMin, now);
  maxMin = Math.max(maxMin, now);

  const startHour = Math.max(0, Math.floor(minMin / 60));
  const endHour = Math.min(24, Math.ceil(maxMin / 60));
  return { startHour, endHour };
}

function updateRightNow() {
  const nextEl = document.getElementById('summary-next-actions');
  if (!nextEl || !currentTimeBlocks.length) return;

  const now = nowMinutes();

  // Find the block currently in progress
  let active = currentTimeBlocks.find(b => {
    const s = timeToMinutes(b.start);
    const e = timeToMinutes(b.end);
    return now >= s && now < e;
  });

  // Fall back to the next upcoming block
  if (!active) {
    const upcoming = currentTimeBlocks
      .filter(b => timeToMinutes(b.start) > now)
      .sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
    active = upcoming[0] || null;
  }

  if (!active || !active.steps || !active.steps.length) return;

  nextEl.innerHTML = '<ul>' + active.steps.map(s => `<li>${escHtml(s)}</li>`).join('') + '</ul>';
}

function renderCalendar(timeBlocks) {
  currentTimeBlocks = timeBlocks || [];
  const eventsEl = document.getElementById('calendar-events');
  const axisEl = document.getElementById('calendar-time-axis');

  if (!eventsEl || !axisEl) return;

  eventsEl.innerHTML = '';
  axisEl.innerHTML = '';

  if (!timeBlocks || timeBlocks.length === 0) {
    showCalendarEmpty();
    return;
  }

  const { startHour, endHour } = computeRange(timeBlocks);
  const rangeStartMin = startHour * 60;
  const totalMinutes = (endHour - startHour) * 60;
  // Height is set after block layout so we can expand if push-down moves blocks past the end tick
  const endTickTop = totalMinutes * PIXELS_PER_MINUTE;

  eventsEl.dataset.rangeStart = rangeStartMin;
  eventsEl.dataset.rangeMinutes = totalMinutes;

  for (let h = startHour; h <= endHour; h++) {
    const topPx = (h * 60 - rangeStartMin) * PIXELS_PER_MINUTE;

    const tick = document.createElement('div');
    tick.className = 'hour-tick';
    tick.style.top = topPx + 'px';
    eventsEl.appendChild(tick);

    if (h < endHour) {
      const halfTick = document.createElement('div');
      halfTick.className = 'hour-tick hour-tick--half';
      halfTick.style.top = (topPx + PIXELS_PER_HOUR / 2) + 'px';
      eventsEl.appendChild(halfTick);
    }

    // Always label every hour including the end hour
    const label = document.createElement('div');
    label.className = 'hour-label';
    label.style.top = topPx + 'px';
    label.textContent = fmt12(h * 60);
    axisEl.appendChild(label);
  }

  const sorted = [...timeBlocks].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
  let stickyBottom = 0;
  let visualBottom = 0;
  sorted.forEach((block, idx) => {
    const startMin = timeToMinutes(block.start) - rangeStartMin;
    const endMin = timeToMinutes(block.end) - rangeStartMin;
    const durationMin = Math.max(0, endMin - startMin);

    const naturalTop = startMin * PIXELS_PER_MINUTE;
    const top = Math.max(naturalTop, stickyBottom);
    const height = Math.max(MIN_BLOCK_HEIGHT, durationMin * PIXELS_PER_MINUTE);
    stickyBottom = top + height;
    visualBottom = Math.max(visualBottom, top + height);
    const kind = block.kind || 'task';

    const isCompact = height < COMPACT_THRESHOLD_PX;
    const div = document.createElement('div');
    div.className = `calendar-block calendar-block--${kind}${isCompact ? ' calendar-block--compact' : ''}`;
    div.style.top = top + 'px';
    div.style.height = height + 'px';
    div.title = `${fmt12(timeToMinutes(block.start))}–${fmt12(timeToMinutes(block.end))}: ${block.task}`;

    const timeLabel = `${fmt12(timeToMinutes(block.start))}–${fmt12(timeToMinutes(block.end))}`;
    div.style.animationDelay = `${idx * 0.055}s`;
    div.innerHTML = `
      <div class="block-time">${escHtml(timeLabel)}</div>
      <div class="block-task">${escHtml(block.task)}</div>
    `;
    eventsEl.appendChild(div);
  });

  // Expand to fit actual visual bottom (push-down may exceed end tick) + 48px breathing room
  const totalHeight = Math.max(endTickTop, visualBottom) + 48;
  eventsEl.style.height = totalHeight + 'px';
  axisEl.style.height = totalHeight + 'px';

  drawNowLine(rangeStartMin, totalHeight, totalMinutes);

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
  const rangeStartMin = parseInt(eventsEl.dataset.rangeStart || '480', 10);
  const totalMinutes = parseInt(eventsEl.dataset.rangeMinutes || '600', 10);
  drawNowLine(rangeStartMin, totalHeight, totalMinutes);
  if (!isDraftMode) updateRightNow();
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
    eventsEl.querySelectorAll('.calendar-block').forEach(b => {
      b.style.opacity = '0.3';
    });
    let overlay = document.getElementById('calendar-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'calendar-overlay';
      overlay.className = 'calendar-loading';
      overlay.style.cssText = 'position:absolute;inset:0;background:rgba(255,255,255,0.7);z-index:20;';
      overlay.innerHTML = '<div class="spinner"></div><span>Replanning\u2026</span>';
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
  const nextActions = planOutput.next_actions || [];
  const dropDefer = planOutput.drop_or_defer || [];
  const rationale = planOutput.rationale || '';

  const dropHtml = dropDefer.length
    ? '<ul>' + dropDefer.map(d => `<li>${escHtml(d)}</li>`).join('') + '</ul>'
    : '<span class="empty-note">Nothing dropped.</span>';

  // Right Now section (shown in approved mode)
  const nextEl = document.getElementById('summary-next-actions');
  const rightNow = document.getElementById('right-now-section');
  if (nextEl) {
    nextEl.innerHTML = nextActions.length
      ? '<ul>' + nextActions.map(a => `<li>${escHtml(a)}</li>`).join('') + '</ul>'
      : '<span class="empty-note">No next actions listed.</span>';
  }
  if (rightNow) rightNow.classList.add('visible');

  // Update Right Now to the active block's micro-steps
  updateRightNow();

  // Draft sidebar panel (shown in draft mode) — always populate
  const draftDroppedEl = document.getElementById('draft-dropped');
  const draftRationaleEl = document.getElementById('draft-rationale');
  if (draftDroppedEl) draftDroppedEl.innerHTML = dropHtml;
  if (draftRationaleEl) {
    draftRationaleEl.textContent = rationale || 'No rationale provided.';
    draftRationaleEl.className = 'empty-note';
  }
}

// ── Date helpers ───────────────────────────────────────────────
function formatDateHuman(dateStr) {
  // "2026-03-02" → "March 2nd, 2026"
  const [year, month, day] = dateStr.split('-').map(Number);
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  const v = day % 100;
  const suffix = (v >= 11 && v <= 13) ? 'th' : (['th','st','nd','rd'][day % 10] || 'th');
  return `${months[month - 1]} ${day}${suffix}, ${year}`;
}

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${padTwo(d.getMonth() + 1)}-${padTwo(d.getDate())}`;
}

function tomorrowStr() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${padTwo(d.getMonth() + 1)}-${padTwo(d.getDate())}`;
}

// ── Sidebar Updates ────────────────────────────────────────────
function updateSidebar(sessionId, currentTime, planOutput) {
  const sessionInfo = document.getElementById('session-info');
  const sessionDateLabel = document.getElementById('session-date-label');
  const sessionPlannedAt = document.getElementById('session-planned-at');

  if (sessionInfo && sessionId) {
    const dateStr = sessionId.split('__')[0];

    if (sessionDateLabel) {
      sessionDateLabel.textContent = formatDateHuman(dateStr);
    }

    if (sessionPlannedAt) {
      sessionPlannedAt.textContent = `Last planned at ${fmt12(timeToMinutes(currentTime))}`;
    }

    sessionInfo.style.display = '';
  }

  const conf = planOutput.confidence || {};
  const low = conf.low != null ? Math.round(conf.low * 100) : null;
  const high = conf.high != null ? Math.round(conf.high * 100) : null;
  const confEl = document.getElementById('confidence-value');
  const confBar = document.getElementById('confidence-bar-fill');
  if (confEl && low != null) {
    confEl.textContent = `${low}\u2013${high}%`;
    if (confBar) confBar.style.width = ((low + high) / 2) + '%';
  }
}

// ── Error display helpers ──────────────────────────────────────
function showError(bannerId, msg) {
  const el = document.getElementById(bannerId);
  if (el) {
    el.textContent = msg;
    el.classList.add('visible');
  }
}

function clearError(bannerId) {
  const el = document.getElementById(bannerId);
  if (el) el.classList.remove('visible');
}

// ── Follow-up screen helper ────────────────────────────────────
function showFollowUpScreen(question, type) {
  const qEl = document.getElementById('followup-question-text');
  if (qEl) qEl.textContent = question;

  const inp = document.getElementById('followup-clarify-input');
  if (inp) {
    if (type === 'end_time') {
      inp.rows = 2;
      inp.classList.add('followup-textarea--small');
      inp.placeholder = 'e.g. 6pm, around 5, whenever';
    } else {
      inp.rows = 3;
      inp.classList.remove('followup-textarea--small');
      inp.placeholder = 'e.g. Standup at 2pm, gym before dinner';
    }
    inp.value = '';
  }

  showScreen('followup-clarify-screen');
  if (inp) inp.focus();
}

// ── New-plan flow ──────────────────────────────────────────────
async function submitPlan() {
  const brainDumpEl = document.getElementById('brain-dump');
  const rawText = brainDumpEl ? brainDumpEl.value.trim() : '';

  if (!rawText) {
    showError('error-banner', 'Please describe what you need to do today.');
    return;
  }
  clearError('error-banner');

  // Save for combining with follow-up answer
  brainDumpText = rawText;

  // Disable plan button
  const planBtn = document.getElementById('plan-btn');
  if (planBtn) { planBtn.disabled = true; planBtn.textContent = 'Checking\u2026'; }

  let clarifyResult;
  try {
    const res = await fetch('/api/clarify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: rawText, current_time: currentTimeHHMM || nowHHMM() }),
    });
    clarifyResult = await res.json();
  } catch (e) {
    showError('error-banner', 'Network error. Is the server running?');
    if (planBtn) { planBtn.disabled = false; planBtn.innerHTML = '<span class="btn-icon">&#9654;</span> Untangle my day'; }
    return;
  }

  if (planBtn) { planBtn.disabled = false; planBtn.innerHTML = '<span class="btn-icon">&#9654;</span> Untangle my day'; }

  if (clarifyResult.follow_up_question) {
    // Store type and end time for submitFollowUp()
    currentFollowUpType = clarifyResult.follow_up_type || null;
    currentFollowUpEndTime = clarifyResult.session_end_time || null;
    showFollowUpScreen(clarifyResult.follow_up_question, currentFollowUpType);
  } else {
    // No follow-up needed — go straight to planning
    await runPlanCall(brainDumpText, clarifyResult.session_end_time || null);
  }
}

async function submitFollowUp(skipped) {
  const inp = document.getElementById('followup-clarify-input');
  const answerText = skipped ? '' : (inp ? inp.value.trim() : '');

  let finalEndTime = null;
  let combinedContext;

  if (currentFollowUpType === 'ordering') {
    // End time was already extracted; user answered with ordering constraints
    finalEndTime = currentFollowUpEndTime;
    combinedContext = answerText
      ? `${brainDumpText}\n${answerText}`
      : brainDumpText;
  } else {
    // end_time type: re-parse the answer for a session end time
    if (!skipped && answerText) {
      try {
        const res = await fetch('/api/clarify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context: answerText, current_time: currentTimeHHMM || nowHHMM() }),
        });
        const clarify2 = await res.json();
        finalEndTime = clarify2.session_end_time || null;
      } catch (e) {
        // ignore; proceed without end time
      }
    }
    combinedContext = answerText
      ? `${brainDumpText}\n${answerText}`
      : brainDumpText;
  }

  await runPlanCall(combinedContext, finalEndTime);
}

async function runPlanCall(context, sessionEndTime) {
  const sessionLabelEl = document.getElementById('session_label');
  const dateOverrideEl = document.getElementById('date_override');

  // Prepend current time so backend has unambiguous anchor
  const timeStr = fmt12(timeToMinutes(currentTimeHHMM || nowHHMM()));
  const fullContext = `It's ${timeStr}. ${context}`;

  // Show loading screen
  showScreen('loading-screen');
  const snapDone = animateProgressBar();

  let data;
  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context: fullContext,
        mode: 'new',
        current_time: currentTimeHHMM || nowHHMM(),
        session_label: sessionLabelEl ? sessionLabelEl.value.trim() : '',
        date_override: dateOverrideEl ? dateOverrideEl.value.trim() : '',
        session_end_time: sessionEndTime,
      }),
    });
    data = await res.json();
  } catch (e) {
    // Network error — go back to brain dump screen
    showScreen('brain-dump-screen');
    showError('error-banner', 'Network error. Is the server running?');
    return;
  }

  if (data.error) {
    showScreen('brain-dump-screen');
    showError('error-banner', data.error);
    return;
  }

  snapDone();

  setTimeout(() => {
    showDraftScreen(data);
  }, 500);
}

// ── Draft Adjust flow ──────────────────────────────────────────
async function submitAdjust() {
  const inputEl = document.getElementById('draft-adjust-input');
  const adjustBtn = document.getElementById('draft-adjust-btn');
  const approveBtn = document.getElementById('draft-approve-btn');
  const errBanner = document.getElementById('draft-error-banner');

  const rawContext = inputEl ? inputEl.value.trim() : '';
  if (!rawContext) {
    if (errBanner) { errBanner.textContent = 'Please describe what to change.'; errBanner.classList.add('visible'); }
    return;
  }
  if (errBanner) errBanner.classList.remove('visible');
  if (adjustBtn) adjustBtn.disabled = true;
  if (approveBtn) approveBtn.disabled = true;

  // Show inline calendar loading
  showCalendarLoading();

  const timeStr = fmt12(timeToMinutes(currentTimeHHMM || nowHHMM()));
  const fullContext = `It's ${timeStr}. ${rawContext}`;

  let data;
  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context: fullContext,
        mode: 'adjust',
        current_time: currentTimeHHMM || nowHHMM(),
      }),
    });
    data = await res.json();
    if (!res.ok || data.error) {
      removeCalendarOverlay();
      if (errBanner) { errBanner.textContent = data.error || 'Adjustment failed. Please try again.'; errBanner.classList.add('visible'); }
      return;
    }
  } catch (e) {
    removeCalendarOverlay();
    if (errBanner) { errBanner.textContent = 'Network error. Is the server running?'; errBanner.classList.add('visible'); }
    return;
  } finally {
    if (adjustBtn) adjustBtn.disabled = false;
    if (approveBtn) approveBtn.disabled = false;
  }

  removeCalendarOverlay();
  currentSessionId = data.session_id;
  currentPlanTime = data.current_time;
  renderCalendar(data.plan_output.time_blocks);
  renderSummary(data.plan_output);
  updateSidebar(data.session_id, data.current_time, data.plan_output);
  if (inputEl) inputEl.value = '';
  // Remain in draft mode
  enterDraftMode();
}

// ── Draft Approve flow ─────────────────────────────────────────
async function submitApprove() {
  const approveBtn = document.getElementById('draft-approve-btn');
  const adjustBtn = document.getElementById('draft-adjust-btn');
  const errBanner = document.getElementById('draft-error-banner');

  if (approveBtn) approveBtn.disabled = true;
  if (adjustBtn) adjustBtn.disabled = true;

  try {
    const res = await fetch('/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId }),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      if (errBanner) { errBanner.textContent = data.error || 'Approve failed.'; errBanner.classList.add('visible'); }
      return;
    }
  } catch (e) {
    if (errBanner) { errBanner.textContent = 'Network error. Is the server running?'; errBanner.classList.add('visible'); }
    return;
  } finally {
    if (approveBtn) approveBtn.disabled = false;
    if (adjustBtn) adjustBtn.disabled = false;
  }

  exitDraftMode();
}

// ── Replan flow ────────────────────────────────────────────────
async function handleReplan() {
  const followupEl = document.getElementById('followup-context');
  const replanBtn = document.getElementById('replan-btn');
  const errBanner = document.getElementById('replan-error-banner');

  const rawContext = followupEl ? followupEl.value.trim() : '';
  if (!rawContext) {
    if (errBanner) {
      errBanner.textContent = 'Please describe what changed.';
      errBanner.classList.add('visible');
    }
    return;
  }
  if (errBanner) errBanner.classList.remove('visible');

  if (replanBtn) replanBtn.disabled = true;

  // Show inline overlay over calendar+summary; header and sidebar remain visible
  const replanOverlay = document.getElementById('replan-loading-overlay');
  const replanBar = document.getElementById('replan-progress-bar');
  const replanLabel = document.getElementById('replan-progress-label');
  if (replanOverlay) replanOverlay.style.display = '';

  // Animate progress bar inline
  const replanStages = [
    { pct: 25, dur: 1000, text: 'Reading your changes\u2026' },
    { pct: 75, dur: 8000, text: 'Estimating tasks\u2026' },
    { pct: 95, dur: 4000, text: 'Building new schedule\u2026' },
  ];
  let replanTimer = null;
  let stageIdx = 0;
  function runReplanStage() {
    if (stageIdx >= replanStages.length) return;
    const { pct, dur, text } = replanStages[stageIdx];
    if (replanBar) { replanBar.style.transition = `width ${dur}ms ease-in-out`; replanBar.style.width = pct + '%'; }
    if (replanLabel) replanLabel.textContent = text;
    stageIdx++;
    replanTimer = setTimeout(runReplanStage, dur);
  }
  if (replanBar) { replanBar.style.transition = 'none'; replanBar.style.width = '0%'; }
  requestAnimationFrame(() => requestAnimationFrame(runReplanStage));

  function snapReplanDone() {
    if (replanTimer) clearTimeout(replanTimer);
    if (replanBar) { replanBar.style.transition = 'width 0.4s ease-in-out'; replanBar.style.width = '100%'; }
    if (replanLabel) replanLabel.textContent = 'Done!';
  }

  let data;
  try {
    const res = await fetch('/api/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        context: rawContext,
        mode: 'replan',
        current_time: currentTimeHHMM || nowHHMM(),
      }),
    });
    data = await res.json();

    if (!res.ok || data.error) {
      if (replanOverlay) replanOverlay.style.display = 'none';
      if (errBanner) {
        errBanner.textContent = data.error || 'Replanning failed. Please try again.';
        errBanner.classList.add('visible');
      }
      return;
    }
  } catch (e) {
    if (replanOverlay) replanOverlay.style.display = 'none';
    if (errBanner) {
      errBanner.textContent = 'Network error. Is the server running?';
      errBanner.classList.add('visible');
    }
    return;
  } finally {
    if (replanBtn) replanBtn.disabled = false;
  }

  snapReplanDone();
  setTimeout(() => {
    if (replanOverlay) replanOverlay.style.display = 'none';
    currentSessionId = data.session_id;
    currentPlanTime = data.current_time;
    renderCalendar(data.plan_output.time_blocks);
    renderSummary(data.plan_output);
    updateSidebar(data.session_id, data.current_time, data.plan_output);
    if (followupEl) followupEl.value = '';
  }, 450);
}

// ── Load existing session on page load ────────────────────────
async function loadSession() {
  // ?debug — skip API and show static draft plan for UI development
  if (new URLSearchParams(window.location.search).has('debug')) {
    showDraftScreen(makeDebugPlanData());
    return;
  }

  try {
    const res = await fetch('/api/session');
    const data = await res.json();
    if (data.plan_output && data.plan_output.time_blocks && data.plan_output.time_blocks.length) {
      currentSessionId = data.session_id;
      if (data.phase === 'draft') {
        showDraftScreen(data);
      } else {
        hideOverlay();
        currentPlanTime = data.current_time;
        renderCalendar(data.plan_output.time_blocks);
        renderSummary(data.plan_output);
        updateSidebar(data.session_id, data.current_time, data.plan_output);
      }
    }
    // If no session, overlay stays visible
  } catch (e) {
    // No session — overlay stays visible
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

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initClock();
  currentTimeHHMM = nowHHMM();

  loadSession();

  nowLineInterval = setInterval(refreshNowLine, 60_000);

  // Plan button (brain dump screen)
  const planBtn = document.getElementById('plan-btn');
  if (planBtn) planBtn.addEventListener('click', submitPlan);

  // Ctrl/Cmd+Enter in brain dump
  const brainDump = document.getElementById('brain-dump');
  if (brainDump) {
    brainDump.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        submitPlan();
      }
    });
  }

  // Follow-up continue button
  const continueBtn = document.getElementById('followup-continue-btn');
  if (continueBtn) continueBtn.addEventListener('click', () => submitFollowUp(false));

  // Follow-up Ctrl/Cmd+Enter
  const followupInput = document.getElementById('followup-clarify-input');
  if (followupInput) {
    followupInput.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        submitFollowUp(false);
      }
    });
  }

  // Follow-up skip link
  const skipLink = document.getElementById('followup-skip-link');
  if (skipLink) {
    skipLink.addEventListener('click', e => {
      e.preventDefault();
      submitFollowUp(true);
    });
  }

  // Draft adjust button
  const draftAdjustBtn = document.getElementById('draft-adjust-btn');
  if (draftAdjustBtn) draftAdjustBtn.addEventListener('click', submitAdjust);

  // Ctrl/Cmd+Enter in draft adjust textarea
  const draftAdjustInput = document.getElementById('draft-adjust-input');
  if (draftAdjustInput) {
    draftAdjustInput.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        submitAdjust();
      }
    });
  }

  // Draft approve button
  const draftApproveBtn = document.getElementById('draft-approve-btn');
  if (draftApproveBtn) draftApproveBtn.addEventListener('click', submitApprove);

  // Replan button
  const replanBtn = document.getElementById('replan-btn');
  if (replanBtn) replanBtn.addEventListener('click', handleReplan);

  // Ctrl/Cmd+Enter in replan textarea
  const followupContext = document.getElementById('followup-context');
  if (followupContext) {
    followupContext.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleReplan();
      }
    });
  }

  // Start fresh button
  const freshBtn = document.getElementById('start-fresh-btn');
  if (freshBtn) {
    freshBtn.addEventListener('click', () => {
      // Reset brain dump screen and show overlay
      const brainDumpEl = document.getElementById('brain-dump');
      if (brainDumpEl) brainDumpEl.value = '';
      brainDumpText = '';

      const overlay = document.getElementById('welcome-overlay');
      const shell = document.getElementById('app-shell');
      if (overlay) { overlay.style.display = ''; overlay.style.opacity = '1'; }
      if (shell) shell.style.display = 'none';

      showScreen('brain-dump-screen');
      clearError('error-banner');
      if (brainDumpEl) brainDumpEl.focus();
    });
  }
});
