/**
 * MemoryOS Content Script — runs on chatgpt.com
 *
 * Adds a ⚡ button next to ChatGPT's send button.
 * Click → reads current input → calls /memory/augment → replaces input with memory-enriched prompt.
 * After send → stores the user message in /memory/add (optional, toggle in popup).
 *
 * User identity: all API calls include session_id = settings.userId so data is isolated per user.
 */

const STORAGE_KEYS = {
  API_URL:     "memoryos_api_url",
  USER_ID:     "memoryos_user_id",
  AUTO_STORE:  "memoryos_auto_store",
  TOP_K:       "memoryos_top_k",
};

// ── Config (loaded from chrome.storage.sync on init) ─────────────────────────

let cfg = {
  apiUrl:    "http://localhost:8000",
  userId:    "default_user",
  autoStore: true,
  topK:      3,
};

function loadConfig(cb) {
  chrome.storage.sync.get(Object.values(STORAGE_KEYS), (items) => {
    cfg.apiUrl    = items[STORAGE_KEYS.API_URL]    || "http://localhost:8000";
    cfg.userId    = items[STORAGE_KEYS.USER_ID]    || "default_user";
    cfg.autoStore = items[STORAGE_KEYS.AUTO_STORE] !== false;  // default true
    cfg.topK      = items[STORAGE_KEYS.TOP_K]      || 3;
    if (cb) cb();
  });
}

// ── ChatGPT DOM helpers ───────────────────────────────────────────────────────

function getEditor() {
  return document.querySelector("#prompt-textarea");
}

function getEditorText() {
  const el = getEditor();
  if (!el) return "";
  return (el.innerText || el.textContent || "").trim();
}

function setEditorText(text) {
  const el = getEditor();
  if (!el) return false;
  el.focus();
  // Use execCommand so React's synthetic event system sees the change
  document.execCommand("selectAll", false, null);
  document.execCommand("insertText", false, text);
  return true;
}

function getSendButton() {
  return (
    document.querySelector('[data-testid="send-button"]') ||
    document.querySelector('button[aria-label="Send prompt"]')
  );
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function apiAugment(prompt) {
  const res = await fetch(`${cfg.apiUrl}/memory/augment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      top_k:        cfg.topK,
      force_inject: true,   // always inject when user clicks the button
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiStore(content) {
  const res = await fetch(`${cfg.apiUrl}/memory/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      source_type: "text",
      session_id:  cfg.userId,   // ← user-specific tag — filters stay isolated
      metadata:    { user_id: cfg.userId, source: "chatgpt_extension" },
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiSearch(query) {
  const res = await fetch(`${cfg.apiUrl}/memory/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      top_k:          5,
      session_filter: cfg.userId,   // ← only this user's memories
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Memory button ─────────────────────────────────────────────────────────────

function createMemoryButton() {
  const btn = document.createElement("button");
  btn.id        = "memoryos-inject-btn";
  btn.title     = "Inject your memory context (MemoryOS)";
  btn.innerHTML = "⚡";
  btn.className = "memoryos-btn";

  btn.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();

    const prompt = getEditorText();
    if (!prompt) {
      showToast("Type a message first", "warn");
      return;
    }

    setButtonState(btn, "loading");

    try {
      const data = await apiAugment(prompt);

      if (data.injected) {
        setEditorText(data.augmented_prompt);
        const count = data.context_added?.length || 0;
        showToast(`${count} memor${count === 1 ? "y" : "ies"} injected`, "success");
        setButtonState(btn, "success");
      } else {
        showToast("No relevant memory found", "info");
        setButtonState(btn, "empty");
      }
    } catch (err) {
      console.error("[MemoryOS]", err);
      showToast("MemoryOS server unreachable", "error");
      setButtonState(btn, "error");
    }

    setTimeout(() => setButtonState(btn, "idle"), 2500);
  });

  return btn;
}

function setButtonState(btn, state) {
  const states = {
    idle:    { text: "⚡", cls: "" },
    loading: { text: "⏳", cls: "memoryos-loading" },
    success: { text: "✅", cls: "memoryos-success" },
    empty:   { text: "💭", cls: "" },
    error:   { text: "❌", cls: "memoryos-error" },
  };
  const s = states[state] || states.idle;
  btn.innerHTML = s.text;
  btn.className = "memoryos-btn " + s.cls;
  btn.disabled  = state === "loading";
}

// ── Memory panel (hover/click to view stored memories) ────────────────────────

function createPanelButton() {
  const btn = document.createElement("button");
  btn.id        = "memoryos-panel-btn";
  btn.title     = "View your stored memories";
  btn.innerHTML = "🧠";
  btn.className = "memoryos-btn memoryos-panel-trigger";

  const panel = createPanel();
  document.body.appendChild(panel);

  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const isOpen = panel.classList.contains("memoryos-panel-open");
    if (isOpen) {
      panel.classList.remove("memoryos-panel-open");
      return;
    }
    panel.classList.add("memoryos-panel-open");
    await refreshPanel(panel);
  });

  // Close panel on outside click
  document.addEventListener("click", (e) => {
    if (!panel.contains(e.target) && e.target !== btn) {
      panel.classList.remove("memoryos-panel-open");
    }
  });

  return btn;
}

function createPanel() {
  const panel = document.createElement("div");
  panel.id        = "memoryos-panel";
  panel.className = "memoryos-panel";
  panel.innerHTML = `
    <div class="memoryos-panel-header">
      <span>🧠 Your Memories</span>
      <span class="memoryos-panel-user" id="memoryos-panel-user"></span>
    </div>
    <div class="memoryos-panel-search">
      <input id="memoryos-search-input" type="text" placeholder="Search your memories…" />
      <button id="memoryos-search-btn">→</button>
    </div>
    <div class="memoryos-panel-results" id="memoryos-panel-results">
      <div class="memoryos-panel-empty">Click to load your memories</div>
    </div>
    <div class="memoryos-panel-footer">
      <a href="${cfg.apiUrl}/docs" target="_blank">API docs</a>
      ·
      <a href="http://localhost:5173/graph" target="_blank">Graph UI</a>
    </div>
  `;

  // Search on Enter or button click
  panel.querySelector("#memoryos-search-btn").addEventListener("click", () => {
    doSearch(panel);
  });
  panel.querySelector("#memoryos-search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch(panel);
  });

  return panel;
}

async function refreshPanel(panel) {
  const resultsEl = panel.querySelector("#memoryos-panel-results");
  const userEl    = panel.querySelector("#memoryos-panel-user");
  userEl.textContent = cfg.userId;

  resultsEl.innerHTML = '<div class="memoryos-panel-loading">Loading…</div>';

  try {
    const res = await fetch(
      `${cfg.apiUrl}/memory/list?limit=20&session_filter=${encodeURIComponent(cfg.userId)}`
    );
    const data = await res.json();
    renderMemories(resultsEl, data.memories || []);
  } catch {
    resultsEl.innerHTML = '<div class="memoryos-panel-error">Cannot reach MemoryOS server</div>';
  }
}

async function doSearch(panel) {
  const input     = panel.querySelector("#memoryos-search-input");
  const resultsEl = panel.querySelector("#memoryos-panel-results");
  const query     = input.value.trim();
  if (!query) return;

  resultsEl.innerHTML = '<div class="memoryos-panel-loading">Searching…</div>';

  try {
    const data = await apiSearch(query);
    renderMemories(resultsEl, data.results || []);
  } catch {
    resultsEl.innerHTML = '<div class="memoryos-panel-error">Search failed</div>';
  }
}

function renderMemories(container, items) {
  if (!items.length) {
    container.innerHTML = '<div class="memoryos-panel-empty">No memories yet. Start chatting!</div>';
    return;
  }

  container.innerHTML = items.map((m) => {
    const age   = m.timestamp ? timeAgo(m.timestamp) : "";
    const score = m.score != null ? `${(m.score * 100).toFixed(0)}%` : "";
    return `
      <div class="memoryos-memory-row" data-id="${m.memory_id}">
        <div class="memoryos-memory-entity">${escHtml(m.entity)}</div>
        <div class="memoryos-memory-attr">${escHtml(m.attribute?.replace(/_/g, " ") || "")}</div>
        <div class="memoryos-memory-value">${escHtml(m.value || "")}</div>
        <div class="memoryos-memory-meta">
          ${m.source_type || ""}  ${age}  ${score}
        </div>
      </div>
    `;
  }).join("");
}

// ── Auto-store: captures user messages after they send ───────────────────────

function interceptSend() {
  // Watch for ChatGPT's form submit or Enter keypress
  document.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter" || e.shiftKey) return;
    if (!cfg.autoStore) return;
    const text = getEditorText();
    if (!text || text.length < 10) return;

    // Small delay so ChatGPT can process the send first
    setTimeout(async () => {
      try {
        await apiStore(text);
        console.debug("[MemoryOS] stored:", text.slice(0, 60));
      } catch (err) {
        console.debug("[MemoryOS] store failed:", err.message);
      }
    }, 300);
  }, true);
}

// ── Toast notification ────────────────────────────────────────────────────────

function showToast(msg, type = "info") {
  const existing = document.getElementById("memoryos-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id        = "memoryos-toast";
  toast.className = `memoryos-toast memoryos-toast-${type}`;
  toast.textContent = `⚡ ${msg}`;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("memoryos-toast-show"));
  setTimeout(() => {
    toast.classList.remove("memoryos-toast-show");
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function timeAgo(ts) {
  const secs = Math.floor(Date.now() / 1000) - ts;
  if (secs < 60)   return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400)return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Mount: inject buttons into ChatGPT UI ────────────────────────────────────

let mounted = false;

function mount() {
  const sendBtn = getSendButton();
  if (!sendBtn) return;
  if (document.getElementById("memoryos-inject-btn")) return;
  if (mounted) return;

  const wrapper = sendBtn.parentElement;

  const injectBtn = createMemoryButton();
  const panelBtn  = createPanelButton();

  wrapper.insertBefore(panelBtn,  sendBtn);
  wrapper.insertBefore(injectBtn, sendBtn);

  if (cfg.autoStore) interceptSend();

  mounted = false; // allow re-mount if ChatGPT re-renders
}

// ChatGPT is a SPA and re-renders the toolbar frequently
const observer = new MutationObserver(() => {
  if (!document.getElementById("memoryos-inject-btn")) {
    mounted = false;
    mount();
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

loadConfig(() => {
  observer.observe(document.body, { childList: true, subtree: true });
  mount();
});

// Re-load config when popup saves settings
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  loadConfig(() => {
    // Re-mount in case URL changed
    mounted = false;
    const old = document.getElementById("memoryos-inject-btn");
    if (old) old.remove();
    const old2 = document.getElementById("memoryos-panel-btn");
    if (old2) old2.remove();
    mount();
  });
});
