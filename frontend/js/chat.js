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

// ── Send message (with workout plan detection) ────────────────────────────────
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  // Hide suggestion chips after first message
  const prompts = document.getElementById("suggestedPrompts");
  if (prompts) prompts.style.display = "none";

  appendBubble("user", text);
  inputEl.value = "";
  autoResize(inputEl);
  setLoading(true);

  try {
    const res = await Chat.send(text);
    appendBubble("assistant", res.reply);
    _tryExtractWorkoutPlan(res.reply);
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

// ── Workout plan JSON detection ───────────────────────────────────────────────
// When Friday returns a bare JSON object with weekday keys (Mon–Sun),
// we treat it as a generated workout plan and fire the global event so
// plans.html (if open) can show the "Save to My Plan" banner.
const _WEEKDAY_KEYS = new Set(['Mon','Tue','Wed','Thu','Fri','Sat','Sun']);

function _tryExtractWorkoutPlan(replyText) {
  // Match a JSON object anywhere in the reply (Claude may return prose + JSON)
  const match = replyText.match(/\{[\s\S]*\}/);
  if (!match) return;
  try {
    const parsed = JSON.parse(match[0]);
    const keys   = Object.keys(parsed);
    // Must have at least one weekday key and array values
    if (keys.some(k => _WEEKDAY_KEYS.has(k)) && keys.every(k => Array.isArray(parsed[k]))) {
      window.dispatchEvent(new CustomEvent('friday_plan_suggestion', { detail: parsed }));
      _showPlanSaveBanner(parsed);
    }
  } catch (_) { /* not a plan JSON */ }
}

function _showPlanSaveBanner(plan) {
  const days = Object.keys(plan).filter(d => plan[d]?.length);
  // Inline banner inside the chat (for users not on plans.html)
  const wrap = document.createElement('div');
  wrap.className = 'flex gap-3 items-end anim-up';
  wrap.innerHTML = `
    <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0"
         style="background:linear-gradient(135deg,#6366f1,#10b981);">🤖</div>
    <div class="bubble-ai" style="border-color:rgba(99,102,241,.35);">
      💪 I've generated a workout plan for <strong>${days.join(', ')}</strong>.<br>
      <a href="/plans" style="color:#a5b4fc;font-weight:600;">→ Go to Plans page to save it</a>
    </div>`;
  messagesEl.insertBefore(wrap, typingEl);
  scrollToBottom();
}


// ── Init ──────────────────────────────────────────────────────────────────────
loadHistory().then(() => {
  // If the user arrived from the onboarding "AI generate my plan" path,
  // fire the pre-seeded prompt automatically so they land in a live plan conversation.
  const seedPrompt = sessionStorage.getItem("chatbot_initial_prompt");
  if (seedPrompt) {
    sessionStorage.removeItem("chatbot_initial_prompt");
    // Small delay so the page finishes rendering first
    setTimeout(() => {
      inputEl.value = seedPrompt;
      sendMessage();
    }, 600);
  }
});