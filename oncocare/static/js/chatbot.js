/* ==========================================================================
   OncoCare AI — OncoBot chat panel
   Talks to /api/chat, which relays to the Gemini API server-side using the
   API key the user pastes into settings (stored in localStorage only).
   ========================================================================== */

(function () {
  const STORAGE_KEY = "oncocare_gemini_key";
  let chatHistory = []; // [{role: 'user'|'model', text}]

  const toggle = document.getElementById("chatToggle");
  const panel = document.getElementById("chatPanel");
  const closeBtn = document.getElementById("chatCloseBtn");
  const settingsBtn = document.getElementById("chatSettingsBtn");
  const settingsPanel = document.getElementById("chatSettings");
  const keyInput = document.getElementById("geminiKeyInput");
  const saveKeyBtn = document.getElementById("saveKeyBtn");
  const messagesEl = document.getElementById("chatMessages");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");

  function getKey() { return localStorage.getItem(STORAGE_KEY) || ""; }

  function appendMessage(text, cls) {
    const div = document.createElement("div");
    div.className = "chat-msg " + cls;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function showTyping() {
    const div = document.createElement("div");
    div.className = "chat-msg-typing";
    div.innerHTML = "<span></span><span></span><span></span>";
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  toggle.addEventListener("click", () => {
    panel.classList.toggle("hidden");
    if (!panel.classList.contains("hidden")) input.focus();
  });
  closeBtn.addEventListener("click", () => panel.classList.add("hidden"));

  settingsBtn.addEventListener("click", () => {
    settingsPanel.classList.toggle("hidden");
    keyInput.value = getKey();
  });

  saveKeyBtn.addEventListener("click", () => {
    const val = keyInput.value.trim();
    if (val) {
      localStorage.setItem(STORAGE_KEY, val);
      appendMessage("API key saved for this browser. Ask me anything about your readings!", "chat-msg-bot");
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    settingsPanel.classList.add("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    appendMessage(text, "chat-msg-user");
    chatHistory.push({ role: "user", text });
    input.value = "";

    const typingEl = showTyping();

    try {
      const patientId = document.body.dataset.patientId;
      const payload = {
        message: text,
        api_key: getKey(),
        history: chatHistory
      };
      if (patientId) payload.patient_id = patientId;

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      typingEl.remove();

      if (!res.ok) {
        appendMessage(data.error || "Something went wrong reaching Gemini.", "chat-msg-error");
        if (!getKey()) {
          settingsPanel.classList.remove("hidden");
        }
        return;
      }

      appendMessage(data.reply, "chat-msg-bot");
      chatHistory.push({ role: "model", text: data.reply });
    } catch (err) {
      typingEl.remove();
      appendMessage("Network error reaching the server.", "chat-msg-error");
    }
  });

  // Prompt for key on first open if none saved yet
  document.addEventListener("DOMContentLoaded", () => {
    if (!getKey()) {
      // leave settings closed but ready; user opens via gear icon
    }
  });
})();
