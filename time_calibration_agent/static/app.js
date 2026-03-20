'use strict';

// ── Constants ──────────────────────────────────────────────────
const BASE_MIN_BLOCK_HEIGHT = 52;
const COMPACT_THRESHOLD_PX = 0; // all blocks show full content
const MICRO_TASK_MAX_MINUTES = 10;
const MICRO_CLUSTER_MAX_SPAN_MINUTES = 24;
// Blocks shorter than this render as compact pills (no minBlockHeight inflation)
const MICRO_BLOCK_MINUTES = 8;
const MICRO_BLOCK_HEIGHT = 26; // px — keeps label legible without cascade push

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
let currentFollowUpType = null;   // "end_time" | null
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

function isMobileViewport() {
  return window.matchMedia('(max-width: 768px)').matches;
}

function getLayoutMetrics(totalMinutes) {
  const mobile = isMobileViewport();
  const minBlockHeight = mobile ? BASE_MIN_BLOCK_HEIGHT + 8 : BASE_MIN_BLOCK_HEIGHT;

  // Target: fit the full schedule in ~85% of the scroll container height
  // so the user rarely needs to scroll more than a small amount.
  const scrollEl = document.getElementById('calendar-scroll');
  const containerH = scrollEl ? scrollEl.clientHeight : 500;
  const targetPx = containerH * 0.85;

  // Natural px/min to fit everything; clamp to a sane range so blocks stay readable
  // Min 3.5 px/min (~210px/hr) keeps labels legible; max 7 px/min (~420px/hr) caps density
  const naturalPxPerMin = targetPx / totalMinutes;
  const pxPerMin = Math.max(3.5, Math.min(7.0, naturalPxPerMin));

  // Never let the scale be so compressed that a short block becomes illegible:
  // if the minimum block height would be violated at this px/min, bump px/min up.
  const worstCaseDuration = 10; // minutes (e.g. a 10-min break)
  const minNeededPxPerMin = minBlockHeight / worstCaseDuration;
  const finalPxPerMin = Math.max(pxPerMin, minNeededPxPerMin);

  return {
    pixelsPerHour: finalPxPerMin * 60,
    pixelsPerMinute: finalPxPerMin,
    minBlockHeight,
  };
}

function buildRenderBlocks(timeBlocks) {
  const sorted = [...(timeBlocks || [])].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
  if (!sorted.length) return [];

  const mobile = isMobileViewport();
  const renderBlocks = [];

  for (let i = 0; i < sorted.length; i++) {
    const block = sorted[i];
    const duration = Math.max(0, timeToMinutes(block.end) - timeToMinutes(block.start));
    const next = sorted[i + 1];

    const canStartCluster = next
      && mobile
      && block.kind !== 'fixed'
      && next.kind === block.kind
      && duration <= MICRO_TASK_MAX_MINUTES;

    if (!canStartCluster) {
      renderBlocks.push(block);
      continue;
    }

    const cluster = [block];
    let clusterStart = timeToMinutes(block.start);
    let clusterEnd = timeToMinutes(block.end);
    let j = i + 1;

    while (j < sorted.length) {
      const candidate = sorted[j];
      const candidateDuration = Math.max(0, timeToMinutes(candidate.end) - timeToMinutes(candidate.start));
      const candidateStart = timeToMinutes(candidate.start);
      const contiguousEnough = candidate.kind === block.kind && candidateStart - clusterEnd <= 4;
      const stillSmall = candidateDuration <= MICRO_TASK_MAX_MINUTES;
      const clusterSpan = timeToMinutes(candidate.end) - clusterStart;

      if (!contiguousEnough || !stillSmall || clusterSpan > MICRO_CLUSTER_MAX_SPAN_MINUTES) break;

      cluster.push(candidate);
      clusterEnd = timeToMinutes(candidate.end);
      j++;
    }

    if (cluster.length === 1) {
      renderBlocks.push(block);
      continue;
    }

    renderBlocks.push({
      start: cluster[0].start,
      end: cluster[cluster.length - 1].end,
      kind: block.kind,
      task: cluster.map(item => item.task).join(' / '),
      steps: cluster[0].steps || [],
      is_cluster: true,
      cluster_tasks: cluster.map(item => ({
        start: item.start,
        end: item.end,
        task: item.task,
      })),
    });
    i = j - 1;
  }

  return renderBlocks;
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

// ── Progress (knot-driven, no visible bar) ─────────────────────
let progressTimer = null;
let _knotProgress = 0;
let _knotProgressRaf = null;

function _easeInOut(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }

function _animKnotTo(target, dur) {
  const startP = _knotProgress, startT = performance.now();
  if (_knotProgressRaf) cancelAnimationFrame(_knotProgressRaf);
  function step() {
    const t = Math.min((performance.now() - startT) / dur, 1);
    _knotProgress = startP + (target - startP) * _easeInOut(t);
    if (t < 1) _knotProgressRaf = requestAnimationFrame(step);
    else _knotProgress = target;
  }
  _knotProgressRaf = requestAnimationFrame(step);
}

function animateProgressBar(onComplete) {
  const label = document.getElementById('progress-label');
  const stages = [
    { pct: 0.20, dur: 1000, text: 'Untangling your day\u2026' },
    { pct: 0.70, dur: 8000, text: 'Estimating task durations\u2026' },
    { pct: 0.95, dur: 4000, text: 'Building your schedule\u2026' },
  ];
  let stageIdx = 0;
  _knotProgress = 0;

  function runStage() {
    if (stageIdx >= stages.length) return;
    const { pct, dur, text } = stages[stageIdx];
    if (label) label.textContent = text;
    _animKnotTo(pct, dur);
    stageIdx++;
    progressTimer = setTimeout(runStage, dur);
  }

  requestAnimationFrame(() => requestAnimationFrame(runStage));

  return function snapDone() {
    if (progressTimer) clearTimeout(progressTimer);
    if (_knotProgressRaf) cancelAnimationFrame(_knotProgressRaf);
    _knotProgress = 1;
    if (label) label.textContent = 'Done!';
    if (onComplete) setTimeout(onComplete, 450);
  };
}

// ── Knot Untangle Animation ────────────────────────────────────
// Core draw: thread with two free ends; complex tangled middle at progress=0,
// straight line at progress=1. Both the progress-driven and looping versions
// call this function.
function drawThreadKnot(canvas, progress) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const cx = W / 2, cy = H / 2;
  const N = 500;
  // Rope thickness proportional to smaller dimension
  const thick = Math.max(5, Math.min(W, H) * 0.038);
  // Spiral knot radius: compact central knot with tails extending to edges
  const knotR = Math.min(H * 0.38, W * 0.18);
  const tailFrac = 0.22; // fraction of path length devoted to each straight tail
  const loops = 3.5;    // number of full rotations in the spiral knot

  ctx.clearRect(0, 0, W, H);

  const pts = [];
  for (let i = 0; i <= N; i++) {
    const u = i / N;
    // Straight line target: spans full canvas width at vertical center
    const sx = W * (0.04 + u * 0.92);
    const sy = cy;

    // Knotted state: tails enter from sides, spiral knot in center
    let kx, ky;
    if (u <= tailFrac) {
      // Left tail: straight line from left edge → canvas center
      kx = W * (0.04 + (u / tailFrac) * (0.5 - 0.04));
      ky = cy;
    } else if (u >= 1 - tailFrac) {
      // Right tail: canvas center → right edge
      const t = (u - (1 - tailFrac)) / tailFrac;
      kx = W * (0.5 + t * (0.96 - 0.5));
      ky = cy;
    } else {
      // Spiral knot body: r peaks at u=0.5, is 0 at entry/exit → smooth join with tails
      const t = (u - tailFrac) / (1 - 2 * tailFrac); // 0→1 within knot section
      const angle = t * Math.PI * 2 * loops;
      const r = knotR * Math.sin(t * Math.PI);
      kx = cx + r * Math.cos(angle);
      ky = cy + r * Math.sin(angle);
    }

    // Blend: knotted at progress=0, straight line at progress=1
    pts.push([
      kx + (sx - kx) * progress,
      ky + (sy - ky) * progress
    ]);
  }

  function strokePts(color, lw) {
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  }

  // Shadow
  ctx.save();
  ctx.shadowColor = 'rgba(20,55,47,0.20)';
  ctx.shadowBlur = thick;
  ctx.shadowOffsetY = thick * 0.4;
  strokePts('#2f7a6a', thick);
  ctx.restore();

  // Main rope
  strokePts('#2f7a6a', thick);

  // Highlight sheen for cord depth
  strokePts('rgba(190,225,215,0.45)', thick * 0.32);

  // End nubs
  const r = thick * 0.7;
  [pts[0], pts[N]].forEach(p => {
    ctx.beginPath();
    ctx.arc(p[0], p[1], r, 0, Math.PI * 2);
    ctx.fillStyle = '#72b59f';
    ctx.fill();
  });
}

// Looping version for calendar overlay (timer-driven, not progress-driven)
const _knotRafs = {};

function startKnotAnimation(canvas) {
  const cid = canvas.id || ('knot_' + Math.random());
  if (_knotRafs[cid]) cancelAnimationFrame(_knotRafs[cid]);

  let blend = 0, phase = 'hold_knot', t0 = null;
  function ease(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }

  function frame(ts) {
    if (!t0) t0 = ts;
    const el = ts - t0;
    if (phase === 'hold_knot') {
      blend = 0;
      if (el > 400) { phase = 'untangling'; t0 = ts; }
    } else if (phase === 'untangling') {
      blend = ease(Math.min(el / 2200, 1));
      if (el > 2200) { phase = 'done'; blend = 1; }
    }
    drawThreadKnot(canvas, blend);
    // Stop once fully unwound — no retangle loop
    if (phase !== 'done') {
      _knotRafs[cid] = requestAnimationFrame(frame);
    }
  }
  _knotRafs[cid] = requestAnimationFrame(frame);
}

// Progress-driven version for main loading screen — polls actual progress bar each frame
let _progressKnotActive = false;
let _progressKnotRaf = null;

function startProgressKnot() {
  const canvas = document.getElementById('knot-canvas-main');
  if (!canvas) return;
  _progressKnotActive = true;
  function loop() {
    if (!_progressKnotActive) return;
    drawThreadKnot(canvas, _knotProgress);
    _progressKnotRaf = requestAnimationFrame(loop);
  }
  _progressKnotRaf = requestAnimationFrame(loop);
}

function stopProgressKnot() {
  _progressKnotActive = false;
  if (_progressKnotRaf) { cancelAnimationFrame(_progressKnotRaf); _progressKnotRaf = null; }
}

// ── Welcome Overlay Transitions ────────────────────────────────
const SCREEN_PATHS = {
  'brain-dump-screen': '/welcome',
  'followup-clarify-screen': '/clarify',
  'loading-screen': '/planning',
};

function showScreen(id) {
  ['brain-dump-screen', 'followup-clarify-screen', 'loading-screen'].forEach(sid => {
    const el = document.getElementById(sid);
    if (el) el.style.display = sid === id ? '' : 'none';
  });
  if (id === 'loading-screen') startProgressKnot();
  else stopProgressKnot();
  const path = SCREEN_PATHS[id];
  if (path) trackPageView(path, id.replace('-screen', '').replace(/-/g, ' '));
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
  const rightNow = document.getElementById('right-now-section');
  if (rightNow) rightNow.classList.remove('visible');
  hideFab();
  requestAnimationFrame(initDraftScrollVisibility);
}

function exitDraftMode() {
  isDraftMode = false;
  const shell = document.getElementById('app-shell');
  if (shell) shell.classList.remove('draft-mode');
  const draftSection = document.getElementById('draft-section');
  if (draftSection) draftSection.style.display = 'none';
  const rightNow = document.getElementById('right-now-section');
  if (rightNow) rightNow.classList.add('visible');
  const draftInput = document.getElementById('draft-adjust-input');
  if (draftInput) draftInput.value = '';
  const scrollArea = document.querySelector('.draft-scroll-area');
  if (scrollArea) scrollArea.classList.remove('revealed');
  trackPageView('/planner', 'day planner');
  showFab();
}

function showDraftScreen(data) {
  currentSessionId = data.session_id;
  currentPlanTime = data.current_time;
  hideOverlay();
  renderCalendar(data.plan_output.time_blocks);
  renderSummary(data.plan_output);
  updateSidebar(data.session_id, data.current_time, data.plan_output);
  enterDraftMode();
  trackPageView('/draft', 'draft plan');
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

  if (!active) {
    return;
  }

  if (!active.steps || !active.steps.length) return;

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

  const renderBlocks = buildRenderBlocks(timeBlocks);
  const { startHour, endHour } = computeRange(renderBlocks);
  const rangeStartMin = startHour * 60;
  const totalMinutes = (endHour - startHour) * 60;
  const layout = getLayoutMetrics(totalMinutes);
  // Height is set after block layout so we can expand if push-down moves blocks past the end tick
  const endTickTop = totalMinutes * layout.pixelsPerMinute;

  eventsEl.dataset.rangeStart = rangeStartMin;
  eventsEl.dataset.rangeMinutes = totalMinutes;
  eventsEl.dataset.pixelsPerMinute = String(layout.pixelsPerMinute);

  for (let h = startHour; h <= endHour; h++) {
    const topPx = (h * 60 - rangeStartMin) * layout.pixelsPerMinute;

    const tick = document.createElement('div');
    tick.className = 'hour-tick';
    tick.style.top = topPx + 'px';
    eventsEl.appendChild(tick);

    if (h < endHour) {
      const halfTick = document.createElement('div');
      halfTick.className = 'hour-tick hour-tick--half';
      halfTick.style.top = (topPx + layout.pixelsPerHour / 2) + 'px';
      eventsEl.appendChild(halfTick);
    }

    // Always label every hour including the end hour
    const label = document.createElement('div');
    label.className = 'hour-label';
    if (h === 24) label.classList.add('hour-label--midnight');
    label.style.top = topPx + 'px';
    label.textContent = fmt12(h * 60);
    axisEl.appendChild(label);
  }

  const sorted = [...renderBlocks].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));
  const now = nowMinutes();
  let stickyBottom = 0;
  let visualBottom = 0;
  sorted.forEach((block, idx) => {
    const startMin = timeToMinutes(block.start) - rangeStartMin;
    const endMin = timeToMinutes(block.end) - rangeStartMin;
    const durationMin = Math.max(0, endMin - startMin);
    const absoluteStartMin = timeToMinutes(block.start);
    const absoluteEndMin = timeToMinutes(block.end);

    // Micro blocks (very short) use a compact height to avoid cascade push-down
    const isMicro = durationMin > 0 && durationMin <= MICRO_BLOCK_MINUTES;
    const effectiveMinHeight = isMicro
      ? Math.max(MICRO_BLOCK_HEIGHT, durationMin * layout.pixelsPerMinute)
      : layout.minBlockHeight;

    const naturalTop = startMin * layout.pixelsPerMinute;
    const naturalHeight = Math.max(effectiveMinHeight, durationMin * layout.pixelsPerMinute);
    const blockEndTop = endMin * layout.pixelsPerMinute;
    const top = Math.max(naturalTop, stickyBottom);
    let height = naturalHeight;
    if (top + height > blockEndTop) {
      // Preserve chronological order, but never let a block render past its true end.
      height = Math.max(durationMin * layout.pixelsPerMinute, blockEndTop - top);
    }
    // Micro blocks use a tighter gap to minimize cascade
    stickyBottom = top + height + (isMicro ? 2 : 4);
    visualBottom = Math.max(visualBottom, top + height);
    const kind = block.kind || 'task';

    const isCompact = height < COMPACT_THRESHOLD_PX;
    const div = document.createElement('div');
    div.className = `calendar-block calendar-block--${kind}${isCompact ? ' calendar-block--compact' : ''}`;
    if (isMicro) div.classList.add('calendar-block--micro');
    if (!isMicro && height <= 58) div.classList.add('calendar-block--short');
    if (!isMicro && height <= 84) div.classList.add('calendar-block--medium');
    if (block.is_cluster) div.classList.add('calendar-block--cluster');
    if (now >= absoluteStartMin && now < absoluteEndMin) {
      div.classList.add('calendar-block--current');
    } else if (absoluteStartMin > now) {
      div.classList.add('calendar-block--upcoming');
    } else {
      div.classList.add('calendar-block--past');
    }
    div.style.top = top + 'px';
    div.style.height = height + 'px';

    const timeLabel = `${fmt12(timeToMinutes(block.start))}–${fmt12(timeToMinutes(block.end))}`;
    div.style.animationDelay = `${idx * 0.055}s`;
    const lockIcon = kind === 'fixed' ? '<span class="block-lock">&#128274;</span>' : '';

    if (isMicro) {
      // Compact single-line layout for tiny blocks
      div.innerHTML = `
        <div class="block-micro-inner">
          <span class="block-micro-time">${escHtml(fmt12(absoluteStartMin))}</span>
          <span class="block-micro-label">${lockIcon}${escHtml(block.task)}</span>
        </div>
      `;
    } else if (block.is_cluster && block.cluster_tasks && block.cluster_tasks.length) {
      div.innerHTML = `
        <div class="block-time">${escHtml(timeLabel)}</div>
        <div class="block-task-list">
          ${block.cluster_tasks.map(item => `
            <div class="block-task-row">
              <span class="block-task-row-time">${escHtml(fmt12(timeToMinutes(item.start)))}</span>
              <span class="block-task-row-label">${escHtml(item.task)}</span>
            </div>
          `).join('')}
        </div>
      `;
    } else {
      div.innerHTML = `
        <div class="block-time">${escHtml(timeLabel)}</div>
        <div class="block-task">${lockIcon}${escHtml(block.task)}</div>
      `;
    }
    eventsEl.appendChild(div);
  });

  // Expand to fit actual visual bottom (push-down may exceed end tick) + 48px breathing room
  const totalHeight = Math.max(endTickTop, visualBottom) + 48;
  eventsEl.style.height = totalHeight + 'px';
  axisEl.style.height = totalHeight + 'px';

  drawNowLine(rangeStartMin, totalHeight, totalMinutes, layout.pixelsPerMinute);

  const scrollEl = document.getElementById('calendar-scroll');
  if (scrollEl) {
    const now = nowMinutes();
    if (now >= rangeStartMin && now <= rangeStartMin + totalMinutes) {
      const viewportHeight = scrollEl.clientHeight || 0;
      const activeBlock = sorted.find(block => {
        const start = timeToMinutes(block.start);
        const end = timeToMinutes(block.end);
        return now >= start && now < end;
      });
      const anchorMinutes = activeBlock
        ? Math.max(0, timeToMinutes(activeBlock.start) - rangeStartMin)
        : Math.max(0, now - rangeStartMin);
      const anchorTop = anchorMinutes * layout.pixelsPerMinute;
      const preferredOffset = 12;
      const maxScrollTop = Math.max(0, totalHeight - viewportHeight);
      const minScrollTop = Math.min(maxScrollTop, Math.max(0, anchorTop - preferredOffset));
      scrollEl.dataset.minScrollTop = String(minScrollTop);
      // Only scroll when element is actually scrollable (not overflow:visible)
      const ovY = getComputedStyle(scrollEl).overflowY;
      if (ovY !== 'visible' && ovY !== 'hidden') {
        scrollEl.scrollTop = minScrollTop;
      }
    } else {
      scrollEl.dataset.minScrollTop = '0';
    }
  }
}

function initCalendarScrollClamp() {
  const scrollEl = document.getElementById('calendar-scroll');
  if (!scrollEl || scrollEl.dataset.clampBound === 'true') return;

  scrollEl.addEventListener('scroll', () => {
    const minScrollTop = parseInt(scrollEl.dataset.minScrollTop || '0', 10);
    if (scrollEl.scrollTop < minScrollTop) {
      scrollEl.scrollTop = minScrollTop;
    }
  }, { passive: true });

  scrollEl.dataset.clampBound = 'true';
}

function drawNowLine(rangeStartMin, totalHeight, totalMinutes, pixelsPerMinute) {
  const eventsEl = document.getElementById('calendar-events');
  if (!eventsEl) return;

  const existing = document.getElementById('now-line');
  if (existing) existing.remove();

  const now = nowMinutes();
  const offsetMin = now - rangeStartMin;
  if (offsetMin < 0 || offsetMin > totalMinutes) return;

  const top = offsetMin * pixelsPerMinute;
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
  const pixelsPerMinute = parseFloat(eventsEl.dataset.pixelsPerMinute || '8');
  drawNowLine(rangeStartMin, totalHeight, totalMinutes, pixelsPerMinute);
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

// ── Calendar overlay knot animation (progress-driven, mirrors main screen) ────
let _calKnotProgress = 0;
let _calKnotProgressRaf = null;
let _calKnotTimer = null;
let _calKnotLoopActive = false;

function _animCalKnotTo(target, dur) {
  const startP = _calKnotProgress, startT = performance.now();
  if (_calKnotProgressRaf) cancelAnimationFrame(_calKnotProgressRaf);
  function step() {
    const t = Math.min((performance.now() - startT) / dur, 1);
    _calKnotProgress = startP + (target - startP) * _easeInOut(t);
    if (t < 1) _calKnotProgressRaf = requestAnimationFrame(step);
    else _calKnotProgress = target;
  }
  _calKnotProgressRaf = requestAnimationFrame(step);
}

function startCalKnotAnimation(canvas) {
  _calKnotProgress = 0;
  _calKnotLoopActive = true;
  const stages = [
    { pct: 0.20, dur: 1000 },
    { pct: 0.70, dur: 8000 },
    { pct: 0.95, dur: 4000 },
  ];
  let stageIdx = 0;
  function runStage() {
    if (stageIdx >= stages.length) return;
    const { pct, dur } = stages[stageIdx];
    _animCalKnotTo(pct, dur);
    stageIdx++;
    _calKnotTimer = setTimeout(runStage, dur);
  }
  requestAnimationFrame(() => requestAnimationFrame(runStage));
  function loop() {
    if (!_calKnotLoopActive) return;
    drawThreadKnot(canvas, _calKnotProgress);
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
}

function stopCalKnotAnimation(canvas) {
  _calKnotLoopActive = false;
  if (_calKnotTimer) clearTimeout(_calKnotTimer);
  if (_calKnotProgressRaf) cancelAnimationFrame(_calKnotProgressRaf);
  _calKnotProgress = 1;
  if (canvas) drawThreadKnot(canvas, 1);
}

function showCalendarLoading() {
  // Fade out existing blocks
  document.querySelectorAll('#calendar-events .calendar-block').forEach(b => {
    b.style.opacity = '0.25';
  });

  // Prevent scroll during loading
  const scrollEl = document.getElementById('calendar-scroll');
  if (scrollEl) scrollEl.style.overflow = 'hidden';

  let overlay = document.getElementById('calendar-overlay');
  if (!overlay) {
    const panelEl = document.querySelector('.calendar-panel');
    if (!panelEl) return;
    panelEl.style.position = 'relative';
    overlay = document.createElement('div');
    overlay.id = 'calendar-overlay';
    overlay.style.cssText = 'position:absolute;inset:0;background:rgba(255,255,255,0.82);z-index:30;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;border-radius:inherit;';
    overlay.innerHTML = '<canvas id="knot-canvas-cal" class="knot-canvas" width="400" height="160" style="width:200px;height:80px;"></canvas><span style="font-size:0.88rem;font-weight:600;color:var(--ink)">Replanning\u2026</span>';
    panelEl.appendChild(overlay);
    const calCanvas = overlay.querySelector('canvas');
    if (calCanvas) startCalKnotAnimation(calCanvas);
  }
}

function removeCalendarOverlay() {
  const overlay = document.getElementById('calendar-overlay');
  const canvas = overlay ? overlay.querySelector('canvas') : null;
  stopCalKnotAnimation(canvas);
  // Restore scroll
  const scrollEl = document.getElementById('calendar-scroll');
  if (scrollEl) scrollEl.style.overflow = '';
  // Brief pause to show the flat/done state before overlay disappears
  setTimeout(() => {
    const ov = document.getElementById('calendar-overlay');
    if (ov) ov.remove();
    // Restore block opacity
    document.querySelectorAll('#calendar-events .calendar-block').forEach(b => {
      b.style.opacity = '';
    });
  }, 350);
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

// ── Analytics ─────────────────────────────────────────────────
function track(event, params = {}) {
  if (typeof gtag === 'function') gtag('event', event, params);
}

function updateVirtualLocation(path, title) {
  if (!window.history || typeof window.history.replaceState !== 'function') return;
  if (window.location.pathname === path && document.title === title) return;
  window.history.replaceState({}, title, path);
  if (title) document.title = title;
}

function trackPageView(path, title) {
  updateVirtualLocation(path, title);
  if (typeof gtag === 'function') {
    gtag('event', 'page_view', {
      page_title: title,
      page_location: window.location.origin + path,
      page_path: path,
    });
  }
}

// ── Error display helpers ──────────────────────────────────────
function showError(bannerId, msg) {
  const el = document.getElementById(bannerId);
  if (el) {
    el.textContent = msg;
    el.classList.add('visible');
  }
  track('error_occurred', { error_message: msg, banner_id: bannerId });
}

function clearError(bannerId) {
  const el = document.getElementById(bannerId);
  if (el) el.classList.remove('visible');
}

// ── Drum Picker ────────────────────────────────────────────────
const DRUM_ITEM_HEIGHT = 44;
const END_OF_DAY_MINUTES = 24 * 60;
const END_OF_DAY_VALUE = '23:59';

function rebuildTimeDrum() {
  const col = document.getElementById('drum-time');
  if (!col) return;
  col.innerHTML = '';

  const now = currentTimeHHMM || nowHHMM();
  const [nowH, nowM] = now.split(':').map(Number);
  let startMin = nowH * 60 + nowM + 30;
  startMin = Math.ceil(startMin / 30) * 30;
  const endMin = END_OF_DAY_MINUTES;

  const makePad = () => { const d = document.createElement('div'); d.className = 'drum-pad'; return d; };

  col.appendChild(makePad());
  for (let min = startMin; min <= endMin; min += 30) {
    const d = document.createElement('div');
    d.className = 'drum-item';
    d.textContent = fmt12(min);
    d.dataset.value = min === END_OF_DAY_MINUTES
      ? END_OF_DAY_VALUE
      : `${padTwo(Math.floor(min / 60))}:${padTwo(min % 60)}`;
    col.appendChild(d);
  }
  col.appendChild(makePad());
}

function defaultEndTime() {
  const now = currentTimeHHMM || nowHHMM();
  const [h, m] = now.split(':').map(Number);
  let totalMin = h * 60 + m + 180;
  totalMin = Math.round(totalMin / 30) * 30;
  totalMin = Math.min(totalMin, END_OF_DAY_MINUTES);
  if (totalMin >= END_OF_DAY_MINUTES) return END_OF_DAY_VALUE;
  return `${padTwo(Math.floor(totalMin / 60))}:${padTwo(totalMin % 60)}`;
}

function setDrumPickerDefault(hhMM) {
  const col = document.getElementById('drum-time');
  if (!col) return;
  const [hh, mm] = hhMM.split(':').map(Number);
  const targetMin = hh * 60 + mm;
  const items = [...col.querySelectorAll('.drum-item')];
  const idx = items.findIndex(item => {
    const [ih, im] = item.dataset.value.split(':').map(Number);
    return ih * 60 + im >= targetMin;
  });
  col.scrollTop = (idx >= 0 ? idx : 0) * DRUM_ITEM_HEIGHT;
}

function getDrumPickerValue() {
  const col = document.getElementById('drum-time');
  if (!col) return null;
  const idx = Math.max(0, Math.round(col.scrollTop / DRUM_ITEM_HEIGHT));
  const items = col.querySelectorAll('.drum-item');
  return idx < items.length ? items[idx].dataset.value : null;
}

// ── Follow-up screen helper ────────────────────────────────────
function showFollowUpScreen(question, type) {
  const qEl = document.getElementById('followup-question-text');
  if (qEl) qEl.textContent = question;

  const inp = document.getElementById('followup-clarify-input');
  const drum = document.getElementById('time-drum-picker');

  if (type === 'end_time') {
    if (inp) inp.style.display = 'none';
    if (drum) drum.style.display = '';
    rebuildTimeDrum();
    showScreen('followup-clarify-screen');
    requestAnimationFrame(() => setDrumPickerDefault(defaultEndTime()));
  } else {
    if (inp) { inp.style.display = ''; inp.value = ''; }
    if (drum) drum.style.display = 'none';
    showScreen('followup-clarify-screen');
    if (inp) inp.focus();
  }
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

  if (clarifyResult.follow_up_question && clarifyResult.follow_up_type === 'end_time') {
    currentFollowUpType = 'end_time';
    showFollowUpScreen(clarifyResult.follow_up_question, 'end_time');
  } else {
    // ordering type or no follow-up: go straight to planning
    await runPlanCall(brainDumpText, clarifyResult.session_end_time || null);
  }
}

async function submitFollowUp(skipped) {
  let finalEndTime = null;
  if (currentFollowUpType === 'end_time' && !skipped) {
    finalEndTime = getDrumPickerValue();
  }
  await runPlanCall(brainDumpText, finalEndTime);
}

async function runPlanCall(context, sessionEndTime) {
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
        session_end_time: sessionEndTime,
        date_override: todayStr(),
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
  track('plan_created');

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

  track('plan_approved');
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

  // Close FAB panel and keep the current calendar visible while replanning
  closeFabPanel();
  showCalendarLoading();

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
      removeCalendarOverlay();
      if (errBanner) {
        errBanner.textContent = data.error || 'Replanning failed. Please try again.';
        errBanner.classList.add('visible');
      }
      return;
    }
  } catch (e) {
    removeCalendarOverlay();
    if (errBanner) {
      errBanner.textContent = 'Network error. Is the server running?';
      errBanner.classList.add('visible');
    }
    return;
  } finally {
    if (replanBtn) replanBtn.disabled = false;
  }

  track('replan_triggered');
  removeCalendarOverlay();
  currentSessionId = data.session_id;
  currentPlanTime = data.current_time;
  renderCalendar(data.plan_output.time_blocks);
  renderSummary(data.plan_output);
  updateSidebar(data.session_id, data.current_time, data.plan_output);
  if (followupEl) followupEl.value = '';
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
        trackPageView('/planner', 'day planner');
        showFab();
      }
    }
    if (!data.plan_output || !data.plan_output.time_blocks || !data.plan_output.time_blocks.length) {
      trackPageView('/welcome', 'welcome');
      track('welcome_screen_shown');
    }
  } catch (e) {
    // No session — overlay stays visible
    trackPageView('/welcome', 'welcome');
    track('welcome_screen_shown');
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

// ── Voice Recording ────────────────────────────────────────────
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
// Tracks which mic session is active
let activeMicCfg = null; // { btnId, textareaId, statusRowId, statusId, errorBannerId }

function _setMicRecording(cfg, recording) {
  const btn = document.getElementById(cfg.btnId);
  const statusRow = document.getElementById(cfg.statusRowId);
  const status = document.getElementById(cfg.statusId);
  if (btn) btn.classList.toggle('recording', recording);
  if (statusRow) statusRow.style.display = recording ? '' : 'none';
  if (status) status.textContent = recording ? 'Recording\u2026 tap to stop' : '';
}

async function startRecording(cfg) {
  clearError(cfg.errorBannerId);
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    activeMicCfg = cfg;
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      await transcribeAudio(cfg);
    };
    mediaRecorder.start();
    isRecording = true;
    _setMicRecording(cfg, true);
  } catch (e) {
    showError(cfg.errorBannerId, 'Microphone access denied. Check browser permissions.');
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    if (activeMicCfg) _setMicRecording(activeMicCfg, false);
  }
}

async function transcribeAudio(cfg) {
  const statusRow = document.getElementById(cfg.statusRowId);
  const status = document.getElementById(cfg.statusId);
  const micBtn = document.getElementById(cfg.btnId);
  if (statusRow) statusRow.style.display = '';
  if (status) status.textContent = 'Transcribing\u2026';
  if (micBtn) micBtn.disabled = true;

  const blob = new Blob(audioChunks, { type: 'audio/webm' });
  const formData = new FormData();
  formData.append('audio', blob, 'recording.webm');

  try {
    const res = await fetch('/api/transcribe', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) {
      showError(cfg.errorBannerId, data.error);
    } else if (data.text) {
      track('voice_used');
      const textarea = document.getElementById(cfg.textareaId);
      if (textarea) {
        const existing = textarea.value.trim();
        textarea.value = existing ? existing + ' ' + data.text : data.text;
        textarea.focus();
      }
    }
  } catch (e) {
    showError(cfg.errorBannerId, 'Transcription failed. Please try again.');
  } finally {
    if (statusRow) statusRow.style.display = 'none';
    if (status) status.textContent = '';
    if (micBtn) micBtn.disabled = false;
    activeMicCfg = null;
  }
}

// Mic configurations per context
const MIC_BRAIN_DUMP = {
  btnId: 'mic-btn',
  textareaId: 'brain-dump',
  statusRowId: 'voice-status-row',
  statusId: 'voice-status',
  errorBannerId: 'error-banner',
};
const MIC_REPLAN = {
  btnId: 'mic-btn-replan',
  textareaId: 'followup-context',
  statusRowId: 'voice-status-row-replan',
  statusId: 'voice-status-replan',
  errorBannerId: 'replan-error-banner',
};
const MIC_DRAFT = {
  btnId: 'mic-btn-draft',
  textareaId: 'draft-adjust-input',
  statusRowId: 'voice-status-row-draft',
  statusId: 'voice-status-draft',
  errorBannerId: 'draft-error-banner',
};

// ── FAB (Replan) ───────────────────────────────────────────────
function openFabPanel() {
  const backdrop = document.getElementById('fab-backdrop');
  const panel = document.getElementById('fab-panel');
  if (backdrop) backdrop.classList.add('open');
  if (panel) panel.classList.add('open');
  const textarea = document.getElementById('followup-context');
  if (textarea) setTimeout(() => textarea.focus(), 300);
}

function closeFabPanel() {
  const backdrop = document.getElementById('fab-backdrop');
  const panel = document.getElementById('fab-panel');
  if (backdrop) backdrop.classList.remove('open');
  if (panel) panel.classList.remove('open');
  clearError('replan-error-banner');
}

function showFab() {
  const btn = document.getElementById('fab-replan-btn');
  if (btn) btn.style.display = '';
}

function hideFab() {
  const btn = document.getElementById('fab-replan-btn');
  if (btn) btn.style.display = 'none';
  closeFabPanel();
}

// ── Calendar Export ────────────────────────────────────────────
function showGcalToast(msg, isError) {
  let toast = document.getElementById('gcal-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'gcal-toast';
    document.body.appendChild(toast);
  }
  toast.className = 'gcal-toast' + (isError ? ' gcal-toast--error' : '');
  toast.textContent = msg;
  toast.classList.add('gcal-toast--visible');
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => { toast.classList.remove('gcal-toast--visible'); }, 4000);
}

async function openGoogleCalendar() {
  track('open_google_calendar');
  const btn = document.getElementById('gcal-btn');
  if (btn) { btn.disabled = true; btn.classList.add('btn--loading'); }
  showGcalToast('Adding to Google Calendar…');
  try {
    const statusRes = await fetch('/api/gcal/status');
    const statusData = await statusRes.json();
    if (statusData.connected) {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      const pushRes = await fetch('/api/gcal/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timezone: tz })
      });
      const pushData = await pushRes.json();
      if (pushData.error) {
        showGcalToast('Error: ' + pushData.error, true);
      } else {
        showGcalToast(`${pushData.pushed} event${pushData.pushed === 1 ? '' : 's'} added to Google Calendar ✓`);
      }
    } else {
      if (btn) { btn.disabled = false; btn.classList.remove('btn--loading'); }
      window.location.href = '/api/gcal/auth';
      return;
    }
  } catch (e) {
    showGcalToast('Network error — could not reach server.', true);
  }
  if (btn) { btn.disabled = false; btn.classList.remove('btn--loading'); }
}

function exportCalendar() {
  track('export_ics');
  if (!currentTimeBlocks || !currentTimeBlocks.length) {
    showGcalToast('No plan to export.', true);
    return;
  }
  const sessionId = currentSessionId || new Date().toISOString().slice(0, 10);
  const dateStr = sessionId.split('__')[0];
  const [year, month, day] = dateStr.split('-').map(Number);
  const pad = n => String(n).padStart(2, '0');
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0',
    'PRODID:-//Untangle//Time Planner//EN',
    'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
  ];
  currentTimeBlocks.forEach((block, idx) => {
    try {
      const [sh, sm] = block.start.split(':').map(Number);
      const [eh, em] = block.end.split(':').map(Number);
      const dtstart = `${year}${pad(month)}${pad(day)}T${pad(sh)}${pad(sm)}00`;
      const dtend   = `${year}${pad(month)}${pad(day)}T${pad(eh)}${pad(em)}00`;
      const task = (block.task || 'Task').replace(/[\r\n]/g, ' ');
      lines.push(
        'BEGIN:VEVENT',
        `UID:${sessionId}-block${idx}@untangle`,
        `DTSTART;TZID=${tz}:${dtstart}`,
        `DTEND;TZID=${tz}:${dtend}`,
        `SUMMARY:${task}`,
        'END:VEVENT',
      );
    } catch (e) {}
  });
  lines.push('END:VCALENDAR');

  const ics = lines.join('\r\n') + '\r\n';
  const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent);
  if (isIOS && sessionId) {
    // On iOS, navigate to the https:// endpoint — Safari sees text/calendar and offers
    // "Open in Calendar" as a one-time import (webcal:// creates a subscription instead)
    window.location.href = `/api/export-ics?session_id=${encodeURIComponent(sessionId)}`;
    return;
  }

  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `untangle-${dateStr}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initClock();
  currentTimeHHMM = nowHHMM();
  initCalendarScrollClamp();

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

  // Replan button (in FAB panel)
  const replanBtn = document.getElementById('replan-btn');
  if (replanBtn) replanBtn.addEventListener('click', handleReplan);

  // Mic button — brain dump screen
  const micBtn = document.getElementById('mic-btn');
  if (micBtn) {
    micBtn.addEventListener('click', () => {
      if (isRecording) stopRecording();
      else startRecording(MIC_BRAIN_DUMP);
    });
  }

  // Mic button — replan textarea (in FAB panel)
  const micBtnReplan = document.getElementById('mic-btn-replan');
  if (micBtnReplan) {
    micBtnReplan.addEventListener('click', () => {
      if (isRecording) stopRecording();
      else startRecording(MIC_REPLAN);
    });
  }

  // Mic button — draft adjust textarea
  const micBtnDraft = document.getElementById('mic-btn-draft');
  if (micBtnDraft) {
    micBtnDraft.addEventListener('click', () => {
      if (isRecording) stopRecording();
      else startRecording(MIC_DRAFT);
    });
  }

  // FAB open/close
  const fabBtn = document.getElementById('fab-replan-btn');
  if (fabBtn) fabBtn.addEventListener('click', openFabPanel);

  const fabClose = document.getElementById('fab-panel-close');
  if (fabClose) fabClose.addEventListener('click', closeFabPanel);

  const fabBackdrop = document.getElementById('fab-backdrop');
  if (fabBackdrop) fabBackdrop.addEventListener('click', closeFabPanel);

  // Cmd/Ctrl+Enter inside FAB panel textarea
  const followupContext = document.getElementById('followup-context');
  if (followupContext) {
    followupContext.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleReplan();
      }
    });
  }

  // Google Calendar button
  const gcalBtn = document.getElementById('gcal-btn');
  if (gcalBtn) gcalBtn.addEventListener('click', openGoogleCalendar);

  // Handle OAuth callback redirect (?gcal=connected / ?gcal=denied)
  const gcalParam = new URLSearchParams(window.location.search).get('gcal');
  if (gcalParam === 'connected') {
    history.replaceState(null, '', window.location.pathname);
    // Now authenticated — push events immediately
    openGoogleCalendar();
  } else if (gcalParam === 'denied') {
    history.replaceState(null, '', window.location.pathname);
    showGcalToast('Google Calendar access was denied.');
  }

  // Export to Apple Calendar button
  const exportCalBtn = document.getElementById('export-cal-btn');
  if (exportCalBtn) exportCalBtn.addEventListener('click', exportCalendar);

  // Init looping knot for replan overlay (dead code canvas, looping version)
  const knotReplan = document.getElementById('knot-canvas-replan');
  if (knotReplan) startKnotAnimation(knotReplan);

  // Start fresh button
  const freshBtn = document.getElementById('start-fresh-btn');
  if (freshBtn) {
    freshBtn.addEventListener('click', () => {
      // Reset brain dump screen and show overlay
      const brainDumpEl = document.getElementById('brain-dump');
      if (brainDumpEl) brainDumpEl.value = '';
      brainDumpText = '';

      // Reset plan button to original arrow state (JS may have changed it to play icon)
      const planBtn = document.getElementById('plan-btn');
      if (planBtn) { planBtn.disabled = false; planBtn.innerHTML = 'Untangle my day \u2192'; }

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
