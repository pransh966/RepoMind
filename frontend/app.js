// RepoMind frontend -- vanilla JS, no build step, no framework.
// Talks to the FastAPI backend over plain fetch(). Auth token + selected
// repo id are kept in localStorage so a refresh doesn't log you out.

const API_BASE = "http://127.0.0.1:8000";

const state = {
  token: localStorage.getItem("repomind_token") || null,
  user: null,
  repos: [],
  activeRepoId: localStorage.getItem("repomind_active_repo")
    ? Number(localStorage.getItem("repomind_active_repo"))
    : null,
};

// ---------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------
const authScreen = document.getElementById("auth-screen");
const appEl = document.getElementById("app");
const connectModal = document.getElementById("connect-modal");

const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const loginError = document.getElementById("login-error");
const registerError = document.getElementById("register-error");

const repoListEl = document.getElementById("repo-list");
const historyListEl = document.getElementById("history-list");
const messagesEl = document.getElementById("messages");
const emptyStateEl = document.getElementById("empty-state");
const currentRepoNameEl = document.getElementById("current-repo-name");
const currentRepoMetaEl = document.getElementById("current-repo-meta");

const askForm = document.getElementById("ask-form");
const questionInput = document.getElementById("question-input");
const askBtn = document.getElementById("ask-btn");

const userEmailEl = document.getElementById("user-email");

// ---------------------------------------------------------------------
// API helper -- attaches the bearer token, throws with the server's own
// error message so callers can show it directly.
// ---------------------------------------------------------------------
async function api(path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  let data = null;
  try { data = await res.json(); } catch (_) { /* no body */ }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `Request failed (${res.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

// ---------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------
function showAuthTab(tab) {
  document.querySelectorAll(".auth-tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  loginForm.classList.toggle("hidden", tab !== "login");
  registerForm.classList.toggle("hidden", tab !== "register");
}
document.querySelectorAll(".auth-tab").forEach(btn => {
  btn.addEventListener("click", () => showAuthTab(btn.dataset.tab));
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  try {
    const data = await api("/auth/login", { method: "POST", json: { email, password } });
    onAuthed(data);
  } catch (err) {
    loginError.textContent = err.message;
  }
});

registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  registerError.textContent = "";
  const email = document.getElementById("register-email").value.trim();
  const password = document.getElementById("register-password").value;
  try {
    const data = await api("/auth/register", { method: "POST", json: { email, password } });
    onAuthed(data);
  } catch (err) {
    registerError.textContent = err.message;
  }
});

function onAuthed(data) {
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem("repomind_token", data.token);
  showApp();
}

document.getElementById("logout-btn").addEventListener("click", () => {
  state.token = null;
  state.user = null;
  state.repos = [];
  state.activeRepoId = null;
  localStorage.removeItem("repomind_token");
  localStorage.removeItem("repomind_active_repo");
  authScreen.classList.remove("hidden");
  appEl.classList.add("hidden");
});

async function tryResumeSession() {
  if (!state.token) return;
  try {
    state.user = await api("/auth/me");
    showApp();
  } catch (_) {
    state.token = null;
    localStorage.removeItem("repomind_token");
  }
}

async function showApp() {
  authScreen.classList.add("hidden");
  appEl.classList.remove("hidden");
  userEmailEl.textContent = state.user.email;
  await loadRepos();
  if (state.activeRepoId && state.repos.some(r => r.id === state.activeRepoId)) {
    await selectRepo(state.activeRepoId);
  }
}

// ---------------------------------------------------------------------
// Repos
// ---------------------------------------------------------------------
async function loadRepos() {
  state.repos = await api("/repos");
  renderRepoList();
}

function renderRepoList() {
  repoListEl.innerHTML = "";
  if (state.repos.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sidebar-empty";
    empty.textContent = "No repos yet.";
    repoListEl.appendChild(empty);
    return;
  }
  for (const repo of state.repos) {
    const item = document.createElement("div");
    item.className = "repo-item" + (repo.id === state.activeRepoId ? " active" : "");
    item.innerHTML = `
      <span class="repo-item-name">${escapeHtml(repo.name)}</span>
      <span class="repo-item-meta">${repo.chunks_count} chunks</span>
    `;
    item.addEventListener("click", () => selectRepo(repo.id));
    repoListEl.appendChild(item);
  }
}

async function selectRepo(repoId) {
  state.activeRepoId = repoId;
  localStorage.setItem("repomind_active_repo", String(repoId));
  renderRepoList();

  const repo = state.repos.find(r => r.id === repoId);
  currentRepoNameEl.textContent = repo ? repo.name : "Unknown repo";
  currentRepoMetaEl.textContent = repo ? `${repo.chunks_count} chunks · ${repo.source}` : "";

  questionInput.disabled = false;
  askBtn.disabled = false;

  messagesEl.innerHTML = "";
  await loadHistory(repoId);
}

// ---------------------------------------------------------------------
// History (shown both as the initial chat transcript for a repo, and as
// the clickable recent-questions list in the sidebar)
// ---------------------------------------------------------------------
async function loadHistory(repoId) {
  const items = await api(`/history?repo_id=${repoId}`);
  const ordered = [...items].reverse(); // oldest first for the chat transcript
  messagesEl.innerHTML = "";
  if (ordered.length === 0) {
    messagesEl.appendChild(makeEmptyState());
  } else {
    for (const item of ordered) {
      appendMessage("user", item.question, null, item.id);
      appendMessage("assistant", item.answer, item.citations);
    }
    scrollToBottom();
  }
  renderHistorySidebar(items.slice(0, 20));
}

function renderHistorySidebar(items) {
  historyListEl.innerHTML = "";
  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sidebar-empty";
    empty.textContent = "No questions yet.";
    historyListEl.appendChild(empty);
    return;
  }
  for (const item of items) {
    const el = document.createElement("div");
    el.className = "history-item";
    el.textContent = item.question;
    el.title = item.question;
    el.addEventListener("click", () => {
      const target = [...messagesEl.querySelectorAll(".message.user")]
        .find(m => m.dataset.historyId === String(item.id));
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    historyListEl.appendChild(el);
  }
}

function makeEmptyState() {
  const div = document.createElement("div");
  div.className = "empty-state";
  div.innerHTML = `<p class="empty-title">Ask your first question</p>
    <p class="empty-body">Try something like "How does authentication work here?"</p>`;
  return div;
}

// ---------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------
function renderMarkdown(text) {
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
    // CDN scripts failed to load (e.g. no internet) -- fall back to plain text
    // instead of showing a blank bubble.
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
  const raw = marked.parse(text, { breaks: true });
  return DOMPurify.sanitize(raw);
}

function appendMessage(role, text, citations, historyId) {
  document.getElementById("empty-state")?.remove();
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;
  if (historyId !== undefined && historyId !== null) wrap.dataset.historyId = String(historyId);

  const roleLabel = document.createElement("div");
  roleLabel.className = "message-role";
  roleLabel.textContent = role === "user" ? "You" : "RepoMind";
  wrap.appendChild(roleLabel);

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  if (role === "assistant") {
    bubble.classList.add("markdown-body");
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  wrap.appendChild(bubble);

  if (citations && citations.length > 0) {
    const cites = document.createElement("div");
    cites.className = "citations";
    for (const c of citations) {
      const chip = document.createElement("div");
      chip.className = "citation";
      chip.innerHTML = `
        <div class="citation-head">
          <span>${escapeHtml(c.file)}:${c.start_line}-${c.end_line}</span>
          <span class="citation-score">score ${c.score}</span>
        </div>
        <pre class="citation-snippet">${escapeHtml(c.snippet)}</pre>
      `;
      cites.appendChild(chip);
    }
    wrap.appendChild(cites);
  }

  messagesEl.appendChild(wrap);
  return wrap;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

askForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !state.activeRepoId) return;

  questionInput.value = "";
  questionInput.style.height = "auto";
  askBtn.disabled = true;

  appendMessage("user", question);
  const thinkingBubble = appendMessage("assistant", "Thinking...");
  scrollToBottom();

  try {
    const data = await api("/query", {
      method: "POST",
      json: { repo_id: state.activeRepoId, question },
    });
    thinkingBubble.remove();
    appendMessage("assistant", data.answer, data.citations);
    scrollToBottom();
    await loadHistory(state.activeRepoId); // refresh sidebar + attach history ids
  } catch (err) {
    const bubbleEl = thinkingBubble.querySelector(".message-bubble");
    bubbleEl.classList.remove("markdown-body");
    bubbleEl.textContent = `Error: ${err.message}`;
  } finally {
    askBtn.disabled = false;
  }
});

questionInput.addEventListener("input", () => {
  questionInput.style.height = "auto";
  questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + "px";
});

questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    askForm.requestSubmit();
  }
});

// ---------------------------------------------------------------------
// Connect-repo modal (git URL / zip upload)
// ---------------------------------------------------------------------
const connectRepoBtn = document.getElementById("connect-repo-btn");
const closeModalBtn = document.getElementById("close-modal-btn");
const gitForm = document.getElementById("git-form");
const uploadForm = document.getElementById("upload-form");
const gitError = document.getElementById("git-error");
const uploadError = document.getElementById("upload-error");

connectRepoBtn.addEventListener("click", () => connectModal.classList.remove("hidden"));
closeModalBtn.addEventListener("click", () => connectModal.classList.add("hidden"));
connectModal.addEventListener("click", (e) => {
  if (e.target === connectModal) connectModal.classList.add("hidden");
});

document.querySelectorAll(".modal-tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".modal-tab").forEach(b => b.classList.toggle("active", b === btn));
    const tab = btn.dataset.modalTab;
    gitForm.classList.toggle("hidden", tab !== "git");
    uploadForm.classList.toggle("hidden", tab !== "upload");
  });
});

gitForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  gitError.textContent = "";
  const submitBtn = document.getElementById("git-submit-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Cloning + indexing...";

  const git_url = document.getElementById("git-url-input").value.trim();
  const name = document.getElementById("git-name-input").value.trim() || null;

  try {
    const repo = await api("/repos/git", { method: "POST", json: { git_url, name } });
    await loadRepos();
    await selectRepo(repo.id);
    connectModal.classList.add("hidden");
    gitForm.reset();
  } catch (err) {
    gitError.textContent = err.message;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Clone & index";
  }
});

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  uploadError.textContent = "";
  const submitBtn = document.getElementById("upload-submit-btn");
  const file = document.getElementById("upload-file-input").files[0];
  const name = document.getElementById("upload-name-input").value.trim();
  if (!file) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Uploading + indexing...";

  const formData = new FormData();
  formData.append("file", file);
  if (name) formData.append("name", name);

  try {
    const headers = {};
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
    const res = await fetch(`${API_BASE}/repos/upload`, { method: "POST", headers, body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    await loadRepos();
    await selectRepo(data.id);
    connectModal.classList.add("hidden");
    uploadForm.reset();
  } catch (err) {
    uploadError.textContent = err.message;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Upload & index";
  }
});

// ---------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------
tryResumeSession();
