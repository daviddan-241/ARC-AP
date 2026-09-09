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
  if (messages.length) {
    $("#greeting").style.display = "none";
    $("#chips").style.display = "none";
  } else { $("#chips").style.display = "flex"; }
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

function addThoughtStep(label, detail) {
  const body = $("#thoughts-body");
  const row = document.createElement("div");
  row.className = "step running";
  row.innerHTML = `<span class="dot"></span><div><div class="label"></div><div class="detail"></div></div>`;
  row.querySelector(".label").textContent = label;
  row.querySelector(".detail").textContent = detail || "";
  body.appendChild(row);
  body.scrollTop = body.scrollHeight;
  $("#thoughts-panel").classList.remove("hidden-fade");
  return row;
}

function resolveThoughtStep(row, ok, detail) {
  if (!row) return;
  row.classList.remove("running");
  row.classList.add(ok ? "ok" : "failed");
  if (detail) row.querySelector(".detail").textContent = detail;
}

async function sendMessage() {
  const input = $("#chat-input");
  let text = input.value.trim();
  if (!text || state.thinking) return;
  if (pendingUploads.length) {
    text += "\n\n[attached files in workspace Uploads: " + pendingUploads.join(", ") + "]";
    pendingUploads.length = 0; renderAttachPreview();
  }
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
  let openStep = null;
  try {
    const res = await fetch(`/api/conversations/${convId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ content: text, mood: state_moods.current }),
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
        } else if (event.kind === "tool_call") {
          openStep = addThoughtStep(`Running ${event.tool}`, JSON.stringify(event.args || {}).slice(0, 160));
        } else if (event.kind === "tool_result") {
          resolveThoughtStep(openStep, event.ok, event.ok
            ? (event.output || "done").slice(0, 200)
            : `⚠ ${event.error || "failed"}`);
          openStep = null;
        } else if (event.kind === "learned") {
          addThoughtStep(`Remembered: ${event.key}`, event.content);
        } else if (event.kind === "done") {
          model = event.model || "arena.ai";
          reply.querySelector(".model-tag").textContent = model;
        } else if (event.kind === "error") {
          errorShown = true;
          resolveThoughtStep(openStep, false, event.error);
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
  files: async (el) => {
    el.innerHTML = "<p class='dim'>Loading your files…</p>";
    const pid = await uploadsProjectId();
    let files = [];
    try { files = await api(`/api/projects/${pid}/files?path=.`); } catch {}
    el.innerHTML = files.length ? "" : "<p class='dim'>No files yet — tap ＋ in the chat to upload.</p>";
    for (const f of files) {
      if (f.dir) continue;
      const row = document.createElement("div");
      row.className = "file-row";
      row.innerHTML = `<span>📄</span><span class="fname"></span><span class="fsize"></span>
        <a class="mini-btn">Download</a>`;
      row.querySelector(".fname").textContent = f.name;
      row.querySelector(".fsize").textContent = f.size > 1048576 ? (f.size/1048576).toFixed(1) + " MB" : (f.size/1024).toFixed(1) + " KB";
      const a = row.querySelector("a");
      a.href = `/api/projects/${pid}/files/download?path=${encodeURIComponent(f.name)}`;
      el.appendChild(row);
    }
  },
  tools: async (el) => {
    el.innerHTML = "<p class='dim'>Loading real tool registry…</p>";
    const tools = await api("/api/tools");
    el.innerHTML = "<p class='dim'>Every tool below is live — the same code the agent calls.</p>";
    for (const t of tools) {
      const card = document.createElement("div");
      card.className = "card tool-row";
      card.innerHTML = `<div class="row"><span></span><span class="chip"></span></div>
        <div class="dim"></div>
        <textarea class="args" placeholder='{"command": "whoami"}' hidden></textarea>
        <div class="btn-row" hidden><button class="mini-btn primary run">Run</button></div>`;
      card.querySelector("span").textContent = t.name;
      card.querySelector(".chip").textContent = t.name;
      card.querySelector(".dim").textContent = (t.description || "") + " " + JSON.stringify(t.args || {});
      card.onclick = () => {
        const ta = card.querySelector(".args"), row = card.querySelector(".btn-row");
        ta.hidden = !ta.hidden; row.hidden = !row.hidden;
      };
      card.querySelector(".run").onclick = async (e) => {
        e.stopPropagation();
        const out = card.querySelector(".run");
        out.textContent = "Running…"; out.disabled = true;
        try {
          const args = JSON.parse(card.querySelector(".args").value || "{}");
          const res = await api(`/api/tools/${t.name}/invoke`, { method: "POST", body: JSON.stringify({ args }) });
          const pre = document.createElement("pre");
          pre.className = "code";
          pre.textContent = (res.ok ? res.output : "⚠ " + (res.error || "failed")).slice(0, 3000);
          card.appendChild(pre);
        } catch (err) {
          const pre = document.createElement("pre");
          pre.className = "code"; pre.textContent = "⚠ " + err.message;
          card.appendChild(pre);
        }
        out.textContent = "Run"; out.disabled = false;
      };
      el.appendChild(card);
    }
  },
  processes: async (el) => {
    el.innerHTML = "<p class='dim'>Loading live processes…</p>";
    const procs = await api("/api/processes");
    el.innerHTML = procs.length ? "" : "<p class='dim'>No background processes running.</p>";
    for (const pr of procs) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<div class="row"><span></span><span class="chip">running</span></div>
        <div class="btn-row"><button class="mini-btn logs">Logs</button><button class="mini-btn stop">Stop</button></div>
        <pre class="code" style="display:none"></pre>`;
      card.querySelector("span").textContent = pr.cmd || pr.handle || JSON.stringify(pr).slice(0, 80);
      card.querySelector(".logs").onclick = async () => {
        try {
          const r = await api(`/api/processes/${pr.id || pr.handle}/logs`);
          const pre = card.querySelector("pre");
          pre.style.display = "block";
          pre.textContent = (r.logs || []).join("\n").slice(0, 3000) || "(empty)";
        } catch (err) { alert(err.message); }
      };
      card.querySelector(".stop").onclick = async () => {
        try { await api(`/api/processes/${pr.id || pr.handle}/stop`, { method: "POST" }); } catch (err) {}
        views.processes(el);
      };
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

    const hasArenaLogin = vault.some(v => v.name === "arena_web_email") && vault.some(v => v.name === "arena_web_password");
    const arenaCard = document.createElement("div");
    arenaCard.className = "card arena-connect";
    arenaCard.innerHTML = `<p>Connect your arena.ai account</p>
      <div class="dim">ArenaOS drives a real logged-in arena.ai browser session with these credentials — no developer API key needed.</div>
      <input id="arena-email" type="email" autocomplete="username" placeholder="arena.ai email"/>
      <input id="arena-password" type="password" autocomplete="current-password" placeholder="arena.ai password"/>
      <div class="btn-row"><button class="mini-btn primary" id="arena-connect-btn">Log in to arena.ai →</button></div>
      <div class="dim" style="margin-top:8px">${hasArenaLogin ? "✓ Credentials stored encrypted in the vault." : "Optional: store email + password for agent auto-login; the live browser handles 2FA/CAPTCHA."}</div>`;
    arenaCard.querySelector("#arena-connect-btn").onclick = async () => {
      // tap login -> straight into the real arena.ai page. If email/password
      // are filled, store them in the vault first (agent auto-login); the
      // live browser is where the actual login happens — you type it.
      const email = arenaCard.querySelector("#arena-email").value.trim();
      const password = arenaCard.querySelector("#arena-password").value;
      try {
        if (email && password) {
          await api("/api/vault", { method: "POST", body: JSON.stringify({ name: "arena_web_email", kind: "email", value: email }) });
          await api("/api/vault", { method: "POST", body: JSON.stringify({ name: "arena_web_password", kind: "password", value: password }) });
        }
      } catch {}
      liveBrowserOpen();
    };
    el.appendChild(arenaCard);

    const vaultCard = document.createElement("div");
    vaultCard.className = "card";
    vaultCard.innerHTML = `<p>Other credentials (values encrypted, never shown back)</p>
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
document.querySelectorAll(".drawer-grid [data-view]").forEach((a) => {
  a.onclick = async () => { toggleDrawer(false); await openView(a.dataset.view); };
});
$("#back-chat").onclick = closeView;
$("#topbar-new-chat").onclick = () => $("#new-chat").click();
$("#side-live-browser").onclick = () => { toggleDrawer(false); liveBrowserOpen(); };
$("#side-downloads").onclick = async () => {
  const data = await api("/api/memory/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "arenaos-memory.json"; a.click();
  toggleDrawer(false);
};
$("#chat-search").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#recent-chats .drawer-item").forEach((a) => {
    a.style.display = a.textContent.toLowerCase().includes(q) ? "" : "none";
  });
});
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


/* ---------------- mood picker (real /api/moods presets) ---------------- */
const state_moods = { current: "uncensored", list: [] };
async function loadMoods() {
  try {
    state_moods.list = await api("/api/moods");
  } catch { state_moods.list = [{ key: "uncensored" }]; }
  const menu = $("#mood-menu");
  menu.innerHTML = "";
  for (const m of state_moods.list) {
    const btn = document.createElement("button");
    btn.className = "mood-item" + (m.key === state_moods.current ? " active" : "");
    btn.textContent = m.key.replace(/_/g, " ");
    btn.onclick = () => {
      state_moods.current = m.key;
      $("#mood-label").textContent = m.key.replace(/_/g, " ");
      menu.classList.add("hidden-fade");
      document.querySelectorAll(".mood-item").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    };
    menu.appendChild(btn);
  }
}
$("#mood-btn").onclick = (e) => { e.stopPropagation(); $("#mood-menu").classList.toggle("hidden-fade"); };
document.addEventListener("click", () => $("#mood-menu").classList.add("hidden-fade"));


/* ---------------- live arena.ai login overlay ----------------
   Real page streamed from the server's Chromium over /ws/browser/arena-login.
   Clicks, drags, typing, scrolling and navigation are relayed back into the
   real page — this IS the login, cookies land in the persistent profile. */
const lb = { ws: null, dragging: false, lastPos: null };

function liveBrowserOpen() {
  $("#live-browser").classList.remove("hidden-fade");
  const img = $("#lb-frame");
  img.src = "";
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  lb.ws = new WebSocket(`${proto}//${location.host}/ws/browser/arena-login`);
  lb.ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "frame") img.src = "data:image/jpeg;base64," + msg.data;
    else if (msg.type === "url") $("#lb-url-text").textContent = msg.url.replace(/^https:\/\//, "");
    else if (msg.type === "error") console.warn("live browser:", msg.error);
  };
  lb.ws.onclose = () => { if (!$("#live-browser").classList.contains("hidden-fade")) liveBrowserClose(); };
}

function liveBrowserClose() {
  $("#live-browser").classList.add("hidden-fade");
  if (lb.ws) { lb.ws.close(); lb.ws = null; }
  $("#lb-hidden-input").blur();
}

function lbSend(obj) { if (lb.ws && lb.ws.readyState === 1) lb.ws.send(JSON.stringify(obj)); }

function lbCoords(e) {
  const img = $("#lb-frame");
  const r = img.getBoundingClientRect();
  return {
    x: Math.round((e.clientX - r.left) / r.width * 480),
    y: Math.round((e.clientY - r.top) / r.height * 854),
  };
}

(() => {
  const img = $("#lb-frame");
  img.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.preventDefault();
    lb.dragging = true; lb.lastPos = lbCoords(e);
    lbSend({ type: "mousedown", ...lb.lastPos });
    img.setPointerCapture(e.pointerId);
  });
  img.addEventListener("pointermove", (e) => {
    const pos = lbCoords(e);
    if (lb.dragging) {
      lbSend({ type: "mousemove", ...pos });
    } else {
      lbSend({ type: "mousemove", ...pos });
    }
    lb.lastPos = pos;
  });
  img.addEventListener("pointerup", (e) => {
    if (!lb.dragging) return;
    lb.dragging = false;
    const pos = lbCoords(e);
    const moved = Math.abs(pos.x - lb.lastPos.x) + Math.abs(pos.y - lb.lastPos.y);
    lbSend({ type: "mouseup", ...pos });
    // mobile taps never send a click event to the page — if the pointer
    // barely moved, treat pointerup as the tap itself.
    if (e.pointerType !== "mouse") lbSend({ type: "click", ...pos });
  });
  img.addEventListener("wheel", (e) => {
    e.preventDefault();
    lbSend({ type: "scroll", dx: Math.round(e.deltaX), dy: Math.round(e.deltaY) });
  }, { passive: false });

  // Mobile keyboards: focus a hidden input, forward every keystroke to the page.
  const hidden = $("#lb-hidden-input");
  img.addEventListener("click", () => hidden.focus());
  hidden.addEventListener("beforeinput", (e) => {
    if (e.inputType === "insertText" && e.data) lbSend({ type: "type", text: e.data });
    else if (e.inputType === "insertLineBreak") lbSend({ type: "key", key: "Enter" });
    else if (e.inputType === "deleteContentBackward") lbSend({ type: "key", key: "Backspace" });
  });
  hidden.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); lbSend({ type: "key", key: "Enter" }); }
  });

  $("#lb-back").onclick = () => lbSend({ type: "back" });
  $("#lb-forward").onclick = () => lbSend({ type: "forward" });
  $("#lb-reload").onclick = () => lbSend({ type: "reload" });
  $("#lb-close").onclick = liveBrowserClose;
  $("#lb-done").onclick = () => {
    liveBrowserClose();
    refreshStatus();
    loadRecentChats();
  };
})();


/* ---------------- PIN lock (real, stored server-side via /api/settings) ---------------- */
const pin = { mode: "locked", entry: "", pendingHash: "" };

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function pinShow(mode, subtitle) {
  pin.mode = mode; pin.entry = "";
  $("#pin-title").textContent = mode === "create" ? "Create your PIN" : (mode === "confirm" ? "Confirm your PIN" : "Enter your PIN");
  $("#pin-sub").textContent = subtitle || "";
  $("#pin-error").textContent = "";
  pinRender();
  $("#pin-screen").classList.remove("hidden-fade");
}

function pinRender() {
  document.querySelectorAll("#pin-dots .dot").forEach((d, i) =>
    d.classList.toggle("filled", i < pin.entry.length));
}

async function pinDigit(k) {
  if (k === "del") { pin.entry = pin.entry.slice(0, -1); pinRender(); return; }
  if (k === "bio") { $("#pin-screen").classList.add("hidden-fade"); showLogin(); return; }
  if (pin.entry.length >= 4) return;
  pin.entry += k; pinRender();
  if (pin.entry.length < 4) return;
  $("#pin-error").textContent = "";
  if (pin.mode === "create") {
    pin.pendingHash = await sha256Hex(pin.entry);
    pinShow("confirm", "One more time so you don't get locked out");
  } else if (pin.mode === "confirm") {
    if ((await sha256Hex(pin.entry)) !== pin.pendingHash) {
      pinShow("create", "PINs didn't match — start over"); return;
    }
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ key: "pin_hash", value: pin.pendingHash }) });
    $("#pin-screen").classList.add("hidden-fade");
  } else {
    const stored = (await api("/api/settings")).pin_hash;
    if (stored && (await sha256Hex(pin.entry)) === stored) {
      $("#pin-screen").classList.add("hidden-fade");
    } else {
      pin.entry = ""; pinRender();
      $("#pin-error").textContent = "Wrong PIN — try again";
    }
  }
}

document.querySelectorAll("#pin-pad button").forEach((b) => {
  b.onclick = () => pinDigit(b.dataset.k);
});

/* ---------------- real uploads (attach button) ---------------- */
async function uploadsProjectId() {
  let pid = localStorage.getItem("uploads_project_id");
  if (pid) { try { await api(`/api/projects/${pid}/files?path=.`); return pid; } catch { localStorage.removeItem("uploads_project_id"); } }
  const proj = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: "Uploads", description: "Files attached from chat" }) });
  localStorage.setItem("uploads_project_id", proj.id);
  return proj.id;
}

const pendingUploads = [];

function renderAttachPreview() {
  const box = $("#attach-preview");
  box.innerHTML = "";
  box.classList.toggle("hidden-fade", pendingUploads.length === 0);
  pendingUploads.forEach((f, i) => {
    const chip = document.createElement("span");
    chip.className = "att";
    const nm = document.createElement("span");
    nm.textContent = "📎 " + f;
    const x = document.createElement("span");
    x.className = "x"; x.textContent = "✕";
    x.onclick = () => { pendingUploads.splice(i, 1); renderAttachPreview(); };
    chip.appendChild(nm); chip.appendChild(x);
    box.appendChild(chip);
  });
}

$("#attach-btn").onclick = () => $("#attach-file").click();
$("#attach-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const pid = await uploadsProjectId();
    const fd = new FormData();
    fd.append("file", file);
    fd.append("path", file.name);
    const res = await fetch(`/api/projects/${pid}/files/upload`, { method: "POST", body: fd, credentials: "include" });
    if (!res.ok) throw new Error("upload failed");
    pendingUploads.push(file.name);
    renderAttachPreview();
  } catch (err) { alert("Upload failed: " + err.message); }
});

/* chips tap = send a real prompt */
document.querySelectorAll(".chip-suggest").forEach((c) => {
  c.onclick = () => { $("#chat-input").value = c.dataset.p; sendMessage(); };
});

/* keyboard stays glued to the message bar (iOS Safari + Android) */
if (window.visualViewport) {
  const vv = window.visualViewport;
  vv.addEventListener("resize", () => {
    const dock = $("#input-dock");
    const gap = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    dock.style.paddingBottom = gap > 0 ? gap + "px" : "";
    const stream = $("#chat-stream");
    if (gap > 0) stream.scrollTop = stream.scrollHeight;
  });
}

/* ---------------- boot with PIN gate ---------------- */
async function boot() {
  try { await api("/api/status"); } catch { return; }  // unauthenticated -> login screen stays
  $("#login-screen").style.display = "none";
  let stored = {};
  try { stored = await api("/api/settings"); } catch { return; }
  if (!stored.pin_hash) {
    pinShow("create", "Pick a 4-digit PIN to unlock ArenaOS fast on this device");
  } else {
    pinShow("locked", "Quick unlock for this device");
  }
  await Promise.all([refreshStatus(), loadRecentChats(), loadConversation()]);
}
boot();
