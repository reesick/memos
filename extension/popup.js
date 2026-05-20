/**
 * MemoryOS Popup — settings + memory preview
 *
 * User identity design:
 *   Every API call tags data with session_id = userId.
 *   /memory/add  → session_id: userId   (writes under this user)
 *   /memory/list → session_filter: userId  (reads only this user)
 *   /memory/search → session_filter: userId
 *
 *   Different people → different userId → completely isolated data.
 *   Same person on multiple machines → same userId → shared memory.
 */

const KEYS = {
  API_URL:    "memoryos_api_url",
  USER_ID:    "memoryos_user_id",
  AUTO_STORE: "memoryos_auto_store",
  TOP_K:      "memoryos_top_k",
};

let apiUrl = "http://localhost:8000";
let userId = "default_user";

// ── Load saved settings ───────────────────────────────────────────────────────

function loadSettings() {
  chrome.storage.sync.get(Object.values(KEYS), (items) => {
    apiUrl = items[KEYS.API_URL] || "http://localhost:8000";
    userId = items[KEYS.USER_ID] || "default_user";

    document.getElementById("api-url").value    = apiUrl;
    document.getElementById("user-id").value    = userId;
    document.getElementById("top-k").value      = items[KEYS.TOP_K] || 3;
    document.getElementById("auto-store").checked = items[KEYS.AUTO_STORE] !== false;

    updateLinks();
    checkServer();
    loadMemories();
  });
}

// ── Save settings ─────────────────────────────────────────────────────────────

document.getElementById("btn-save").addEventListener("click", () => {
  const newUrl    = document.getElementById("api-url").value.trim().replace(/\/$/, "");
  const newUserId = document.getElementById("user-id").value.trim() || "default_user";
  const newTopK   = parseInt(document.getElementById("top-k").value) || 3;
  const newAuto   = document.getElementById("auto-store").checked;

  chrome.storage.sync.set({
    [KEYS.API_URL]:    newUrl,
    [KEYS.USER_ID]:    newUserId,
    [KEYS.AUTO_STORE]: newAuto,
    [KEYS.TOP_K]:      newTopK,
  }, () => {
    apiUrl = newUrl;
    userId = newUserId;
    updateLinks();
    checkServer();
    loadMemories();

    const fb = document.getElementById("save-feedback");
    fb.textContent = "✓ Saved";
    setTimeout(() => fb.textContent = "", 2000);
  });
});

// ── Server health check ───────────────────────────────────────────────────────

async function checkServer() {
  const dot  = document.getElementById("status-dot");
  const text = document.getElementById("status-text");

  dot.className  = "status-dot";
  text.textContent = "Checking…";

  try {
    const res  = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(4000) });
    const data = await res.json();

    if (data.status === "ok") {
      dot.className    = "status-dot ok";
      const ollama     = data.ollama ? "Ollama ✓" : "Ollama ✗ (Claude fallback)";
      text.textContent = `Connected · ${ollama}`;
    } else {
      dot.className    = "status-dot warn";
      text.textContent = "Server responded but status unknown";
    }
  } catch {
    dot.className    = "status-dot error";
    text.textContent = "Server unreachable — is run.py running?";
  }
}

document.getElementById("btn-refresh").addEventListener("click", () => {
  apiUrl = document.getElementById("api-url").value.trim().replace(/\/$/, "");
  checkServer();
  loadMemories();
});

// ── Load memory preview ───────────────────────────────────────────────────────

async function loadMemories() {
  const list = document.getElementById("memories-list");
  const stat = document.getElementById("stat-count");

  list.innerHTML = '<div class="placeholder">Loading…</div>';

  try {
    // Fetch memories for THIS user only — session_filter isolates by userId
    const res  = await fetch(
      `${apiUrl}/memory/list?limit=15&session_filter=${encodeURIComponent(userId)}`
    );
    const data = await res.json();
    const mems = data.memories || [];
    const total = data.total || 0;

    stat.textContent = `${total} fact${total !== 1 ? "s" : ""} for "${userId}"`;

    if (!mems.length) {
      list.innerHTML = '<div class="placeholder">No memories yet. Start chatting on ChatGPT!</div>';
      return;
    }

    list.innerHTML = mems.map((m) => `
      <div class="mem-row">
        <div class="mem-entity">${esc(m.entity)}</div>
        <div class="mem-attr">${esc(m.attribute?.replace(/_/g, " ") || "")}</div>
        <div class="mem-value">${esc(m.value || "")}</div>
      </div>
    `).join("");
  } catch {
    list.innerHTML = '<div class="placeholder" style="color:#e74c3c">Cannot reach server</div>';
    stat.textContent = "— facts";
  }
}

// ── Update footer links ───────────────────────────────────────────────────────

function updateLinks() {
  document.getElementById("link-graph").href = "http://localhost:5173/graph";
  document.getElementById("link-docs").href  = `${apiUrl}/docs`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadSettings();
