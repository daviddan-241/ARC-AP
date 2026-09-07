/* ArenaOS SPA — vanilla ES modules, no build step. Every control calls a real API route. */
const $ = (sel) => document.querySelector(sel);

/* ---------------- state ---------------- */
const state = {
  conversationId: localStorage.getItem("conversationId") || null,
  thinking: false,
  listening: false,
  recognition: null,
};

/* ---------------- api ---------------- */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...opts,
  });
  if (res.status === 401) { showLogin(); throw new Error("auth required"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  const ctype = res.headers.get("content-type") || "";
  return ctype.includes("json") ? res.json() : res;
}

/* ---------------- auth ---------------- */
function showLogin() {
  $("#login-screen").classList.remove("hidden-fade");
  $("#login-screen").style.display = "flex";
}
async function tryLogin() {
  const btn = $("#login-btn");
  btn.disabled = true; $("#login-error").textContent = "";
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password: $("#login-password").value }),
    });
    $("#login-screen").style.display = "none";
    await boot();
  } catch (err) {
    $("#login-error").textContent = err.message;
  } finally { btn.disabled = false; }
}

/* ---------------- chat ---------------- */
async function ensureConversation() {
  if (state.conversationId) return state.conversationId;
  const conv = await api("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title: "New chat" }),
  });
  state.conversationId = conv.id;
  localStorage.setItem("conversationId", conv.id);
  return conv.id;
}

async function loadConversation() {
  if (!state.conversationId) return;
  const messages = await api(`/api/conversations/${state.conversationId}/messages`);
  const stream = $("#chat-stream");
  stream.innerHTML = "";
  for (const m of messages) appendMessage(m.role, m.content, m.model);
  if (messages.length) $("#greeting").style.display = "none";
}

function appendMessage(role, content, model) {
  const stream = $("#chat-stream");
  $("#greeting").style.display = "none";
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "assistant") {
    const tag = document.createElement("div");
    tag.className = "model-tag";
    tag.textContent = model || "arena.ai";
    div.appendChild(tag);
    const body = document.createElement("div");
    body.textContent = content;
    div.appendChild(body);
  } else {
    div.textContent = content;
  }
  stream.appendChild(div);
  stream.scrollTop = stream.scrollHeight;
  return div;
}

async function addThought(kind, text) {
  const body = $("#thoughts-body");
  const row = document.createElement("div");
  row.className = "step";
  row.innerHTML = `<span class="dot">●</span><span></span>`;
  row.querySelector("span:last-child").textContent = `${kind}: ${text}`;
  body.appendChild(row);
  body.scrollTop = body.scrollHeight;
}

async function sendMessage() {
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || state.thinking) return;
  input.value = ""; autoGrow(input);
  appendMessage("user", text);
  state.thinking = true;
  $("#send-btn").disabled = true;
  const convId = await ensureConversation();
  const reply = appendMessage("assistant", "", null);
  const bodyDiv = document.createElement("div");
  reply.appendChild(bodyDiv);
  const cursor = document.createElement("span");
  cursor.className = "cursor-blink"; cursor.textContent = "●";
  reply.appendChild(cursor);
  let full = "", model = "";
  let errorShown = false;
  try {
    const res = await fetch(`/api/conversations/${convId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ content: text }),
    });
    if (!res.ok || !res.body) {
      const detail = await res.text();
      throw new Error(detail.slice(0, 200) || `HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        let event; try { event = JSON.parse(part.slice(6)); } catch { continue; }
        if (event.kind === "token") {
          full += event.delta;
          bodyDiv.textContent = full;
          $("#chat-stream").scrollTop = $("#chat-stream").scrollHeight;
          await addThought("stream", "arena.ai is responding…");
        } else if (event.kind === "done") {
          model = event.model || "arena.ai";
          reply.querySelector(".model-tag").textContent = model;
        } else if (event.kind === "error") {
          errorShown = true;
          const err = document.createElement("div");
          err.className = "error-inline";
          err.textContent = `⚠ ${event.error}`;
          reply.appendChild(err);
        }
      }
    }
  } catch (err) {
    const errMsg = document.createElement("div");
    errMsg.className = "error-inline";
    errMsg.textContent = `⚠ ${err.message}`;
    reply.appendChild(errMsg);
  } finally {
    cursor.remove();
    state.thinking = false;
    $("#send-btn").disabled = false;
    if (!full && !errorShown) bodyDiv.textContent = "(no response)";
    if (full) bodyDiv.textContent = full;
  }
}

/* ---------------- voice (real Web Speech API) ---------------- */
function toggleMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("#mic-btn").title = "Speech recognition unsupported in this browser"; return; }
  if (state.listening) { state.recognition?.stop(); return; }
  const rec = new SR();
  state.recognition = rec;
  rec.lang = "en-US"; rec.interimResults = true; rec.continuous = false;
  rec.onstart = () => { state.listening = true; $("#mic-btn").classList.add("listening"); };
  rec.onend = () => { state.listening = false; $("#mic-btn").classList.remove("listening"); };
  rec.onresult = (e) => {
    let text = "";
    for (const r of e.results) text += r[0].transcript;
    $("#chat-input").value = text;
    autoGrow($("#chat-input"));
  };
  rec.start();
}

/* ---------------- secondary views ---------------- */
const views = {
  tasks: async (el) => {
    el.innerHTML = "<p class='dim'>Loading tasks…</p>";
    const tasks = await api("/api/tasks");
    el.innerHTML = tasks.length ? "" : "<p class='dim'>No tasks yet — create one:</p>";
    const form = document.createElement("div");
    form.innerHTML = `
      <input id="task-goal" placeholder="Describe an autonomous task (uses the arena.ai session)"/>
      <div class="btn-row"><button class="mini-btn primary" id="task-create">Create & run</button></div>`;
    el.appendChild(form);
    form.querySelector("#task-create").onclick = async () => {
      const goal = form.querySelector("#task-goal").value.trim();
      if (!goal) return;
      await api("/api/tasks", { method: "POST", body: JSON.stringify({ goal }) });
      views.tasks(el);
    };
    for (const t of tasks.slice(0, 30)) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<div class="row"><span></span><span class="chip"></span></div>
        <div class="dim" style="margin-top:6px"></div>
        <div class="btn-row"></div>`;
      card.querySelector("span").textContent = t.goal;
      const chip = card.querySelector(".chip");
      chip.textContent = t.status;
      chip.className = "chip " + (t.status === "completed" ? "ok" : t.status === "failed" ? "bad" : "");
      card.querySelector(".dim").textContent = `${t.task_type} · ${t.created_at || ""} ${t.error || ""}`;
      const row = card.querySelector(".btn-row");
      const mk = (label, fn) => {
        const b = document.createElement("button");
        b.className = "mini-btn"; b.textContent = label;
        b.onclick = async () => { await fn(); views.tasks(el); };
        row.appendChild(b);
      };
      if (t.status === "blocked_on_permission") mk("Approve", () => api(`/api/tasks/${t.id}/approve`, { method: "POST" }));
      if (["failed", "waiting_retry"].includes(t.status)) mk("Resume", () => api(`/api/tasks/${t.id}/resume`, { method: "POST" }));
      if (!["completed", "cancelled", "failed"].includes(t.status)) mk("Cancel", () => api(`/api/tasks/${t.id}/cancel`, { method: "POST" }));
      el.appendChild(card);
    }
  },
  projects: async (el) => {
    el.innerHTML = "";
    const form = document.createElement("div");
    form.className = "card";
    form.innerHTML = `
      <input id="proj-name" placeholder="New project name"/>
      <div class="btn-row"><button class="mini-btn primary" id="proj-create">Create project + Linux workspace</button></div>`;
    el.appendChild(form);
    form.querySelector("#proj-create").onclick = async () => {
      const name = form.querySelector("#proj-name").value.trim();
      if (!name) return;
      await api("/api/projects", { method: "POST", body: JSON.stringify({ name }) });
      views.projects(el);
    };
    const projects = await api("/api/projects");
    for (const p of projects) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<div class="row"><span></span><span class="chip ok">workspace</span></div>
        <div class="dim"></div><div class="btn-row">
        <input placeholder="file path (e.g. main.py)"/><button class="mini-btn">Open</button></div>
        <pre class="code" style="display:none"></pre>`;
      card.querySelector("span").textContent = p.name;
      card.querySelector(".dim").textContent = p.workspace_path;
      const [pathInput, openBtn] = card.querySelectorAll(".btn-row input, .btn-row .mini-btn");
      openBtn.onclick = async () => {
        const pre = card.querySelector("pre");
        try {
          const f = await api(`/api/projects/${p.id}/files/content?path=${encodeURIComponent(pathInput.value)}`);
          pre.style.display = "block"; pre.textContent = f.content.slice(0, 4000);
        } catch (err) { pre.style.display = "block"; pre.textContent = err.message; }
      };
      el.appendChild(card);
    }
  },
  memory: async (el) => {
    el.innerHTML = "";
    const form = document.createElement("div");
    form.className = "card";
    form.innerHTML = `
      <select id="mem-layer"><option value="long">long</option><option value="project">project</option></select>
      <input id="mem-key" placeholder="key (optional)"/>
      <textarea id="mem-content" rows="2" placeholder="memory content"></textarea>
      <div class="btn-row"><button class="mini-btn primary" id="mem-add">Add</button>
      <button class="mini-btn" id="mem-export">Export all</button></div>`;
    el.appendChild(form);
    form.querySelector("#mem-add").onclick = async () => {
      const content = form.querySelector("#mem-content").value.trim();
      if (!content) return;
      await api("/api/memory", { method: "POST", body: JSON.stringify({
        layer: form.querySelector("#mem-layer").value, content,
        key: form.querySelector("#mem-key").value }) });
      views.memory(el);
    };
    form.querySelector("#mem-export").onclick = async () => {
      const data = await api("/api/memory/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "arenaos-memory.json"; a.click();
    };
    const memories = await api("/api/memory");
    for (const m of memories.slice(0, 50)) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<div class="row"><span class="chip"></span><button class="mini-btn">Delete</button></div>
        <div style="margin-top:8px"></div><div class="dim"></div>`;
      card.querySelector(".chip").textContent = m.layer;
      card.querySelector("div:nth-child(2)").textContent = m.content.slice(0, 300);
      card.querySelector(".dim").textContent = m.key || `id ${m.id} · ${m.created_at || ""}`;
      card.querySelector("button").onclick = async () => {
        await api(`/api/memory/${m.id}`, { method: "DELETE" }); views.memory(el);
      };
      el.appendChild(card);
    }
  },
  logs: async (el) => {
    el.innerHTML = "<p class='dim'>Loading audit trail…</p>";
    const [audit, calls] = await Promise.all([
      api("/api/logs/audit?limit=50"), api("/api/logs/tool-calls?limit=50"),
    ]);
    el.innerHTML = "<p class='dim'>Audit log</p>";
    for (const a of audit.slice(0, 25)) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<div class="row"><span></span><span class="dim"></span></div>`;
      card.querySelector("span").textContent = `${a.actor} · ${a.action} ${a.resource}`;
      card.querySelector(".dim").textContent = a.ts || "";
      el.appendChild(card);
    }
    const head = document.createElement("p");
    head.className = "dim"; head.style.marginTop = "14px";
    head.textContent = `Tool calls (${calls.length})`;
    el.appendChild(head);
    for (const c of calls.slice(0, 25)) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<div class="row"><span></span><span class="chip"></span></div>`;
      card.querySelector("span").textContent = c.tool;
      const chip = card.querySelector(".chip");
      chip.textContent = c.ok ? "ok" : "failed";
      chip.className = "chip " + (c.ok ? "ok" : "bad");
      el.appendChild(card);
    }
  },
  settings: async (el) => {
    el.innerHTML = "<p class='dim'>Loading status…</p>";
    const [status, vault] = await Promise.all([api("/api/status"), api("/api/vault")]);
    el.innerHTML = "";
    const statusCard = document.createElement("div");
    statusCard.className = "card";
    const arenaStatus = status.arena_session_status?.status || (status.arena_provider ? "ready" : "unavailable");
    statusCard.innerHTML = `<div class="row"><span>Arena.ai session</span><span class="chip ${arenaStatus === "ready" ? "ok" : "bad"}"></span></div>
      <div class="dim">transport: ${status.transport} · engine: ${status.engine_ready ? "ready" : "offline"}</div>
      <div class="dim">session: ${arenaStatus}${status.arena_session_status?.detail ? " — " + status.arena_session_status.detail : ""}</div>`;
    statusCard.querySelector(".chip").textContent = arenaStatus;
    el.appendChild(statusCard);
    const vaultCard = document.createElement("div");
    vaultCard.className = "card";
    vaultCard.innerHTML = `<p>Vault credentials (values encrypted, never shown back)</p>
      <input id="v-name" placeholder="name e.g. arena_web_email"/>
      <input id="v-kind" placeholder="kind e.g. password / token"/>
      <input id="v-value" type="password" placeholder="secret value"/>
      <div class="btn-row"><button class="mini-btn primary" id="v-add">Save credential</button></div>
      <div id="v-list" class="dim" style="margin-top:10px"></div>`;
    vaultCard.querySelector("#v-add").onclick = async () => {
      const [name, kind, value] = ["#v-name", "#v-kind", "#v-value"].map(s => vaultCard.querySelector(s).value.trim());
      if (!name || !value) return;
      await api("/api/vault", { method: "POST", body: JSON.stringify({ name, kind: kind || "token", value }) });
      views.settings(el);
    };
    vaultCard.querySelector("#v-list").textContent = vault.length
      ? vault.map(v => `${v.name} (${v.kind})`).join(" · ") : "no credentials stored";
    el.appendChild(vaultCard);
  },
};

async function openView(name) {
  $("#view-chat").classList.add("hidden-fade");
  $("#view-secondary").classList.remove("hidden-fade");
  $("#secondary-title").textContent = name[0].toUpperCase() + name.slice(1);
  const body = $("#secondary-body");
  try {
    await views[name](body);
  } catch (err) {
    body.innerHTML = `<div class="card"><div class="error-text">${err.message}</div></div>`;
  }
}

function closeView() {
  $("#view-secondary").classList.add("hidden-fade");
  $("#view-chat").classList.remove("hidden-fade");
}

/* ---------------- boot ---------------- */
function autoGrow(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
}

async function refreshStatus() {
  try {
    const health = await api("/healthz");
    const chip = $("#status-chip");
    chip.classList.toggle("ok", !health.degraded);
    chip.title = health.degraded ? "Arena transport degraded — check Settings" : "Arena session ready";
  } catch { $("#status-chip").classList.remove("ok"); }
}

async function loadRecentChats() {
  const list = $("#recent-chats");
  list.innerHTML = "";
  try {
    const convs = await api("/api/conversations");
    for (const c of convs.slice(0, 20)) {
      const a = document.createElement("a");
      a.className = "drawer-item";
      a.textContent = c.title === "New chat" ? c.id.slice(0, 8) : c.title;
      a.onclick = async () => {
        state.conversationId = c.id;
        localStorage.setItem("conversationId", c.id);
        await loadConversation(); toggleDrawer(false); closeView();
      };
      list.appendChild(a);
    }
  } catch {}
}

async function boot() {
  try { await api("/api/status"); } catch { return; }  // unauthenticated → login screen stays
  $("#login-screen").style.display = "none";
  await Promise.all([refreshStatus(), loadRecentChats(), loadConversation()]);
}

/* ---------------- wire up ---------------- */
$("#login-btn").onclick = tryLogin;
$("#login-password").addEventListener("keydown", (e) => { if (e.key === "Enter") tryLogin(); });
$("#menu-btn").onclick = () => toggleDrawer(true);
$("#drawer-close").onclick = () => toggleDrawer(false);
$("#drawer-backdrop").onclick = () => toggleDrawer(false);
function toggleDrawer(open) {
  $("#drawer").classList.toggle("open", open);
  $("#drawer-backdrop").classList.toggle("show", open);
}
$("#new-chat").onclick = async () => {
  const conv = await api("/api/conversations", { method: "POST", body: JSON.stringify({ title: "New chat" }) });
  state.conversationId = conv.id;
  localStorage.setItem("conversationId", conv.id);
  $("#chat-stream").innerHTML = "";
  $("#greeting").style.display = "block";
  toggleDrawer(false); closeView();
};
document.querySelectorAll(".library-grid [data-view]").forEach((a) => {
  a.onclick = async () => { toggleDrawer(false); await openView(a.dataset.view); };
});
$("#back-chat").onclick = closeView;
$("#send-btn").onclick = sendMessage;
$("#mic-btn").onclick = toggleMic;
$("#chat-input").addEventListener("input", (e) => autoGrow(e.target));
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
$("#attach-btn").title = "Attach files — upload in a project (Projects view)";
$("#thoughts-toggle").onclick = () => {
  const body = $("#thoughts-body");
  const open = body.style.display !== "none";
  body.style.display = open ? "none" : "block";
  $("#thoughts-toggle").textContent = (open ? "▸" : "▾") + " Thoughts";
};
boot();
