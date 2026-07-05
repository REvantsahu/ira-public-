/* ═══════════════════════════════════════════════════════════════
   IRA Web GUI — Main Application Logic
   ═══════════════════════════════════════════════════════════════ */

// ─── DOM References ──────────────────────────────────────────────
const chatFeed = document.getElementById("chatFeed");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("messageInput");
const statusLabel = document.getElementById("statusLabel");
const avatar = document.getElementById("avatar");
const voiceToggle = document.getElementById("voiceToggle");
const screenToggle = document.getElementById("screenToggle");
const listenButton = document.getElementById("listenButton");
const timeline = document.getElementById("timeline");
const toolLibrary = document.getElementById("toolLibrary");
const modelName = document.getElementById("modelName");
const toolCount = document.getElementById("toolCount");
const audioModel = document.getElementById("audioModel");
const nativeAudioNote = document.getElementById("nativeAudioNote");
const sendBtn = document.getElementById("sendBtn");
const stopBtn = document.getElementById("stopBtn");

// ─── Voice Overlay DOM ──────────────────────────────────────────
const voiceOverlay = document.getElementById("voiceOverlay");
const voiceCloseBtn = document.getElementById("voiceCloseBtn");
const voiceMicBtn = document.getElementById("voiceMicBtn");
const voiceStatusText = document.getElementById("voiceStatusText");
const voiceTranscript = document.getElementById("voiceTranscript");
const voiceToolList = document.getElementById("voiceToolList");
const voiceToolCount = document.getElementById("voiceToolCount");

// ─── State ──────────────────────────────────────────────────────
let state = "idle";
let voiceMode = false;
let includeScreen = false;
let recognition = null;
let busy = false;
let voiceBusy = false;
let voiceLoopActive = false;
let currentSessionId = null;
let eventSource = null;
let stoppedByUser = false;

// Random phase messages shown while IRA is processing
const phaseMessages = [
  "Consulting neural pathways...",
  "Warming up the circuits...",
  "Sipping digital chai...",
  "Thinking really hard...",
  "Running the algorithms...",
  "Connecting the dots...",
  "Waking up the GPUs...",
  "Brewing some logic...",
  "Sharpening the AI claws...",
  "Checking the matrix...",
  "Polishing the response...",
  "Crunching the numbers...",
  "Aligning the stars...",
  "Feeling lucky today...",
  "Channeling inner Jarvis...",
  "Consulting the knowledge base...",
  "Running diagnostic...",
  "Almost there, just a sec...",
  "Doing some digital yoga...",
  "Forming the perfect response...",
];

const stateLabels = {
  idle: "Ready",
  listening: "Listening",
  booting: "Starting",
  capturing: "Reading screen",
  thinking: "Thinking",
  tool: "Using tools",
  speaking: "Speaking",
  error: "Needs attention",
};

const voiceStateLabels = {
  idle: "Tap to speak",
  listening: "Listening...",
  processing: "Processing...",
  speaking: "Speaking...",
  error: "Something went wrong",
};

// ─── Main State ─────────────────────────────────────────────────
function setState(next, label) {
  state = next;
  avatar.className = `jarvis-avatar ${next}`;
  const statusLabelEl = document.getElementById('statusLabel');
  const statusText = label || stateLabels[next] || next;
  statusLabelEl.className = `status-indicator ${next === 'idle' ? 'status-active' : next === 'error' ? 'status-error' : 'status-warning'}`;
  statusLabelEl.textContent = statusText;
}

// ─── Voice Overlay State ────────────────────────────────────────
function setVoiceState(next) {
  voiceOverlay.className = `voice-overlay visible ${next}`;
  voiceStatusText.textContent = voiceStateLabels[next] || next;
}

// ─── CharStreamer — progressive reveal for HTML/text content ────
class CharStreamer {
  constructor(container, opts = {}) {
    this.container = container;
    this.charsPerTick = opts.charsPerTick || 3;
    this.interval = opts.interval || 18;
    this.startDelay = opts.startDelay || 120;
    this.useCursor = opts.cursor !== false;
    this.minTotal = opts.minTotal || 300;
    this.maxTotal = opts.maxTotal || 15000;
    this.onDone = opts.onDone || (() => {});
    this.text = "";
    this.index = 0;
    this.timer = null;
    this.started = false;
    this.cancelled = false;
    this.startTime = 0;
  }

  feed(text) {
    this.text = text || "";
    if (!this.text) { this.onDone(); return; }
    // Adaptive: don't exceed max total time
    const ticks = Math.ceil(this.text.length / this.charsPerTick);
    const idealTotal = Math.min(this.maxTotal, Math.max(this.minTotal, ticks * this.interval));
    if (ticks * this.interval > this.maxTotal) {
      this.interval = Math.max(2, Math.floor(this.maxTotal / ticks));
    }
    this.startTime = performance.now();
    this.timer = setTimeout(() => this._tick(), this.startDelay);
  }

  _tick() {
    if (this.cancelled) return;
    const end = Math.min(this.index + this.charsPerTick, this.text.length);
    const visible = this.text.slice(0, end);
    if (this.useCursor && end < this.text.length) {
      this.container.innerHTML = visible + '<span class="typing-cursor">▌</span>';
    } else {
      this.container.innerHTML = visible;
    }
    this.index = end;
    if (this.index < this.text.length) {
      this.timer = setTimeout(() => this._tick(), this.interval);
    } else {
      this._finish();
    }
  }

  _finish() {
    this.container.innerHTML = this.text;
    this.onDone();
  }

  skip() {
    if (this.cancelled) return;
    this.cancelled = true;
    if (this.timer) clearTimeout(this.timer);
    this.container.innerHTML = this.text;
    this.onDone();
  }

  cancel() {
    this.cancelled = true;
    if (this.timer) clearTimeout(this.timer);
  }
}

// Active streamer for the current IRA message (so user can click to skip)
let activeStreamer = null;

function skipActiveStream() {
  if (activeStreamer) {
    activeStreamer.skip();
    activeStreamer = null;
  }
}

// ─── Chat Messages ──────────────────────────────────────────────
function addMessage(kind, meta, body, extraActions, htmlBody, pygmentsCss) {
  // Don't add IRA messages to chat in voice mode — TTS handles it
  if (kind === 'ira' && voiceOverlay.classList.contains('visible')) return;

  const article = document.createElement("article");
  article.className = `jarvis-message ${kind}`;
  // Click IRA bubble to skip streaming
  if (kind === 'ira') {
    article.style.cursor = 'pointer';
    article.title = 'Click to skip animation';
    article.addEventListener('click', () => skipActiveStream(), { once: true });
  }

  const metaEl = document.createElement("div");
  metaEl.className = "message-meta";
  metaEl.textContent = meta;

  const bodyEl = document.createElement("div");
  bodyEl.className = "message-body";

  // Inject pygments CSS once (shared across messages)
  if (pygmentsCss && !document.getElementById("pygments-styles")) {
    const styleEl = document.createElement("style");
    styleEl.id = "pygments-styles";
    styleEl.textContent = pygmentsCss;
    document.head.appendChild(styleEl);
  }

  if (kind === 'ira' && htmlBody) {
    // Server-formatted HTML — stream the rendered HTML char by char
    // for premium feel. Click to skip.
    bodyEl.classList.add("md-rendered", "md-streaming");
    article.append(metaEl, bodyEl);
    addActionButtons(article, kind, body, extraActions);
    chatFeed.appendChild(article);
    chatFeed.scrollTop = chatFeed.scrollHeight;

    // Start char-by-char reveal of the HTML (cursor is part of streamer)
    activeStreamer = new CharStreamer(bodyEl, {
      charsPerTick: 4,
      interval: 14,
      startDelay: 100,
      minTotal: 350,
      maxTotal: 12000,
      cursor: true,
      onDone: () => {
        bodyEl.classList.remove("md-streaming");
        bodyEl.classList.add("md-done");
        activeStreamer = null;
        // Auto-scroll to bottom
        chatFeed.scrollTo({ top: chatFeed.scrollHeight, behavior: 'smooth' });
      },
    });
    activeStreamer.feed(htmlBody);
    return article;
  } else if (kind === 'ira') {
    revealTextLineByLine(bodyEl, body);
  } else {
    bodyEl.textContent = body;
  }

  article.append(metaEl, bodyEl);

  // Action buttons (copy, edit, retry) — copy uses plain text version
  addActionButtons(article, kind, body, extraActions);

  chatFeed.appendChild(article);
  chatFeed.scrollTop = chatFeed.scrollHeight;
  return article;
}

function revealTextLineByLine(container, fullText) {
  // Split into chunks by sentence boundaries
  const chunks = splitIntoChunks(fullText, 80);
  container.textContent = '';
  container.style.minHeight = '20px';

  chunks.forEach((chunk, i) => {
    const span = document.createElement("span");
    span.textContent = chunk;
    span.style.display = "inline-block";
    span.style.opacity = "0";
    span.style.transform = "translateY(8px)";
    span.style.transition = "opacity 0.35s ease, transform 0.35s ease";
    span.style.willChange = "opacity, transform";
    container.appendChild(span);

    // Reveal with staggered delay
    setTimeout(() => {
      span.style.opacity = "1";
      span.style.transform = "translateY(0)";
      container.parentElement.closest('.chat-feed')?.scrollTo({
        top: container.parentElement.closest('.chat-feed')?.scrollHeight,
        behavior: 'smooth'
      });
    }, 30 * i);
  });

  // Add typing cursor at the end
  const cursor = document.createElement("span");
  cursor.className = "typing-cursor";
  cursor.style.display = "inline-block";
  cursor.style.width = "2px";
  cursor.style.height = "1em";
  cursor.style.backgroundColor = "var(--jarvis-primary)";
  cursor.style.animation = "typing-blink 1s ease-in-out infinite";
  cursor.style.opacity = "0";
  cursor.style.transition = "opacity 0.3s ease";
  container.appendChild(cursor);

  // Reveal cursor after all lines
  setTimeout(() => { cursor.style.opacity = "1"; }, 30 * chunks.length);
}

function splitIntoChunks(text, maxLen) {
  // Split by sentences first, then combine short ones
  const sentences = text.match(/[^.!?]*[.!?]+/g) || [text];
  const chunks = [];
  let current = '';

  for (const s of sentences) {
    const trimmed = s.trim();
    if (!trimmed) continue;
    if ((current + ' ' + trimmed).length <= maxLen && current) {
      current += ' ' + trimmed;
    } else {
      if (current) chunks.push(current.trim());
      current = trimmed;
    }
  }
  if (current) chunks.push(current.trim());
  if (chunks.length === 0 && text.trim()) chunks.push(text.trim());
  return chunks;
}

function addToolMessage(name, argsText) {
  const article = document.createElement("article");
  article.className = "message tool";
  article.dataset.toolName = name;

  const metaEl = document.createElement("div");
  metaEl.className = "message-meta";
  metaEl.textContent = "Tool call";

  const details = document.createElement("details");
  details.className = "tool-output";
  details.open = true;

  const summary = document.createElement("summary");
  summary.textContent = name;

  const pre = document.createElement("pre");
  pre.textContent = argsText || "(no args)";

  details.append(summary, pre);
  article.append(metaEl, details);
  chatFeed.appendChild(article);
  chatFeed.scrollTop = chatFeed.scrollHeight;
  return pre;
}

function updateLatestToolResult(name, result) {
  const items = [...document.querySelectorAll(`.message.tool[data-tool-name="${CSS.escape(name)}"] pre`)];
  const pre = items[items.length - 1];
  if (pre) {
    pre.textContent = `${pre.textContent}\n\nOutput:\n${result}`;
  } else {
    addToolMessage(name, `Output:\n${result}`);
  }
}

function addTimeline(title, detail) {
  const item = document.createElement("div");
  item.className = "timeline-item";
  item.innerHTML = `<strong>${escapeHtml(title)}</strong>${escapeHtml(detail || "")}`;
  timeline.prepend(item);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// ─── Voice Tool List ────────────────────────────────────────────
function addVoiceToolCall(name, argsText) {
  const empty = voiceToolList.querySelector('.voice-tool-empty');
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = "voice-tool-item running";
  item.dataset.toolName = name;

  const nameRow = document.createElement("div");
  nameRow.className = "voice-tool-name";
  nameRow.innerHTML = `<span class="voice-tool-status"></span>${escapeHtml(name)}`;

  const argsRow = document.createElement("div");
  argsRow.className = "voice-tool-args";
  argsRow.textContent = argsText || "(no args)";

  const resultRow = document.createElement("div");
  resultRow.className = "voice-tool-result";
  resultRow.style.display = "none";

  item.append(nameRow, argsRow, resultRow);
  voiceToolList.appendChild(item);
  voiceToolList.scrollTop = voiceToolList.scrollHeight;
  updateVoiceToolCount();
  return item;
}

function updateVoiceToolResult(name, result) {
  const items = voiceToolList.querySelectorAll(`.voice-tool-item[data-tool-name="${CSS.escape(name)}"]`);
  const item = items[items.length - 1];
  if (!item) return;

  item.classList.remove("running");
  item.classList.add("done");
  const resultRow = item.querySelector('.voice-tool-result');
  if (resultRow) {
    resultRow.textContent = result;
    resultRow.style.display = "block";
  }
}

function setVoiceToolError(name) {
  const items = voiceToolList.querySelectorAll(`.voice-tool-item[data-tool-name="${CSS.escape(name)}"]`);
  const item = items[items.length - 1];
  if (!item) return;
  item.classList.remove("running");
  item.classList.add("error");
}

function updateVoiceToolCount() {
  const count = voiceToolList.querySelectorAll('.voice-tool-item').length;
  voiceToolCount.textContent = count;
}

function clearVoiceTools() {
  voiceToolList.innerHTML = '<div class="voice-tool-empty">Waiting for your command...</div>';
  voiceToolCount.textContent = '0';
}

// ─── Stop / Abort ───────────────────────────────────────────────
function showStopButton() {
  sendBtn.style.display = "none";
  stopBtn.style.display = "flex";
  stopBtn.disabled = false;
}

function hideStopButton() {
  stopBtn.style.display = "none";
  sendBtn.style.display = "flex";
  stopBtn.disabled = true;
}

function stopProcessing() {
  const sessionId = currentSessionId;
  if (sessionId) {
    fetch('/api/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: sessionId })
    }).catch(err => console.error("Error stopping agent on server:", err));
  }

  // Close EventSource
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  currentSessionId = null;
  busy = false;
  stoppedByUser = true;

  // Stop working animation
  hideWorkingAnimation();

  // Stop thought timer
  stopThoughtTimer();
  closeVoiceThought();

  // Hide stop button
  hideStopButton();

  // Re-enable input
  messageInput.disabled = false;
  listenButton.disabled = false;

  // Show "stopped" message
  setState("idle");
  const reply = "Ok master ji, main ruk gayi. Batao or kuch karna hai?";
  addMessage("ira", "IRA", reply, [
    { icon: "↻", label: "Retry", action: () => retryLastMessage() }
  ]);
}

function getLastUserText() {
  const msgs = chatFeed.querySelectorAll('.jarvis-message.user');
  const last = msgs[msgs.length - 1];
  if (!last) return '';
  const body = last.querySelector('.message-body');
  return body ? body.textContent.trim() : '';
}

function retryLastMessage() {
  const text = getLastUserText();
  if (!text) return;
  // Remove all messages after the last user message
  const msgs = chatFeed.querySelectorAll('.jarvis-message');
  const lastUser = chatFeed.querySelector('.jarvis-message.user:last-of-type');
  if (lastUser) {
    let after = false;
    msgs.forEach(m => {
      if (m === lastUser) { after = true; return; }
      if (after) m.remove();
    });
  }
  sendMessage(text);
}

// ─── Action Buttons: Copy & Edit ───────────────────────────────
function addActionButtons(article, kind, bodyText) {
  const actions = document.createElement("div");
  actions.className = "message-actions";
  actions.style.cssText = "display:flex;gap:6px;margin-top:8px;opacity:0;transition:opacity 0.2s ease;";

  article.addEventListener("mouseenter", () => actions.style.opacity = "1");
  article.addEventListener("mouseleave", () => actions.style.opacity = "0");

  // Copy button
  const copyBtn = document.createElement("button");
  copyBtn.className = "msg-action-btn";
  copyBtn.title = "Copy";
  copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(bodyText).then(() => {
      copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00ff00" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
      setTimeout(() => {
        copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
      }, 1500);
    }).catch(() => {});
  });

  actions.appendChild(copyBtn);

  // Edit button (only for user messages)
  if (kind === 'user') {
    const editBtn = document.createElement("button");
    editBtn.className = "msg-action-btn";
    editBtn.title = "Edit";
    editBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
    editBtn.addEventListener("click", () => {
      const newText = prompt("Edit your message:", bodyText);
      if (!newText || newText.trim() === bodyText) return;
      // Remove all messages after this one
      let found = false;
      chatFeed.querySelectorAll('.jarvis-message').forEach(m => {
        if (m === article) { found = true; return; }
        if (found) m.remove();
      });
      // Update this message text
      const body = article.querySelector('.message-body');
      if (body) body.textContent = newText.trim();
      // Send edited message
      sendMessage(newText.trim());
    });
    actions.appendChild(editBtn);
  }

  // Retry button (for IRA error/stopped messages)
  if (kind === 'ira' && arguments[3]) {
    const retryBtns = arguments[3];
    retryBtns.forEach(btn => {
      const el = document.createElement("button");
      el.className = "msg-action-btn";
      el.title = btn.label;
      el.textContent = btn.icon;
      el.style.fontSize = "14px";
      el.addEventListener("click", btn.action);
      actions.appendChild(el);
    });
  }

  article.appendChild(actions);
}

// ─── TTS System ─────────────────────────────────────────────────
let utteranceSpeak = null;
let audioAnimationFrame = null;
let voiceTtsCallback = null;

async function speak(text, onDone) {
  voiceTtsCallback = onDone || null;
  try {
    await speakWithSarvamBackend(text);
    return;
  } catch (error) {
    console.warn('Sarvam TTS via backend failed, falling back to browser TTS:', error);
  }
  speakWithBrowserFallback(text);
}

async function speakWithSarvamBackend(text) {
  window.speechSynthesis.cancel();
  if (audioAnimationFrame) {
    cancelAnimationFrame(audioAnimationFrame);
    audioAnimationFrame = null;
  }

  const response = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `Backend TTS error: ${response.status}`);
  }

  const blob = await response.blob();
  const arrayBuffer = await blob.arrayBuffer();

  setState("speaking");
  if (voiceOverlay.classList.contains('visible')) setVoiceState("speaking");

  await playAudioBuffer(arrayBuffer);

  setState("idle");
  if (voiceOverlay.classList.contains('visible')) {
    setVoiceState("idle");
  }

  if (voiceTtsCallback) {
    voiceTtsCallback();
    voiceTtsCallback = null;
  }
}

function speakWithBrowserFallback(text) {
  window.speechSynthesis.cancel();
  if (audioAnimationFrame) {
    cancelAnimationFrame(audioAnimationFrame);
    audioAnimationFrame = null;
  }

  utteranceSpeak = new SpeechSynthesisUtterance(text);
  utteranceSpeak.rate = 1.03;
  utteranceSpeak.pitch = 1.02;
  utteranceSpeak.onstart = () => {
    setState("speaking");
    if (voiceOverlay.classList.contains('visible')) setVoiceState("speaking");
  };
  utteranceSpeak.onend = () => {
    setState("idle");
    if (voiceOverlay.classList.contains('visible')) {
      setVoiceState("idle");
    }
    if (voiceTtsCallback) {
      voiceTtsCallback();
      voiceTtsCallback = null;
    }
  };
  utteranceSpeak.onerror = () => {
    if (voiceTtsCallback) {
      voiceTtsCallback();
      voiceTtsCallback = null;
    }
  };
  window.speechSynthesis.speak(utteranceSpeak);
}

function playAudioBuffer(arrayBuffer) {
  return new Promise((resolve, reject) => {
    try {
      const blob = new Blob([arrayBuffer], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().then(() => {
        audio.onended = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
        audio.onerror = (err) => {
          URL.revokeObjectURL(url);
          reject(err);
        };
      }).catch(err => {
        URL.revokeObjectURL(url);
        reject(err);
      });
    } catch (error) {
      reject(error);
    }
  });
}

function startWaveformAnimation() {
  const waveformBars = document.getElementById('waveformBars');
  waveformBars.innerHTML = '';
  for (let i = 0; i < 20; i++) {
    const bar = document.createElement('div');
    bar.className = 'waveform-bar';
    bar.style.height = `${Math.random() * 20 + 5}px`;
    waveformBars.appendChild(bar);
  }
  animateWaveform();
}

function stopWaveformAnimation() {
  if (audioAnimationFrame) {
    cancelAnimationFrame(audioAnimationFrame);
    audioAnimationFrame = null;
  }
  document.querySelectorAll('.waveform-bar').forEach(bar => bar.style.height = '5px');
}

function animateWaveform() {
  if (!utteranceSpeak || window.speechSynthesis.speaking === false) {
    stopWaveformAnimation();
    return;
  }
  document.querySelectorAll('.waveform-bar').forEach(bar => {
    bar.style.height = `${Math.random() * 45 + 5}px`;
  });
  audioAnimationFrame = requestAnimationFrame(animateWaveform);
}

// ─── Voice Overlay ──────────────────────────────────────────────
function showVoiceOverlay() {
  voiceOverlay.classList.remove('hidden');
  voiceOverlay.classList.add('visible');
  voiceOverlay.className = 'voice-overlay visible idle';
  clearVoiceTools();
  voiceLoopActive = true;
  voiceBusy = false;
  voiceTranscript.textContent = '';

  // Start listening immediately
  setTimeout(() => startVoiceListening(), 500);
}

function hideVoiceOverlay() {
  voiceLoopActive = false;
  voiceBusy = false;
  stopVoiceListening();
  window.speechSynthesis.cancel();
  voiceOverlay.classList.remove('visible');
  voiceOverlay.classList.add('hidden');
  voiceOverlay.className = 'voice-overlay hidden';

  // Clean up any active session
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (currentSessionId) {
    currentSessionId = null;
  }
  busy = false;
}

function startVoiceListening() {
  if (!recognition || voiceBusy || !voiceLoopActive) return;
  voiceBusy = true;
  setVoiceState("listening");
  voiceTranscript.textContent = '';
  try {
    recognition.start();
  } catch (e) {
    // Already started, ignore
  }
}

function stopVoiceListening() {
  voiceBusy = false;
  if (recognition) {
    try { recognition.stop(); } catch (e) {}
  }
}

// ─── Send Message (shared between chat & voice) ─────────────────
async function sendMessage(message) {
  if (busy || !message.trim()) return;
  busy = true;
  stoppedByUser = false;

  const isVoice = voiceOverlay.classList.contains('visible');

  if (!isVoice) {
    setState("booting");
    addMessage("user", "You", message);
    chatMessages.push({ role: "user", text: message });
    showWorkingAnimation();
    messageInput.value = "";
    resizeInput();
    messageInput.disabled = true;
    listenButton.disabled = true;
  } else {
    setVoiceState("processing");
    voiceTranscript.textContent = message;
  }

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, withScreenshot: includeScreen }),
    });
    if (stoppedByUser) return; // User hit stop while fetching
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Chat failed");
    streamEvents(data.sessionId, isVoice);
  } catch (error) {
    if (stoppedByUser) return;
    if (!isVoice) {
      showErrorWithRetry(error.message);
    } else {
      setVoiceState("error");
      voiceTranscript.textContent = error.message;
      setTimeout(() => {
        if (voiceLoopActive) {
          voiceBusy = false;
          startVoiceListening();
        }
      }, 2000);
    }
    busy = false;
  }
}

function showErrorWithRetry(msg) {
  hideWorkingAnimation();
  hideStopButton();
  setState("error");
  messageInput.disabled = false;
  listenButton.disabled = false;
  addMessage("ira", "Error", msg, [
    { icon: "↻", label: "Retry", action: () => retryLastMessage() }
  ]);
}

function streamEvents(sessionId, isVoice) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  currentSessionId = sessionId;
  eventSource = new EventSource(`/api/events?id=${encodeURIComponent(sessionId)}`);

  eventSource.onmessage = (event) => {
    const item = JSON.parse(event.data);
    const payload = item.payload || {};

    // Hide working animation on first real event
    if (item.type !== "ping" && item.type !== "status") {
      hideWorkingAnimation();
    }

    if (item.type === "status") {
      if (!isVoice) {
        setState(payload.state || "thinking", payload.label);
        // Sync working indicator phase label with actual event payload
        const phaseEl = document.getElementById("workingPhase");
        if (phaseEl) {
          if (payload.label) {
            // Stop generic cycling — use the real label
            if (workingPhaseInterval) {
              clearInterval(workingPhaseInterval);
              workingPhaseInterval = null;
            }
            phaseEl.textContent = payload.label;
          } else if (!workingPhaseInterval) {
            // No real label, restart generic cycling
            let idx = phaseMessages.indexOf(phaseEl.textContent);
            if (idx < 0) idx = 0;
            workingPhaseInterval = setInterval(() => {
              const el = document.getElementById("workingPhase");
              if (el) {
                idx = (idx + 1) % phaseMessages.length;
                el.textContent = phaseMessages[idx];
              }
            }, 1800);
          }
        }
      } else {
        if (payload.state !== 'idle' && payload.state !== 'speaking') {
          setVoiceState("processing");
        }
      }
    }

    if (item.type === "thought") {
      if (!isVoice) {
        setState("thinking", "Reasoning");
        addThoughtMessage(payload.text || "");
      }
      addVoiceThought(payload.text || "");
    }

    if (item.type === "tool_call") {
      // Stop thinking timer when first tool call arrives
      stopThoughtTimer();
      closeVoiceThought();

      if (!isVoice) {
        setState("tool", `Running ${payload.name}`);
        addToolMessage(payload.name, payload.args_text);
        addTimeline(payload.name, payload.args_text);
      }
      addVoiceToolCall(payload.name, payload.args_text);
    }

    if (item.type === "tool_result") {
      if (!isVoice) {
        updateLatestToolResult(payload.name, payload.result);
        addTimeline(`${payload.name} done`, String(payload.result).slice(0, 180));
      }
      updateVoiceToolResult(payload.name, payload.result);
    }

    if (item.type === "assistant") {
      if (!isVoice) {
        // Smoothly hide the working indicator before streaming the response
        hideWorkingAnimation();
        // Brief breath before the response starts — feels more natural
        setTimeout(() => {
          addMessage("ira", "IRA", payload.text || "", null, payload.html || null, payload.css || null);
          chatMessages.push({ role: "assistant", text: payload.text || "" });
        }, 120);
      }
      // In voice mode, ONLY speak via TTS — no chat text shown
      // Prefer TTS-clean text if server provided it (markdown stripped)
      const ttsText = payload.tts || payload.text || "";
      if (isVoice) {
        speak(ttsText, () => {
          // TTS done callback — restart voice loop
          if (voiceLoopActive) {
            voiceBusy = false;
            setTimeout(() => startVoiceListening(), 400);
          }
        });
      }
    }

    if (item.type === "error") {
      if (!isVoice) {
        showErrorWithRetry(payload.message || "Something went wrong");
      } else {
        setVoiceState("error");
        voiceTranscript.textContent = payload.message || "Error occurred";
        setTimeout(() => {
          if (voiceLoopActive) {
            voiceBusy = false;
            startVoiceListening();
          }
        }, 2000);
      }
    }

    if (item.type === "done") {
      eventSource.close();
      eventSource = null;
      currentSessionId = null;
      busy = false;
      if (stoppedByUser) return;
      hideStopButton();
      if (!isVoice) {
        if (state !== "speaking" && state !== "error") setState("idle");
      }
      // Enable input
      messageInput.disabled = false;
      listenButton.disabled = false;
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    eventSource = null;
    currentSessionId = null;
    busy = false;
    if (stoppedByUser) return;
    hideStopButton();
    if (!isVoice) {
      showErrorWithRetry("Connection lost. Please try again.");
    } else {
      if (voiceLoopActive) {
        voiceBusy = false;
        setTimeout(() => startVoiceListening(), 500);
      }
    }
  };
}

// ─── Working Animation ──────────────────────────────────────────
let workingEl = null;
let workingPhaseInterval = null;

function showWorkingAnimation() {
  hideWorkingAnimation();

  const article = document.createElement("article");
  article.className = "jarvis-message working";
  article.id = "workingIndicator";

  const metaEl = document.createElement("div");
  metaEl.className = "message-meta";
  metaEl.textContent = "IRA";

  const bodyEl = document.createElement("div");
  bodyEl.className = "message-body working-body";

  const bar = document.createElement("div");
  bar.className = "working-bar";

  const wave = document.createElement("div");
  wave.className = "working-wave";

  const phase = document.createElement("span");
  phase.className = "working-label";
  phase.id = "workingPhase";
  phase.textContent = "Working";

  const dots = document.createElement("span");
  dots.className = "working-dots";
  dots.innerHTML = "<span>.</span><span>.</span><span>.</span>";

  bodyEl.append(bar, wave, phase, dots);
  article.append(metaEl, bodyEl);
  chatFeed.appendChild(article);
  chatFeed.scrollTop = chatFeed.scrollHeight;
  workingEl = article;

  // Show stop button
  showStopButton();

  // Cycle phase messages
  let idx = 0;
  workingPhaseInterval = setInterval(() => {
    const el = document.getElementById("workingPhase");
    if (el) {
      idx = (idx + 1) % phaseMessages.length;
      el.textContent = phaseMessages[idx];
    }
  }, 1800);
}

function hideWorkingAnimation() {
  if (workingPhaseInterval) {
    clearInterval(workingPhaseInterval);
    workingPhaseInterval = null;
  }
  const el = document.getElementById("workingIndicator");
  if (el) {
    el.style.transition = "opacity 0.3s ease, transform 0.3s ease";
    el.style.opacity = "0";
    el.style.transform = "translateY(-6px)";
    setTimeout(() => el.remove(), 350);
  }
  workingEl = null;
  hideStopButton();
}

// ─── Think Block (IRA's Reasoning) ──────────────────────────────
let thoughtStartTime = null;
let thoughtTimerInterval = null;
let currentThoughtEl = null;
let currentVoiceThoughtEl = null;

function addThoughtMessage(text) {
  // Remove any existing "thinking..." placeholder
  const existing = document.querySelector('.message.thought');
  if (existing) existing.remove();

  const article = document.createElement("article");
  article.className = "jarvis-message thought";
  article.style.cursor = "pointer";

  const header = document.createElement("div");
  header.className = "message-meta";
  header.style.display = "flex";
  header.style.alignItems = "center";
  header.style.gap = "8px";
  header.style.cursor = "pointer";

  const icon = document.createElement("span");
  icon.textContent = "🤔";
  icon.style.fontSize = "14px";

  const label = document.createElement("span");
  thoughtStartTime = Date.now();
  label.id = "thoughtTimer";
  // Show first 80 chars of thinking text as label
  const previewText = text.length > 80 ? text.substring(0, 80) + "..." : text;
  label.textContent = previewText || "Thinking...";
  label.style.color = "var(--jarvis-warning)";

  const dots = document.createElement("span");
  dots.className = "thinking-dots";
  dots.innerHTML = "<span>.</span><span>.</span><span>.</span>";

  header.append(icon, label, dots);

  const body = document.createElement("div");
  body.className = "message-body thought-body";
  body.textContent = text;
  body.style.display = "none"; // Hidden by default, click to reveal

  article.append(header, body);

  // Click to toggle thought visibility
  article.addEventListener("click", () => {
    const isHidden = body.style.display === "none";
    body.style.display = isHidden ? "block" : "none";
    article.style.borderColor = isHidden ? "rgba(255,200,0,0.5)" : "var(--line)";
  });

  chatFeed.appendChild(article);
  chatFeed.scrollTop = chatFeed.scrollHeight;

  currentThoughtEl = article;

  // Start timer
  startThoughtTimer();

  return article;
}

function startThoughtTimer() {
  if (thoughtTimerInterval) clearInterval(thoughtTimerInterval);
  thoughtTimerInterval = setInterval(() => {
    if (!thoughtStartTime) return;
    const elapsed = Math.floor((Date.now() - thoughtStartTime) / 1000);
    const timer = document.getElementById("thoughtTimer");
    if (timer) timer.textContent = `Thinking (${elapsed}s)`;
  }, 200);
}

function stopThoughtTimer() {
  if (thoughtTimerInterval) {
    clearInterval(thoughtTimerInterval);
    thoughtTimerInterval = null;
  }
  const timer = document.getElementById("thoughtTimer");
  if (timer && thoughtStartTime) {
    const elapsed = Math.floor((Date.now() - thoughtStartTime) / 1000);
    timer.textContent = `Thought (${elapsed}s)`;
    timer.style.color = "var(--jarvis-ok)";
  }
  // Remove dots
  const dots = document.querySelector(".thinking-dots");
  if (dots) dots.remove();
}

function addVoiceThought(text) {
  // Add thought block to voice sidebar tool list
  const empty = voiceToolList.querySelector('.voice-tool-empty');
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = "voice-tool-item running";
  item.dataset.toolName = "__think__";
  item.style.cursor = "pointer";

  const nameRow = document.createElement("div");
  nameRow.className = "voice-tool-name";
  nameRow.innerHTML = `<span class="voice-tool-status"></span>🤔 THINK`;

  const argsRow = document.createElement("div");
  argsRow.className = "voice-tool-args";
  argsRow.textContent = text;
  argsRow.style.whiteSpace = "normal";
  argsRow.style.maxHeight = "80px";
  argsRow.style.overflow = "hidden";
  argsRow.style.display = "none"; // Hidden by default

  // Click to toggle
  item.addEventListener("click", () => {
    const isHidden = argsRow.style.display === "none";
    argsRow.style.display = isHidden ? "block" : "none";
  });

  item.append(nameRow, argsRow);
  voiceToolList.appendChild(item);
  voiceToolList.scrollTop = voiceToolList.scrollHeight;
  updateVoiceToolCount();

  currentVoiceThoughtEl = item;
}

function closeVoiceThought() {
  if (currentVoiceThoughtEl) {
    currentVoiceThoughtEl.classList.remove("running");
    currentVoiceThoughtEl.classList.add("done");
    currentVoiceThoughtEl = null;
  }
}

// ─── Speech Recognition ─────────────────────────────────────────
function setupSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    listenButton.disabled = true;
    listenButton.title = "Speech recognition not available";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.interimResults = false;
  recognition.continuous = false;

  recognition.onstart = () => {
    setState("listening");
    startWaveformAnimation();
  };

  recognition.onend = () => {
    stopWaveformAnimation();
    // Voice overlay mode: don't reset state here, handled by voice flow
    if (!voiceOverlay.classList.contains('visible')) {
      if (!busy && state === "listening") setState("idle");
    }
  };

  recognition.onerror = (event) => {
    stopWaveformAnimation();
    const isVoice = voiceOverlay.classList.contains('visible');

    if (isVoice) {
      // In voice mode, restart listening on non-fatal errors
      if (event.error !== 'aborted' && voiceLoopActive) {
        voiceBusy = false;
        setTimeout(() => startVoiceListening(), 500);
      }
    } else {
      if (!busy) setState("error", "Mic error");
    }
  };

  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    const isVoice = voiceOverlay.classList.contains('visible');

    if (isVoice) {
      voiceBusy = false; // Will be set true again in sendMessage via busy flag
    }
    sendMessage(text);
  };
}

// ─── Input ──────────────────────────────────────────────────────
function resizeInput() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 140)}px`;
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy) return;
  sendMessage(messageInput.value);
});

stopBtn.addEventListener("click", stopProcessing);

messageInput.addEventListener("input", resizeInput);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!busy) composer.requestSubmit();
  }
});

// Disable input while busy
function setInputEnabled(enabled) {
  messageInput.disabled = !enabled;
  listenButton.disabled = !enabled;
}

// ─── Buttons ────────────────────────────────────────────────────
voiceToggle.addEventListener("click", () => {
  if (voiceOverlay.classList.contains('visible')) {
    hideVoiceOverlay();
    voiceToggle.classList.remove("active");
    voiceToggle.textContent = "Mic";
  } else {
    showVoiceOverlay();
    voiceToggle.classList.add("active");
    voiceToggle.textContent = "Voice on";
  }
});

screenToggle.addEventListener("click", () => {
  includeScreen = !includeScreen;
  screenToggle.classList.toggle("active", includeScreen);
  screenToggle.textContent = includeScreen ? "Screen" : "No screen";
});

listenButton.addEventListener("click", () => {
  if (!recognition || busy || state !== "idle") return;
  // If voice overlay is visible, use its flow instead
  if (voiceOverlay.classList.contains('visible')) {
    if (!voiceBusy && voiceLoopActive) startVoiceListening();
    return;
  }
  recognition.start();
});

voiceCloseBtn.addEventListener("click", () => {
  hideVoiceOverlay();
  voiceToggle.classList.remove("active");
  voiceToggle.textContent = "Mic";
});

voiceMicBtn.addEventListener("click", () => {
  if (voiceOverlay.classList.contains('visible')) {
    if (!voiceBusy && voiceLoopActive && state === 'idle') {
      startVoiceListening();
    }
  }
});

// ─── Config ─────────────────────────────────────────────────────
async function loadConfig() {
  const response = await fetch("/api/config");
  const config = await response.json();
  modelName.textContent = config.model;
  toolCount.textContent = `${config.toolCount} available`;
  audioModel.textContent = config.liveAudioModel;
  nativeAudioNote.textContent = config.nativeAudio.note;
  toolLibrary.innerHTML = "";
  config.tools.forEach((name) => {
    const chip = document.createElement("span");
    chip.className = "tool-chip";
    chip.textContent = name;
    toolLibrary.appendChild(chip);
  });
}

function createFloatingHUD(text, positionV, positionH, offsetV, offsetH) {
  const hud = document.createElement("div");
  hud.className = `floating-hud pulse`;
  hud.textContent = text;
  if (positionV === "top") hud.style.top = `${offsetV}px`;
  else hud.style.bottom = `${offsetV}px`;
  if (positionH === "left") hud.style.left = `${offsetH}px`;
  else hud.style.right = `${offsetH}px`;
  document.body.appendChild(hud);
  setTimeout(() => hud.remove(), 10000);
}

// ─── Init ───────────────────────────────────────────────────────
screenToggle.textContent = "No screen";
setupSpeechRecognition();
loadConfig().catch(() => {});
setState("idle");

setTimeout(() => {
  createFloatingHUD("SUIT SYSTEMS", "top", "left", 20, 20);
  createFloatingHUD("THREAT RADAR", "top", "right", 20, 20);
  createFloatingHUD("STARK ANALYTICS", "bottom", "left", 20, 20);
  createFloatingHUD("COMMS & MISSION LOG", "bottom", "right", 20, 20);
}, 1000);

document.getElementById('refreshTools')?.addEventListener('click', () => {
  loadConfig().catch(() => {});
  const chip = document.createElement("span");
  chip.className = "tool-chip";
  chip.textContent = "REFRESHED";
  chip.style.animation = "pulse 0.5s";
  toolLibrary.appendChild(chip);
  setTimeout(() => chip.remove(), 1000);
});

// ─── Chat History & New Chat ──────────────────────────────────
const historyDrawer = document.getElementById("historyDrawer");
const historyBtn = document.getElementById("historyBtn");
const historyClose = document.getElementById("historyClose");
const historyList = document.getElementById("historyList");
const historySearch = document.getElementById("historySearch");
const newChatBtn = document.getElementById("newChatBtn");

let chatMessages = []; // Track messages for saving
let currentChatFile = null; // Currently loaded chat file

// Open history drawer
historyBtn.addEventListener("click", () => {
  historyDrawer.classList.add("open");
  loadChatHistory();
});

// Close history drawer
historyClose.addEventListener("click", () => {
  historyDrawer.classList.remove("open");
});

// Close on backdrop click
historyDrawer.addEventListener("click", (e) => {
  if (e.target === historyDrawer || e.target === historyDrawer.querySelector("::before")) {
    historyDrawer.classList.remove("open");
  }
});

// New chat
newChatBtn.addEventListener("click", () => {
  if (chatMessages.length > 0 && !confirm("Start new chat? Current chat will be saved.")) return;

  // Save current chat if there are messages
  if (chatMessages.length > 0) {
    saveCurrentChat();
  }

  // Clear everything
  chatFeed.innerHTML = "";
  chatMessages = [];
  currentChatFile = null;
  busy = false;
  stoppedByUser = false;
  setState("idle");

  // Clear timeline
  timeline.innerHTML = "";

  // Add welcome message
  addMessage("ira", "IRA", "Namaste bhai. Main ready hoon. Message type kar, ya voice mode on karke bol.");

  // Close drawer if open
  historyDrawer.classList.remove("open");
});

// Search chats
let searchTimeout = null;
historySearch.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  const q = historySearch.value.trim();
  searchTimeout = setTimeout(() => {
    if (q.length > 0) {
      searchChats(q);
    } else {
      loadChatHistory();
    }
  }, 300);
});

// Load chat history from API
async function loadChatHistory() {
  try {
    const resp = await fetch("/api/chats");
    const data = await resp.json();
    renderHistoryList(data.sessions || []);
  } catch (err) {
    historyList.innerHTML = '<div class="history-empty">Failed to load history</div>';
  }
}

// Search chats
async function searchChats(query) {
  try {
    const resp = await fetch(`/api/chats/search?q=${encodeURIComponent(query)}`);
    const data = await resp.json();
    renderSearchResults(data.results || [], query);
  } catch (err) {
    historyList.innerHTML = '<div class="history-empty">Search failed</div>';
  }
}

// Render history list grouped by date
function renderHistoryList(sessions) {
  if (!sessions.length) {
    historyList.innerHTML = '<div class="history-empty">No conversations yet</div>';
    return;
  }

  historyList.innerHTML = "";
  sessions.forEach(session => {
    const folder = document.createElement("div");
    folder.className = "history-folder open";

    const header = document.createElement("div");
    header.className = "history-folder-header";
    header.innerHTML = `<span class="history-folder-icon">\u25B6</span>${escapeHtml(session.display)}`;
    header.addEventListener("click", () => folder.classList.toggle("open"));

    const files = document.createElement("div");
    files.className = "history-folder-files";

    session.files.forEach(file => {
      const item = document.createElement("div");
      item.className = "history-item";
      if (file.filepath === currentChatFile) item.classList.add("active");

      const time = document.createElement("span");
      time.className = "history-item-time";
      time.textContent = file.time;

      const name = document.createElement("span");
      name.className = "history-item-name";
      name.textContent = file.name;

      item.append(time, name);
      item.addEventListener("click", () => loadChat(file.filepath));
      files.appendChild(item);
    });

    folder.append(header, files);
    historyList.appendChild(folder);
  });
}

// Render search results
function renderSearchResults(results, query) {
  if (!results.length) {
    historyList.innerHTML = '<div class="history-empty">No results found</div>';
    return;
  }

  historyList.innerHTML = "";
  const title = document.createElement("div");
  title.style.cssText = "padding: 8px 18px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.1em;";
  title.textContent = `${results.length} result${results.length !== 1 ? 's' : ''} for "${query}"`;
  historyList.appendChild(title);

  results.forEach(result => {
    const item = document.createElement("div");
    item.className = "history-item";
    item.style.flexDirection = "column";
    item.style.alignItems = "flex-start";
    item.style.padding = "10px 18px";

    const topRow = document.createElement("div");
    topRow.style.cssText = "display: flex; gap: 8px; width: 100%;";

    const time = document.createElement("span");
    time.className = "history-item-time";
    time.textContent = result.display;

    topRow.appendChild(time);

    const snippet = document.createElement("div");
    snippet.style.cssText = "font-size: 11px; color: var(--text-dim); margin-top: 4px; line-height: 1.4; word-break: break-word;";
    snippet.textContent = result.snippet;

    item.append(topRow, snippet);
    item.addEventListener("click", () => loadChat(result.filepath));
    historyList.appendChild(item);
  });
}

// Load a specific chat
async function loadChat(filepath) {
  try {
    const resp = await fetch(`/api/chats/load?path=${encodeURIComponent(filepath)}`);
    if (!resp.ok) throw new Error("Failed to load");
    const data = await resp.json();

    // Save current chat first if needed
    if (chatMessages.length > 0) {
      saveCurrentChat();
    }

    // Clear and populate
    chatFeed.innerHTML = "";
    chatMessages = [];
    currentChatFile = filepath;

    const messages = data.messages || [];
    messages.forEach(msg => {
      if (msg.role === "user") {
        addMessage("user", "You", msg.text);
        chatMessages.push({ role: "user", text: msg.text });
      } else if (msg.role === "assistant") {
        addMessage("ira", "IRA", msg.text);
        chatMessages.push({ role: "assistant", text: msg.text });
      }
    });

    // Close drawer
    historyDrawer.classList.remove("open");
  } catch (err) {
    console.error("Failed to load chat:", err);
  }
}

// Save current chat via API
async function saveCurrentChat() {
  if (chatMessages.length === 0) return;
  try {
    const firstUserMsg = chatMessages.find(m => m.role === "user");
    const firstPrompt = firstUserMsg ? firstUserMsg.text.slice(0, 60) : "chat";
    await fetch("/api/chats/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatMessages, first_prompt: firstPrompt }),
    });
  } catch (err) {
    console.error("Failed to save chat:", err);
  }
}
