/**
 * chat.js
 * Dietary AI chatbot — connects to /api/chat endpoint.
 */

// ── Auth guard handled by async script in chatbot.html ────────────────────────

const messagesEl  = document.getElementById("chatMessages");
const inputEl     = document.getElementById("chatInput");
const sendBtnEl   = document.getElementById("sendBtn");
const typingEl    = document.getElementById("typingIndicator");

// ── Load existing history ─────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const res = await Chat.history();
    const history = res.history || [];
    history.forEach((msg) => appendBubble(msg.role, msg.content, false));
    scrollToBottom();
  } catch (err) {
    console.warn("Could not load chat history:", err);
  }
}

// ── Send message ──────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  // Hide suggestion chips after first message
  const prompts = document.getElementById("suggestedPrompts");
  if (prompts) prompts.style.display = "none";

  // Show user message
  appendBubble("user", text);
  inputEl.value = "";
  autoResize(inputEl);

  // Disable input & show typing
  setLoading(true);

  try {
    const res = await Chat.send(text);
    appendBubble("assistant", res.reply);
  } catch (err) {
    appendBubble("assistant", `⚠️ Error: ${err.message}`);
  } finally {
    setLoading(false);
  }
}

function sendPrompt(text) {
  inputEl.value = text;
  sendMessage();
}

// ── Render bubble ─────────────────────────────────────────────────────────────
function appendBubble(role, content, animate = true) {
  const isUser = role === "user";
  const wrap   = document.createElement("div");
  wrap.className = `flex gap-3 items-end ${isUser ? "justify-end" : ""} ${animate ? "anim-up" : ""}`;

  const avatar = isUser ? "" : `
    <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0"
         style="background:linear-gradient(135deg,#6366f1,#10b981);">🤖</div>
  `;

  // Convert markdown-ish formatting to HTML
  const html = formatMessage(content);

  wrap.innerHTML = `
    ${avatar}
    <div class="${isUser ? "bubble-user" : "bubble-ai"}">${html}</div>
  `;

  messagesEl.insertBefore(wrap, typingEl);
  scrollToBottom();
}

function formatMessage(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/^-\s(.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>")
    .replace(/\n{2,}/g, "<br><br>")
    .replace(/\n/g, "<br>");
}

// ── Loading state ─────────────────────────────────────────────────────────────
function setLoading(on) {
  sendBtnEl.disabled = on;
  inputEl.disabled   = on;
  typingEl.classList.toggle("hidden", !on);
  if (on) scrollToBottom();
}

// ── Clear history ─────────────────────────────────────────────────────────────
async function clearHistory() {
  if (!confirm("Clear all chat history?")) return;
  await Chat.clear();
  // Remove all bubbles except the first welcome one
  const bubbles = messagesEl.querySelectorAll("div.flex");
  bubbles.forEach((b, i) => { if (i > 0) b.remove(); });
  document.getElementById("suggestedPrompts").style.display = "";
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

function handleKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadHistory();