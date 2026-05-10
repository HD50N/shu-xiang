// Vanilla overlay for the in-flow pause beat.
// Injected into the form page via Playwright page.evaluate().
// No build step. No React. No bundle. ~150 lines.
//
// Public API (called from Python via page.evaluate):
//   window.shuxiang.showOverlay({ selector, questionZh, explanationZh, listeningLabelZh })
//   window.shuxiang.markListening(state)   // 'listening' | 'thinking' | 'recorded'
//   window.shuxiang.hideOverlay()
//   window.shuxiang.showSidebar({ transcript, fields })
//   window.shuxiang.updateSidebarField(name, value)
//   window.shuxiang.hideSidebar()
//   window.shuxiang.showToast({ kind, textZh })  // 'info' | 'success' | 'error'

(function () {
  if (window.shuxiang && window.shuxiang._installed) return;

  const NS = "shuxiang";
  const ROOT_ID = `${NS}-root`;
  const TRANSCRIPT_TEXT_KEY = `${NS}:liveTranscriptText`;
  const TRANSCRIPT_ENTRIES_KEY = `${NS}:liveTranscriptEntries`;
  const TRANSCRIPT_POSITION_KEY = `${NS}:liveTranscriptPosition`;

  const TOKENS = {
    ringColor: "#D97706",
    ringGlow: "rgba(217, 119, 6, 0.25)",
    successGreen: "#10B981",
    cardBg: "#FFFFFF",
    cardBorder: "#E5E5E5",
    cardShadow: "0 4px 12px rgba(0, 0, 0, 0.06)",
    textPrimary: "#1A1A1A",
    textSecondary: "#4A5568",
    textMuted: "#9CA3AF",
  };

  // Inject one-time stylesheet.
  function installStyles() {
    if (document.getElementById(`${NS}-styles`)) return;
    const style = document.createElement("style");
    style.id = `${NS}-styles`;
    style.textContent = `
      .${NS}-ring {
        position: absolute;
        pointer-events: none;
        border: 2px solid ${TOKENS.ringColor};
        border-radius: 4px;
        box-shadow: 0 0 0 8px ${TOKENS.ringGlow};
        z-index: 9998;
        opacity: 0;
        transition: opacity 200ms ease-out, border-color 300ms ease-out;
      }
      .${NS}-ring--visible { opacity: 1; }
      .${NS}-ring--success {
        border-color: ${TOKENS.successGreen};
        box-shadow: 0 0 0 8px rgba(16, 185, 129, 0.25);
      }

      .${NS}-card {
        position: absolute;
        width: 320px;
        padding: 24px;
        background: ${TOKENS.cardBg};
        border: 1px solid ${TOKENS.cardBorder};
        border-radius: 8px;
        box-shadow: ${TOKENS.cardShadow};
        z-index: 9999;
        opacity: 0;
        transform: translateX(8px);
        transition: opacity 250ms ease-out, transform 250ms ease-out;
        font-family: 'Noto Sans SC', -apple-system, sans-serif;
      }
      .${NS}-card--visible { opacity: 1; transform: translateX(0); }

      .${NS}-question {
        font-size: 20px;
        font-weight: 700;
        line-height: 1.4;
        color: ${TOKENS.textPrimary};
        margin: 0 0 12px 0;
      }
      .${NS}-explanation {
        font-size: 14px;
        line-height: 1.6;
        color: ${TOKENS.textSecondary};
        margin: 0 0 20px 0;
        white-space: pre-wrap;
      }

      .${NS}-listening {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        font-weight: 400;
        color: ${TOKENS.textMuted};
      }
      .${NS}-dots { display: inline-flex; gap: 4px; }
      .${NS}-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: ${TOKENS.ringColor};
        animation: ${NS}-pulse 1.2s ease-in-out infinite;
      }
      .${NS}-dot:nth-child(2) { animation-delay: 0.2s; }
      .${NS}-dot:nth-child(3) { animation-delay: 0.4s; }
      @keyframes ${NS}-pulse {
        0%, 100% { opacity: 0.3; transform: scale(0.8); }
        50% { opacity: 1; transform: scale(1); }
      }

      .${NS}-sidebar {
        position: fixed;
        top: 0;
        right: 0;
        width: 280px;
        height: 100vh;
        background: ${TOKENS.cardBg};
        border-left: 1px solid ${TOKENS.cardBorder};
        padding: 24px 20px;
        box-sizing: border-box;
        z-index: 9997;
        font-family: 'Noto Sans SC', -apple-system, sans-serif;
        opacity: 0;
        transform: translateX(8px);
        transition: opacity 250ms ease-out, transform 250ms ease-out;
        overflow-y: auto;
      }
      .${NS}-sidebar--visible { opacity: 1; transform: translateX(0); }
      .${NS}-sidebar--collapsed {
        width: 48px;
        padding: 16px 8px;
        overflow: visible;
      }
      .${NS}-sidebar-toggle {
        position: sticky;
        top: 0;
        float: right;
        width: 28px;
        height: 28px;
        border: 1px solid ${TOKENS.cardBorder};
        border-radius: 999px;
        background: ${TOKENS.cardBg};
        color: ${TOKENS.textSecondary};
        box-shadow: ${TOKENS.cardShadow};
        cursor: pointer;
        font-size: 16px;
        line-height: 1;
        z-index: 1;
      }
      .${NS}-sidebar--collapsed .${NS}-sidebar-content {
        display: none;
      }
      .${NS}-sidebar--collapsed .${NS}-sidebar-toggle {
        float: none;
        transform: rotate(180deg);
      }
      .${NS}-sidebar h3 {
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: ${TOKENS.textMuted};
        margin: 0 0 12px 0;
      }
      .${NS}-transcript {
        font-size: 14px;
        line-height: 1.6;
        color: ${TOKENS.textPrimary};
        padding-bottom: 20px;
        margin-bottom: 20px;
        border-bottom: 1px solid ${TOKENS.cardBorder};
      }
      .${NS}-fields { font-size: 13px; line-height: 1.8; }
      .${NS}-field {
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }
      .${NS}-field-name { color: ${TOKENS.textSecondary}; flex-shrink: 0; }
      .${NS}-field-value {
        color: ${TOKENS.textMuted};
        text-align: right;
        font-variant-numeric: tabular-nums;
        transition: color 250ms ease-out;
      }
      .${NS}-field-value--filled {
        color: ${TOKENS.textPrimary};
        font-weight: 500;
      }

      .${NS}-toast {
        position: fixed;
        bottom: 24px;
        right: 24px;
        padding: 12px 20px;
        background: ${TOKENS.cardBg};
        border: 1px solid ${TOKENS.cardBorder};
        border-radius: 8px;
        box-shadow: ${TOKENS.cardShadow};
        font-family: 'Noto Sans SC', -apple-system, sans-serif;
        font-size: 13px;
        color: ${TOKENS.textPrimary};
        z-index: 10000;
        opacity: 0;
        transform: translateY(8px);
        transition: opacity 250ms ease-out, transform 250ms ease-out;
        max-width: 360px;
      }
      .${NS}-toast--visible { opacity: 1; transform: translateY(0); }
      .${NS}-toast--success { border-color: ${TOKENS.successGreen}; }
      .${NS}-toast--error {
        background: #FEF2F2;
        border-color: #FCA5A5;
        color: #991B1B;
      }
      .${NS}-live-transcript {
        position: fixed;
        left: 50%;
        bottom: max(88px, calc(env(safe-area-inset-bottom, 0px) + 72px));
        transform: translate(-50%, 8px);
        z-index: 10003;
        min-width: 320px;
        max-width: min(760px, calc(100vw - 48px));
        max-height: 180px;
        padding: 12px 16px;
        border: 1px solid ${TOKENS.cardBorder};
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: ${TOKENS.cardShadow};
        color: ${TOKENS.textPrimary};
        font-family: 'Noto Sans SC', -apple-system, sans-serif;
        font-size: 14px;
        line-height: 1.45;
        opacity: 0;
        cursor: grab;
        pointer-events: auto;
        transition: opacity 180ms ease-out, transform 180ms ease-out;
        user-select: none;
        overflow: hidden;
        text-align: left;
      }
      .${NS}-live-transcript--dragging {
        cursor: grabbing;
        transition: opacity 180ms ease-out;
      }
      .${NS}-live-transcript--visible {
        opacity: 1;
        transform: translate(-50%, 0);
      }
      .${NS}-live-transcript-label {
        display: block;
        color: ${TOKENS.textMuted};
        font-size: 11px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 6px;
      }
      .${NS}-live-transcript-lines {
        display: flex;
        flex-direction: column;
        gap: 4px;
        max-height: 142px;
        overflow-y: auto;
        padding-right: 4px;
      }
      .${NS}-live-transcript-line {
        display: flex;
        gap: 8px;
        align-items: baseline;
      }
      .${NS}-live-transcript-speaker {
        flex: 0 0 auto;
        color: ${TOKENS.textMuted};
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
      }
      .${NS}-live-transcript-body {
        min-width: 0;
        color: ${TOKENS.textPrimary};
        white-space: normal;
        overflow-wrap: anywhere;
      }
    `;
    document.head.appendChild(style);
  }

  function getRoot() {
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      root = document.createElement("div");
      root.id = ROOT_ID;
      document.body.appendChild(root);
    }
    return root;
  }

  function positionRing(targetEl, ringEl) {
    const r = targetEl.getBoundingClientRect();
    const scrollY = window.scrollY || document.documentElement.scrollTop;
    const scrollX = window.scrollX || document.documentElement.scrollLeft;
    ringEl.style.top = `${r.top + scrollY - 4}px`;
    ringEl.style.left = `${r.left + scrollX - 4}px`;
    ringEl.style.width = `${r.width + 8}px`;
    ringEl.style.height = `${r.height + 8}px`;
  }

  function positionCard(targetEl, cardEl) {
    const r = targetEl.getBoundingClientRect();
    const scrollY = window.scrollY || document.documentElement.scrollTop;
    const scrollX = window.scrollX || document.documentElement.scrollLeft;
    // Anchor upper-right of the field, 16px offset.
    let left = r.right + scrollX + 16;
    let top = r.top + scrollY;
    // Viewport-edge protection: flip to left of field if card would overflow right edge.
    const cardWidth = 320;
    if (left + cardWidth > window.innerWidth + scrollX - 8) {
      left = r.left + scrollX - cardWidth - 16;
    }
    cardEl.style.top = `${top}px`;
    cardEl.style.left = `${left}px`;
  }

  const state = {
    ring: null,
    card: null,
    sidebar: null,
    toast: null,
    liveTranscript: null,
    target: null,
    listeningEl: null,
    lang: "zh",
    customCopy: null,
  };

  const TEXT = {
    zh: {
      listening: "正在聆听…",
      thinking: "正在思考…",
      recorded: "已记录",
      retry: "请再说一次",
      recognizing: "识别中…",
      transcript: "实时转写",
      transcriptUser: "你",
      transcriptAgent: "AI",
      extractedFields: "提取字段",
      emptyValue: "—",
      micReady: "麦克风已开启 · 请说话",
      micIdle: "点击录音",
      micRecording: "录音中 · 点击停止",
      checklistEyebrow: "你的合规清单 · OBLIGATIONS MAP",
      checklistTitle: "为你的餐厅定制的清单",
      checklistSubtitle: (count) => `${count} 项, 按顺序处理`,
      citation: "引用 →",
      hour: (n) => `约 ${n} 小时`,
      minute: (n) => `约 ${n} 分钟`,
      free: "免费",
    },
    en: {
      listening: "Listening...",
      thinking: "Thinking...",
      recorded: "Recorded",
      retry: "Please try again",
      recognizing: "Recognizing...",
      transcript: "Transcript",
      transcriptUser: "You",
      transcriptAgent: "AI",
      extractedFields: "Extracted fields",
      emptyValue: "—",
      micReady: "Microphone is on · please speak",
      micIdle: "Tap to record",
      micRecording: "Recording · tap to stop",
      checklistEyebrow: "Your Compliance Checklist · OBLIGATIONS MAP",
      checklistTitle: "Checklist for your restaurant",
      checklistSubtitle: (count) => `${count} items, handled in order`,
      citation: "Source →",
      hour: (n) => `about ${n} hour${n === 1 ? "" : "s"}`,
      minute: (n) => `about ${n} minute${n === 1 ? "" : "s"}`,
      free: "free",
    },
  };

  function copy() {
    return state.customCopy || TEXT[state.lang] || TEXT.zh;
  }

  function normalizeCopy(customCopy) {
    if (!customCopy) return null;
    const base = TEXT.en;
    const normalized = { ...base, ...customCopy };
    ["checklistSubtitle", "hour", "minute"].forEach((key) => {
      if (typeof normalized[key] === "string") {
        const template = normalized[key];
        normalized[key] = (value) => template.replace("{count}", value).replace("{n}", value);
      }
    });
    return normalized;
  }

  function setLanguage(config) {
    const lang = typeof config === "string" ? config : (config && config.code);
    state.lang = lang === "en" ? "en" : (lang === "zh" ? "zh" : "custom");
    state.customCopy = typeof config === "object" ? normalizeCopy(config.copy) : null;
    if (state.listeningEl) state.listeningEl.textContent = copy().listening;
    if (state.micBtn) setMicState(!state.micBtn.classList.contains(`${NS}-mic-btn--listening`));
    if (state.liveTranscript) {
      state.liveTranscript.querySelector(`.${NS}-live-transcript-label`).textContent = copy().transcript;
      renderTranscriptEntries(state.liveTranscript, readTranscriptEntries());
    }
  }

  function showOverlay({ selector, questionZh, explanationZh, listeningLabelZh }) {
    installStyles();
    const target = document.querySelector(selector);
    if (!target) {
      console.error(`[${NS}] selector not found:`, selector);
      return false;
    }
    hideOverlay();
    const root = getRoot();

    const ring = document.createElement("div");
    ring.className = `${NS}-ring`;
    positionRing(target, ring);
    root.appendChild(ring);

    const card = document.createElement("div");
    card.className = `${NS}-card`;
    card.innerHTML = `
      <div class="${NS}-question"></div>
      <div class="${NS}-explanation"></div>
      <div class="${NS}-listening">
        <span class="${NS}-dots"><span class="${NS}-dot"></span><span class="${NS}-dot"></span><span class="${NS}-dot"></span></span>
        <span class="${NS}-listening-label"></span>
      </div>
    `;
    card.querySelector(`.${NS}-question`).textContent = questionZh;
    card.querySelector(`.${NS}-explanation`).textContent = explanationZh;
    card.querySelector(`.${NS}-listening-label`).textContent = listeningLabelZh || copy().listening;
    positionCard(target, card);
    root.appendChild(card);

    state.ring = ring;
    state.card = card;
    state.target = target;
    state.listeningEl = card.querySelector(`.${NS}-listening-label`);

    // Sequential entrance: ring first, card 50ms after.
    requestAnimationFrame(() => {
      ring.classList.add(`${NS}-ring--visible`);
      setTimeout(() => card.classList.add(`${NS}-card--visible`), 50);
    });

    // Reposition on resize/scroll.
    state._reposition = () => {
      if (state.target && state.ring) positionRing(state.target, state.ring);
      if (state.target && state.card) positionCard(state.target, state.card);
    };
    window.addEventListener("resize", state._reposition);
    window.addEventListener("scroll", state._reposition, { passive: true });
    return true;
  }

  function markListening(stateLabel) {
    if (!state.listeningEl) return;
    const map = {
      listening: copy().listening,
      thinking: copy().thinking,
      recorded: copy().recorded,
      retry: copy().retry,
    };
    state.listeningEl.textContent = map[stateLabel] || stateLabel;
    if (stateLabel === "recorded" && state.ring) {
      state.ring.classList.add(`${NS}-ring--success`);
    }
  }

  function hideOverlay() {
    if (state._reposition) {
      window.removeEventListener("resize", state._reposition);
      window.removeEventListener("scroll", state._reposition);
      state._reposition = null;
    }
    [state.ring, state.card].forEach((el) => {
      if (el) {
        el.classList.remove(`${NS}-ring--visible`, `${NS}-card--visible`);
        setTimeout(() => el.remove(), 250);
      }
    });
    state.ring = null;
    state.card = null;
    state.target = null;
    state.listeningEl = null;
  }

  // fields = [{ key, labelZh, value }] — `key` is the stable schema key,
  // `labelZh` is the localized display label, `value` is initial text (may be empty).
  function showSidebar({ transcript, fields }) {
    installStyles();
    const root = getRoot();
    hideSidebar();
    const sidebar = document.createElement("aside");
    sidebar.className = `${NS}-sidebar`;
    sidebar.innerHTML = `
      <button type="button" class="${NS}-sidebar-toggle" aria-label="Collapse sidebar">›</button>
      <div class="${NS}-sidebar-content">
        <h3></h3>
        <div class="${NS}-transcript"></div>
        <h3></h3>
        <div class="${NS}-fields"></div>
      </div>
    `;
    sidebar.querySelector(`.${NS}-sidebar-toggle`).addEventListener("click", () => {
      sidebar.classList.toggle(`${NS}-sidebar--collapsed`);
    });
    const headings = sidebar.querySelectorAll("h3");
    headings[0].textContent = copy().recognizing;
    headings[1].textContent = copy().extractedFields;
    sidebar.querySelector(`.${NS}-transcript`).textContent = transcript || "";
    const fieldsRoot = sidebar.querySelector(`.${NS}-fields`);
    (fields || []).forEach((f) => {
      const row = document.createElement("div");
      row.className = `${NS}-field`;
      row.dataset.field = f.key;
      row.innerHTML = `<span class="${NS}-field-name"></span><span class="${NS}-field-value"></span>`;
      row.querySelector(`.${NS}-field-name`).textContent = f.labelZh;
      const v = row.querySelector(`.${NS}-field-value`);
      v.textContent = f.value || copy().emptyValue;
      if (f.value) v.classList.add(`${NS}-field-value--filled`);
      fieldsRoot.appendChild(row);
    });
    document.body.appendChild(sidebar);
    state.sidebar = sidebar;
    requestAnimationFrame(() => sidebar.classList.add(`${NS}-sidebar--visible`));
  }

  function safeSessionGet(key) {
    try { return window.sessionStorage && window.sessionStorage.getItem(key); }
    catch (e) { return null; }
  }

  function safeSessionSet(key, value) {
    try {
      if (window.sessionStorage) window.sessionStorage.setItem(key, value);
    } catch (e) { /* ignore */ }
  }

  function transcriptSpeakerLabel(speaker) {
    if (speaker === "agent") return copy().transcriptAgent || "AI";
    if (speaker === "user") return copy().transcriptUser || "You";
    return speaker || "";
  }

  function readTranscriptEntries() {
    try {
      const entries = JSON.parse(safeSessionGet(TRANSCRIPT_ENTRIES_KEY) || "[]");
      if (Array.isArray(entries)) return entries;
    } catch (e) { /* ignore */ }
    const legacyText = (safeSessionGet(TRANSCRIPT_TEXT_KEY) || "").trim();
    return legacyText ? [{ speaker: "user", text: legacyText }] : [];
  }

  function compactTranscriptEntries(entries) {
    const latest = {};
    entries.forEach((entry) => {
      if (entry && entry.speaker && entry.text) latest[entry.speaker] = entry;
    });
    return ["agent", "user"].map((speaker) => latest[speaker]).filter(Boolean);
  }

  function writeTranscriptEntries(entries) {
    safeSessionSet(TRANSCRIPT_ENTRIES_KEY, JSON.stringify(compactTranscriptEntries(entries)));
  }

  function renderTranscriptEntries(el, entries) {
    const lines = el.querySelector(`.${NS}-live-transcript-lines`);
    lines.innerHTML = "";
    compactTranscriptEntries(entries).forEach((entry) => {
      const row = document.createElement("div");
      row.className = `${NS}-live-transcript-line`;
      const speaker = document.createElement("span");
      speaker.className = `${NS}-live-transcript-speaker`;
      speaker.textContent = transcriptSpeakerLabel(entry.speaker);
      const body = document.createElement("span");
      body.className = `${NS}-live-transcript-body`;
      body.textContent = entry.text || "";
      row.appendChild(speaker);
      row.appendChild(body);
      lines.appendChild(row);
    });
    lines.scrollTop = lines.scrollHeight;
  }

  function clampTranscriptPosition(left, top, el) {
    const width = el.offsetWidth || 360;
    const height = el.offsetHeight || 48;
    return {
      left: Math.max(8, Math.min(left, window.innerWidth - width - 8)),
      top: Math.max(8, Math.min(top, window.innerHeight - height - 8)),
    };
  }

  function applyTranscriptPosition(el, position) {
    if (!position) return;
    const clamped = clampTranscriptPosition(position.left, position.top, el);
    el.style.left = `${clamped.left}px`;
    el.style.top = `${clamped.top}px`;
    el.style.right = "auto";
    el.style.bottom = "auto";
    el.style.transform = "none";
  }

  function makeTranscriptDraggable(el) {
    if (el.dataset.dragReady === "true") return;
    el.dataset.dragReady = "true";
    let drag = null;

    el.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const rect = el.getBoundingClientRect();
      drag = {
        dx: event.clientX - rect.left,
        dy: event.clientY - rect.top,
      };
      el.classList.add(`${NS}-live-transcript--dragging`);
      el.setPointerCapture(event.pointerId);
      event.preventDefault();
    });

    el.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const next = clampTranscriptPosition(event.clientX - drag.dx, event.clientY - drag.dy, el);
      el.style.left = `${next.left}px`;
      el.style.top = `${next.top}px`;
      el.style.right = "auto";
      el.style.bottom = "auto";
      el.style.transform = "none";
    });

    const finishDrag = (event) => {
      if (!drag) return;
      drag = null;
      el.classList.remove(`${NS}-live-transcript--dragging`);
      try { el.releasePointerCapture(event.pointerId); } catch (e) { /* ignore */ }
      const rect = el.getBoundingClientRect();
      safeSessionSet(TRANSCRIPT_POSITION_KEY, JSON.stringify({ left: rect.left, top: rect.top }));
    };

    el.addEventListener("pointerup", finishDrag);
    el.addEventListener("pointercancel", finishDrag);
  }

  function ensureLiveTranscript() {
    installStyles();
    if (state.liveTranscript && document.documentElement.contains(state.liveTranscript)) {
      return state.liveTranscript;
    }
    const el = document.createElement("div");
    el.className = `${NS}-live-transcript`;
    el.innerHTML = `<span class="${NS}-live-transcript-label"></span><div class="${NS}-live-transcript-lines"></div>`;
    (document.body || document.documentElement).appendChild(el);
    state.liveTranscript = el;
    makeTranscriptDraggable(el);

    try {
      const storedPosition = JSON.parse(safeSessionGet(TRANSCRIPT_POSITION_KEY) || "null");
      applyTranscriptPosition(el, storedPosition);
    } catch (e) { /* ignore malformed stored positions */ }
    return el;
  }

  function restoreLiveTranscript() {
    const entries = readTranscriptEntries();
    if (entries.length) updateLiveTranscript({ entries });
  }

  function updateLiveTranscript(payload) {
    const isObject = payload && typeof payload === "object";
    const value = (isObject ? (payload.text || "") : (payload || "")).trim();
    const speaker = isObject ? (payload.speaker || "user") : "user";
    let entries = isObject && Array.isArray(payload.entries) ? payload.entries : readTranscriptEntries();
    if (value) {
      entries = compactTranscriptEntries([
        ...entries.filter((entry) => entry.speaker !== speaker),
        { speaker, text: value },
      ]);
      writeTranscriptEntries(entries);
      safeSessionSet(TRANSCRIPT_TEXT_KEY, value);
    }
    const el = ensureLiveTranscript();
    el.querySelector(`.${NS}-live-transcript-label`).textContent = copy().transcript;
    renderTranscriptEntries(el, entries);
    el.classList.toggle(`${NS}-live-transcript--visible`, entries.length > 0);

    const openingWrap = speaker === "user" ? document.querySelector(`.${NS}-opening-transcript`) : null;
    if (openingWrap) {
      const cursor = openingWrap.querySelector(`.${NS}-opening-transcript-cursor`);
      let span = openingWrap.querySelector(`span:not(.${NS}-opening-transcript-cursor)`);
      if (!span) {
        span = document.createElement("span");
        if (cursor) openingWrap.insertBefore(span, cursor);
        else openingWrap.appendChild(span);
      }
      span.textContent = value;
    }
  }

  function stopSpeech() {
    const audio = window.__shuxiangActiveAudio;
    if (!audio) return;
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (e) { /* ignore */ }
    if (typeof audio.__shuxiangResolve === "function") {
      audio.__shuxiangResolve();
    }
    window.__shuxiangActiveAudio = null;
  }

  // Call with the SCHEMA_KEY (stable), not display label.
  function updateSidebarField(key, value) {
    if (!state.sidebar) return;
    const row = state.sidebar.querySelector(`.${NS}-field[data-field="${key}"]`);
    if (!row) return;
    const v = row.querySelector(`.${NS}-field-value`);
    v.textContent = value;
    v.classList.add(`${NS}-field-value--filled`);
  }

  function hideSidebar() {
    if (!state.sidebar) return;
    const s = state.sidebar;
    s.classList.remove(`${NS}-sidebar--visible`);
    setTimeout(() => s.remove(), 250);
    state.sidebar = null;
  }

  // ── Opening prompt ─────────────────────────────────────────────────
  // A full-screen scrim with the localized prompt + a live transcript area.
  // The typewriter beat happens INSIDE this card (visible to the judge).
  // After the sentence finishes, the scrim fades out to reveal the form.
  function showOpeningPrompt({ promptZh }) {
    installStyles();
    if (!document.getElementById(`${NS}-opening-styles`)) {
      const s = document.createElement("style");
      s.id = `${NS}-opening-styles`;
      s.textContent = `
        .${NS}-opening {
          position: fixed; inset: 0; z-index: 10001;
          background: rgba(255,255,255,0.96);
          display: flex; align-items: center; justify-content: center;
          opacity: 0; transition: opacity 350ms ease-out;
          font-family: 'Noto Sans SC', -apple-system, sans-serif;
        }
        .${NS}-opening--visible { opacity: 1; }
        .${NS}-opening-card {
          max-width: 720px; padding: 48px 56px;
          text-align: center;
        }
        .${NS}-opening-prompt {
          font-size: 32px; font-weight: 700; color: ${TOKENS.textPrimary};
          line-height: 1.4; margin: 0 0 24px 0;
        }
        .${NS}-opening-mic {
          display: inline-flex; align-items: center; gap: 8px;
          padding: 10px 18px;
          background: ${TOKENS.cardBg}; border: 1px solid ${TOKENS.cardBorder};
          border-radius: 999px; box-shadow: ${TOKENS.cardShadow};
          font-size: 13px; color: ${TOKENS.textMuted};
          margin-bottom: 32px;
        }
        .${NS}-opening-mic-dot {
          width: 8px; height: 8px; border-radius: 50%;
          background: ${TOKENS.ringColor};
          animation: ${NS}-pulse 1.2s ease-in-out infinite;
        }
        .${NS}-opening-transcript {
          min-height: 64px;
          font-size: 22px; line-height: 1.6;
          color: ${TOKENS.textPrimary};
          font-weight: 400;
          padding: 20px 24px;
          background: ${TOKENS.cardBg};
          border: 1px solid ${TOKENS.cardBorder};
          border-radius: 12px;
          box-shadow: ${TOKENS.cardShadow};
          text-align: left;
          position: relative;
        }
        .${NS}-opening-transcript:empty::before {
          content: '\\200B';  /* zero-width space keeps height stable */
        }
        .${NS}-opening-transcript-cursor {
          display: inline-block;
          width: 2px;
          height: 1em;
          background: ${TOKENS.ringColor};
          margin-left: 2px;
          vertical-align: text-bottom;
          animation: ${NS}-cursor-blink 0.9s steps(2, start) infinite;
        }
        @keyframes ${NS}-cursor-blink { to { visibility: hidden; } }
      `;
      document.head.appendChild(s);
    }
    const root = getRoot();
    const el = document.createElement("div");
    el.className = `${NS}-opening`;
    el.innerHTML = `
      <div class="${NS}-opening-card">
        <div class="${NS}-opening-prompt"></div>
        <div class="${NS}-opening-mic">
          <span class="${NS}-opening-mic-dot"></span>
          <span class="${NS}-opening-mic-label"></span>
        </div>
        <div class="${NS}-opening-transcript"><span class="${NS}-opening-transcript-cursor"></span></div>
      </div>
    `;
    el.querySelector(`.${NS}-opening-prompt`).textContent = promptZh;
    el.querySelector(`.${NS}-opening-mic-label`).textContent = copy().micReady;
    root.appendChild(el);
    state.opening = el;
    requestAnimationFrame(() => el.classList.add(`${NS}-opening--visible`));
  }

  // Type the user's sentence into the opening prompt's transcript area.
  // Called between showOpeningPrompt() and hideOpeningPrompt() — this IS
  // the visible "user speaking" beat.
  async function typeOpeningTranscript({ fullText, perCharMs }) {
    if (!state.opening) return;
    const wrap = state.opening.querySelector(`.${NS}-opening-transcript`);
    if (!wrap) return;
    const cursor = wrap.querySelector(`.${NS}-opening-transcript-cursor`);
    // Wipe existing content but keep the cursor.
    wrap.innerHTML = "";
    const text = document.createElement("span");
    wrap.appendChild(text);
    if (cursor) wrap.appendChild(cursor);
    for (let i = 0; i < fullText.length; i++) {
      text.textContent += fullText[i];
      await new Promise((r) => setTimeout(r, perCharMs));
    }
  }

  function hideOpeningPrompt() {
    if (!state.opening) return;
    const el = state.opening;
    el.classList.remove(`${NS}-opening--visible`);
    setTimeout(() => el.remove(), 350);
    state.opening = null;
  }

  // ── Sidebar transcript typewriter ──────────────────────────────────
  // Reveal the sentence character-by-character to sell "user is speaking"
  // in recording mode (no real STT roundtrip).
  async function typeTranscript({ fullText, perCharMs }) {
    if (!state.sidebar) return;
    const node = state.sidebar.querySelector(`.${NS}-transcript`);
    if (!node) return;
    node.textContent = "";
    for (let i = 0; i < fullText.length; i++) {
      node.textContent += fullText[i];
      await new Promise((r) => setTimeout(r, perCharMs));
    }
  }

  // ── Closing scene ──────────────────────────────────────────────────
  function showClosing({ messageZh }) {
    installStyles();
    if (!document.getElementById(`${NS}-closing-styles`)) {
      const s = document.createElement("style");
      s.id = `${NS}-closing-styles`;
      s.textContent = `
        .${NS}-closing {
          position: fixed; inset: 0; z-index: 10002;
          background: rgba(255,255,255,0.96);
          display: flex; align-items: center; justify-content: center;
          opacity: 0; transition: opacity 350ms ease-out;
          font-family: 'Noto Sans SC', -apple-system, sans-serif;
        }
        .${NS}-closing--visible { opacity: 1; }
        .${NS}-closing-card {
          max-width: 720px; padding: 56px 64px;
          text-align: center;
        }
        .${NS}-closing-check {
          width: 64px; height: 64px; border-radius: 50%;
          background: ${TOKENS.successGreen}; color: #fff;
          display: inline-flex; align-items: center; justify-content: center;
          font-size: 32px; line-height: 1; margin-bottom: 24px;
        }
        .${NS}-closing-msg {
          font-size: 28px; font-weight: 700; color: ${TOKENS.textPrimary};
          line-height: 1.5;
        }
      `;
      document.head.appendChild(s);
    }
    const root = getRoot();
    const el = document.createElement("div");
    el.className = `${NS}-closing`;
    el.innerHTML = `
      <div class="${NS}-closing-card">
        <div class="${NS}-closing-check">✓</div>
        <div class="${NS}-closing-msg"></div>
      </div>
    `;
    el.querySelector(`.${NS}-closing-msg`).textContent = messageZh;
    root.appendChild(el);
    state.closing = el;
    requestAnimationFrame(() => el.classList.add(`${NS}-closing--visible`));
  }

  function showToast({ kind, textZh, durationMs }) {
    installStyles();
    if (state.toast) state.toast.remove();
    const toast = document.createElement("div");
    toast.className = `${NS}-toast ${NS}-toast--${kind || "info"}`;
    toast.textContent = textZh;
    document.body.appendChild(toast);
    state.toast = toast;
    requestAnimationFrame(() => toast.classList.add(`${NS}-toast--visible`));
    if (durationMs) {
      setTimeout(() => {
        toast.classList.remove(`${NS}-toast--visible`);
        setTimeout(() => toast.remove(), 250);
      }, durationMs);
    }
  }

  // ── Mic button (mute/unmute toggle) ────────────────────────────────
  // Floating bottom-right pill with a mic icon. Clicking calls window.toggleMic
  // (exposed from Python via page.expose_function). Visual reflects state:
  //   muted    → grey pill, slashed mic
  //   listening → amber pill, pulsing mic + localized label
  // Always re-attach to documentElement so SPA navigations / form-based
  // pages that rewrite document.body don't wipe the button. Position is
  // top-right with a huge offset so it can't fall below a smaller viewport.
  function installMicButton() {
    if (document.getElementById(`${NS}-mic-btn`)) {
      return;
    }
    installStyles();
    if (!document.getElementById(`${NS}-mic-styles`)) {
      const s = document.createElement("style");
      s.id = `${NS}-mic-styles`;
      s.textContent = `
        /* MUTED: bright amber pill in TOP-RIGHT so it's always visible
           regardless of viewport size or page DOM rewriting */
        .${NS}-mic-btn {
          position: fixed; top: 24px; right: 24px; z-index: 2147483647;
          display: inline-flex; align-items: center; gap: 14px;
          padding: 18px 26px;
          background: ${TOKENS.ringColor};
          border: 3px solid #B45309;
          border-radius: 999px;
          box-shadow: 0 10px 28px rgba(0,0,0,0.30), 0 0 0 0 rgba(217,119,6,0.55);
          font-family: 'Noto Sans SC', -apple-system, sans-serif;
          font-size: 16px; font-weight: 700;
          color: #fff;
          cursor: pointer;
          user-select: none;
          transition: background 200ms ease, color 200ms ease, border-color 200ms ease, transform 150ms ease;
        }
        .${NS}-mic-btn:hover {
          transform: translateY(-2px) scale(1.03);
        }
        .${NS}-mic-btn:active { transform: translateY(0) scale(1); }
        /* MUTED idle: bigger pulse halo so it's impossible to miss */
        .${NS}-mic-btn:not(.${NS}-mic-btn--listening) {
          animation: ${NS}-mic-idle-pulse 1.8s ease-in-out infinite;
        }
        @keyframes ${NS}-mic-idle-pulse {
          0%, 100% { box-shadow: 0 10px 28px rgba(0,0,0,0.30), 0 0 0 0 rgba(217,119,6,0.65); }
          50% { box-shadow: 0 10px 28px rgba(0,0,0,0.30), 0 0 0 22px rgba(217,119,6,0); }
        }
        /* LISTENING: switches to GREEN (recording active) */
        .${NS}-mic-btn--listening {
          background: ${TOKENS.successGreen};
          border-color: #047857;
          color: #fff;
          animation: ${NS}-mic-listening-pulse 1.2s ease-in-out infinite;
        }
        @keyframes ${NS}-mic-listening-pulse {
          0%, 100% { box-shadow: 0 10px 28px rgba(0,0,0,0.30), 0 0 0 0 rgba(16,185,129,0.65); }
          50% { box-shadow: 0 10px 28px rgba(0,0,0,0.30), 0 0 0 18px rgba(16,185,129,0); }
        }
        .${NS}-mic-icon {
          width: 20px; height: 20px;
          display: inline-flex; align-items: center; justify-content: center;
          position: relative;
        }
        .${NS}-mic-label-zh { white-space: nowrap; }
      `;
      document.head.appendChild(s);
    }
    const btn = document.createElement("button");
    btn.id = `${NS}-mic-btn`;
    btn.className = `${NS}-mic-btn`;
    btn.type = "button";
    btn.innerHTML = `
      <span class="${NS}-mic-icon" style="position:relative;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
          <path d="M19 10v1a7 7 0 0 1-14 0v-1"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      </span>
      <span class="${NS}-mic-label-zh"></span>
    `;
    btn.querySelector(`.${NS}-mic-label-zh`).textContent = copy().micIdle;
    btn.addEventListener("click", async () => {
      console.log("[shuxiang] mic button clicked, toggleMic=", typeof window.toggleMic);
      const willStartListening = !btn.classList.contains(`${NS}-mic-btn--listening`);
      if (willStartListening) stopSpeech();
      if (typeof window.toggleMic === "function") {
        await window.toggleMic();
      } else {
        console.warn("[shuxiang] window.toggleMic not exposed yet");
      }
    });
    // Attach to documentElement (the <html> tag) — survives any code that
    // rewrites document.body (some IL SOS pages do this on form submit).
    (document.documentElement || document.body).appendChild(btn);
    state.micBtn = btn;
    console.log("[shuxiang] mic button installed at TOP-RIGHT");

    // Watchdog: if anything removes the button (page nav, DOM rewrite, etc.)
    // re-attach it every 500ms while state.micWatchdog is true.
    if (!state.micWatchdog) {
      state.micWatchdog = setInterval(() => {
        const root = document.documentElement || document.body;
        if (!document.getElementById(`${NS}-mic-btn`) && root && state.micBtn) {
          try {
            root.appendChild(state.micBtn);
            console.log("[shuxiang] mic button re-attached by watchdog");
          } catch (e) { /* ignore */ }
        }
      }, 500);
    }
  }

  function setMicState(muted) {
    if (!state.micBtn) installMicButton();
    if (!state.micBtn) return;
    const labelEl = state.micBtn.querySelector(`.${NS}-mic-label-zh`);
    if (muted) {
      state.micBtn.classList.remove(`${NS}-mic-btn--listening`);
      if (labelEl) labelEl.textContent = copy().micIdle;
    } else {
      state.micBtn.classList.add(`${NS}-mic-btn--listening`);
      if (labelEl) labelEl.textContent = copy().micRecording;
    }
  }

  function hideMicButton() {
    if (state.micBtn) {
      state.micBtn.remove();
      state.micBtn = null;
    }
  }

  // ── Phase 2 ChecklistView ──────────────────────────────────────────
  // Slide-in panel from the right showing the obligation map. Items animate
  // in one-by-one with a stagger to create the "asymmetry-being-closed"
  // reveal moment. Each item: number, Chinese + English title, jurisdiction
  // badge (Federal / IL / Cook / Chicago), time/cost, citation link.
  function installChecklistStyles() {
    if (document.getElementById(`${NS}-checklist-styles`)) return;
    const s = document.createElement("style");
    s.id = `${NS}-checklist-styles`;
    s.textContent = `
      .${NS}-checklist {
        position: fixed; top: 0; right: 0; bottom: 0;
        width: 540px; max-width: 95vw;
        z-index: 10004;
        background: ${TOKENS.cardBg};
        border-left: 1px solid ${TOKENS.cardBorder};
        box-shadow: -8px 0 32px rgba(0,0,0,0.10);
        font-family: 'Noto Sans SC', -apple-system, sans-serif;
        opacity: 0;
        transform: translateX(20px);
        transition: opacity 350ms ease-out, transform 350ms ease-out;
        overflow-y: auto;
        padding: 32px 32px 48px;
        box-sizing: border-box;
        /* Click-through during Phase 3 so the IL SOS form buttons sitting
           under the right-edge panel remain clickable. Citation links
           override this with pointer-events: auto below. */
        pointer-events: none;
      }
      .${NS}-checklist--visible { opacity: 1; transform: translateX(0); }

      .${NS}-checklist-header {
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid ${TOKENS.cardBorder};
      }
      .${NS}-checklist-eyebrow {
        font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
        color: ${TOKENS.textMuted}; font-weight: 600;
        margin-bottom: 8px;
      }
      .${NS}-checklist-title {
        font-size: 22px; font-weight: 700; color: ${TOKENS.textPrimary};
        line-height: 1.3; margin: 0 0 6px 0;
      }
      .${NS}-checklist-subtitle {
        font-size: 13px; color: ${TOKENS.textSecondary};
        line-height: 1.5; margin: 0;
      }

      .${NS}-checklist-item {
        display: flex; gap: 14px; padding: 16px 0;
        border-bottom: 1px solid #F3F4F6;
        opacity: 0;
        transform: translateY(8px);
        transition: opacity 400ms ease-out, transform 400ms ease-out;
      }
      .${NS}-checklist-item--visible {
        opacity: 1; transform: translateY(0);
      }
      .${NS}-checklist-item:last-child { border-bottom: none; }

      .${NS}-checklist-num {
        flex-shrink: 0;
        width: 28px; height: 28px;
        border-radius: 50%;
        background: ${TOKENS.cardBg};
        border: 1.5px solid ${TOKENS.cardBorder};
        display: flex; align-items: center; justify-content: center;
        font-size: 12px; font-weight: 700;
        color: ${TOKENS.textSecondary};
      }
      .${NS}-checklist-item--active .${NS}-checklist-num {
        background: ${TOKENS.ringColor};
        border-color: ${TOKENS.ringColor};
        color: #fff;
      }
      .${NS}-checklist-item--done .${NS}-checklist-num {
        background: ${TOKENS.successGreen};
        border-color: ${TOKENS.successGreen};
        color: #fff;
      }

      .${NS}-checklist-body { flex: 1; min-width: 0; }

      .${NS}-checklist-item-title-zh {
        font-size: 15px; font-weight: 600;
        color: ${TOKENS.textPrimary};
        line-height: 1.4; margin: 0 0 2px 0;
      }
      .${NS}-checklist-item-title-en {
        font-size: 11px; color: ${TOKENS.textMuted};
        font-style: italic; margin: 0 0 6px 0;
      }
      .${NS}-checklist-item-desc {
        font-size: 12px; color: ${TOKENS.textSecondary};
        line-height: 1.55; margin: 0 0 8px 0;
      }
      .${NS}-checklist-item-meta {
        display: flex; gap: 12px; align-items: center;
        flex-wrap: wrap;
        font-size: 10px;
        color: ${TOKENS.textMuted};
      }
      .${NS}-checklist-jurisdiction-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        background: #F3F4F6;
        color: ${TOKENS.textSecondary};
        font-weight: 600;
        font-size: 10px;
        letter-spacing: 0.02em;
      }
      .${NS}-jurisdiction-Federal { background: #DBEAFE; color: #1E3A8A; }
      .${NS}-jurisdiction-Illinois { background: #FEF3C7; color: #78350F; }
      .${NS}-jurisdiction-Chicago, .${NS}-jurisdiction-Cook-County {
        background: #F3E8FF; color: #581C87;
      }

      .${NS}-checklist-citation {
        color: ${TOKENS.ringColor};
        text-decoration: none;
        font-size: 10px;
        /* Re-enable interaction since the parent panel is click-through. */
        pointer-events: auto;
      }
      .${NS}-checklist-citation:hover { text-decoration: underline; }

      .${NS}-checklist-summary {
        margin-top: 24px;
        padding: 14px 16px;
        background: #FFFBEB;
        border: 1px solid #FDE68A;
        border-radius: 8px;
        font-size: 12px;
        color: #78350F;
        line-height: 1.5;
      }
      .${NS}-checklist-summary strong { color: #451A03; }
    `;
    document.head.appendChild(s);
  }

  // items: [{ num, titleZh, titleEn, jurisdiction, descZh, citationUrl, timeMin, costUsd }]
  function showChecklist({ items, headerZh, subtitleZh, summaryZh, staggerMs }) {
    installStyles();
    installChecklistStyles();
    if (state.checklist) state.checklist.remove();
    const el = document.createElement("aside");
    el.className = `${NS}-checklist`;
    el.innerHTML = `
      <div class="${NS}-checklist-header">
        <div class="${NS}-checklist-eyebrow"></div>
        <h2 class="${NS}-checklist-title"></h2>
        <p class="${NS}-checklist-subtitle"></p>
      </div>
      <div class="${NS}-checklist-body-list"></div>
      <div class="${NS}-checklist-summary" hidden></div>
    `;
    el.querySelector(`.${NS}-checklist-eyebrow`).textContent = copy().checklistEyebrow;
    el.querySelector(`.${NS}-checklist-title`).textContent = headerZh || copy().checklistTitle;
    el.querySelector(`.${NS}-checklist-subtitle`).textContent =
      subtitleZh || copy().checklistSubtitle(items.length);
    if (summaryZh) {
      const s = el.querySelector(`.${NS}-checklist-summary`);
      s.innerHTML = summaryZh;
      s.hidden = false;
    }
    const list = el.querySelector(`.${NS}-checklist-body-list`);
    items.forEach((item, i) => {
      const row = document.createElement("div");
      const jurisSlug = (item.jurisdiction || "").replace(/\s+/g, "-");
      row.className = `${NS}-checklist-item`;
      row.dataset.id = item.id || String(i);
      row.innerHTML = `
        <div class="${NS}-checklist-num">${i + 1}</div>
        <div class="${NS}-checklist-body">
          <div class="${NS}-checklist-item-title-zh"></div>
          <div class="${NS}-checklist-item-title-en"></div>
          <div class="${NS}-checklist-item-desc"></div>
          <div class="${NS}-checklist-item-meta">
            <span class="${NS}-checklist-jurisdiction-badge ${NS}-jurisdiction-${jurisSlug}"></span>
            <span class="${NS}-checklist-time-cost"></span>
            <a class="${NS}-checklist-citation" target="_blank" rel="noopener"></a>
          </div>
        </div>
      `;
      row.querySelector(`.${NS}-checklist-item-title-zh`).textContent = item.titleZh || "";
      row.querySelector(`.${NS}-checklist-item-title-en`).textContent = item.titleEn || "";
      row.querySelector(`.${NS}-checklist-item-desc`).textContent = item.descZh || "";
      row.querySelector(`.${NS}-checklist-jurisdiction-badge`).textContent = item.jurisdiction || "";
      const tcEl = row.querySelector(`.${NS}-checklist-time-cost`);
      const parts = [];
      if (typeof item.timeMin === "number" && item.timeMin > 0) {
        if (item.timeMin >= 60) parts.push(copy().hour(Math.round(item.timeMin / 60)));
        else parts.push(copy().minute(item.timeMin));
      }
      if (typeof item.costUsd === "number") {
        parts.push(item.costUsd === 0 ? copy().free : `$${item.costUsd}`);
      }
      tcEl.textContent = parts.join(" · ");
      const cite = row.querySelector(`.${NS}-checklist-citation`);
      cite.textContent = copy().citation;
      if (item.citationUrl) cite.href = item.citationUrl;
      else cite.style.display = "none";
      list.appendChild(row);
    });

    document.body.appendChild(el);
    state.checklist = el;
    requestAnimationFrame(() => el.classList.add(`${NS}-checklist--visible`));

    // Staggered reveal of items
    const stagger = typeof staggerMs === "number" ? staggerMs : 250;
    Array.from(list.children).forEach((row, i) => {
      setTimeout(() => {
        row.classList.add(`${NS}-checklist-item--visible`);
      }, 200 + i * stagger);
    });
  }

  function setChecklistItemState(itemId, stateName) {
    if (!state.checklist) return;
    const row = state.checklist.querySelector(
      `.${NS}-checklist-item[data-id="${itemId}"]`
    );
    if (!row) return;
    row.classList.remove(
      `${NS}-checklist-item--active`,
      `${NS}-checklist-item--done`
    );
    if (stateName) row.classList.add(`${NS}-checklist-item--${stateName}`);
  }

  function hideChecklist() {
    if (!state.checklist) return;
    const el = state.checklist;
    el.classList.remove(`${NS}-checklist--visible`);
    setTimeout(() => el.remove(), 350);
    state.checklist = null;
  }

  window.shuxiang = {
    _installed: true,
    setLanguage,
    showOverlay,
    markListening,
    hideOverlay,
    showSidebar,
    updateSidebarField,
    hideSidebar,
    showToast,
    showOpeningPrompt,
    updateLiveTranscript,
    stopSpeech,
    typeOpeningTranscript,
    hideOpeningPrompt,
    typeTranscript,
    showClosing,
    installMicButton,
    setMicState,
    hideMicButton,
    showChecklist,
    setChecklistItemState,
    hideChecklist,
    TOKENS,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restoreLiveTranscript, { once: true });
  } else {
    restoreLiveTranscript();
  }
})();
