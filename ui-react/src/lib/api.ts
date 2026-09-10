/* Typed API client for the real ArenaOS backend. No mocks — every function
 * hits a live FastAPI route with cookie-session auth. */

export type Mood = { key: string; temperature?: number };
export type Conversation = { id: string; title: string; mode?: string; updated_at?: string | null };
export type ChatMessage = { id?: string; role: "user" | "assistant"; content: string; model?: string | null; ts?: string | null };
export type ToolInfo = { name: string; description?: string; args?: Record<string, unknown> };
export type Task = { id: string; goal: string; status: string; task_type?: string; created_at?: string; error?: string };
export type Proc = { id?: string; handle?: string; cmd?: string } & Record<string, unknown>;
export type FileEntry = { name: string; size: number; dir?: boolean };
export type Project = { id: string; name: string; workspace_path?: string; description?: string };
export type MemoryItem = { id: string; layer: string; content: string; key?: string; created_at?: string };
export type VaultItem = { name: string; kind: string };
export type SSEEvent =
  | { kind: "token"; delta: string }
  | { kind: "tool_call"; tool: string; args?: Record<string, unknown> }
  | { kind: "tool_result"; ok: boolean; output?: string; error?: string }
  | { kind: "learned"; key?: string; content: string }
  | { kind: "done"; model?: string }
  | { kind: "error"; error: string };

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  // No infinite spinners, ever: every request has a hard timeout.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 25000);
  let res: Response;
  try {
    res = await fetch(path, { credentials: "include", signal: ctrl.signal, ...opts });
  } catch {
    throw new Error("connection timed out");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401) throw new Error("auth required");
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = ((await res.json()) as { detail?: string }).detail || detail; } catch { /* keep */ }
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : (res.text() as unknown)) as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  // auth / settings
  login: (password: string) => req<{ ok?: boolean }>("/api/auth/login", { method: "POST", ...json({ password }) }),
  settings: () => req<Record<string, string>>("/api/settings"),
  putSetting: (key: string, value: string) => req<unknown>("/api/settings", { method: "PUT", ...json({ key, value }) }),
  status: () => req<{ transport?: string; engine_ready?: boolean; arena_session_status?: { status?: string; detail?: string } }>("/api/status"),
  moods: () => req<Mood[]>("/api/moods"),

  // conversations
  listConversations: () => req<Conversation[]>("/api/conversations"),
  createConversation: (title: string, mode?: string) => req<{ id: string }>("/api/conversations", { method: "POST", ...json({ title, mode }) }),
  deleteConversation: (id: string) => req<{ deleted: string }>(`/api/conversations/${id}`, { method: "DELETE" }),
  messages: (id: string) => req<ChatMessage[]>(`/api/conversations/${id}/messages`),
  memory: () => req<MemoryItem[]>("/api/memory"),

  // agent
  tasks: () => req<Task[]>("/api/tasks"),
  createTask: (goal: string) => req<Task>("/api/tasks", { method: "POST", ...json({ goal }) }),
  taskAction: (id: string, action: "approve" | "resume" | "cancel") =>
    req<unknown>(`/api/tasks/${id}/${action}`, { method: "POST" }),
  tools: () => req<ToolInfo[]>("/api/tools"),
  invokeTool: (name: string, args: Record<string, unknown>) =>
    req<{ ok: boolean; output?: string; error?: string }>(`/api/tools/${name}/invoke`, { method: "POST", ...json({ args }) }),
  processes: () => req<Proc[]>("/api/processes"),
  processLogs: (id: string) => req<{ logs?: string[] }>(`/api/processes/${id}/logs`),
  stopProcess: (id: string) => req<unknown>(`/api/processes/${id}/stop`, { method: "POST" }),

  // files
  projects: () => req<Project[]>("/api/projects"),
  createProject: (name: string, description?: string) => req<Project>("/api/projects", { method: "POST", ...json({ name, description }) }),
  files: (projectId: string, path = ".") => req<FileEntry[]>(`/api/projects/${projectId}/files?path=${encodeURIComponent(path)}`),
  uploadFile: async (projectId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${projectId}/files/upload`, { method: "POST", body: fd, credentials: "include" });
    if (!res.ok) throw new Error("upload failed");
  },
  fileDownloadUrl: (projectId: string, path: string) => `/api/projects/${projectId}/files/download?path=${encodeURIComponent(path)}`,

  // vault
  vault: () => req<VaultItem[]>("/api/vault"),
  putVault: (name: string, kind: string, value: string) => req<unknown>("/api/vault", { method: "POST", ...json({ name, kind, value }) }),

  exportMemory: () => req<unknown>("/api/memory/export"),
};

/** SSE stream of one agent turn — the same real backend stream the old UI used. */
export async function streamTurn(
  conversationId: string,
  content: string,
  mood: string,
  onEvent: (e: SSEEvent) => void,
): Promise<void> {
  const res = await fetch(`/api/conversations/${conversationId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ content, mood }),
  });
  if (!res.ok || !res.body) throw new Error((await res.text()).slice(0, 200) || `HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      try { onEvent(JSON.parse(part.slice(6)) as SSEEvent); } catch { /* skip partial */ }
    }
  }
}

/** Uploads project: lazily created once, reused forever — files attach from chat. */
export async function uploadsProjectId(): Promise<string> {
  const pid = localStorage.getItem("uploads_project_id");
  if (pid) {
    try { await api.files(pid); return pid; } catch { localStorage.removeItem("uploads_project_id"); }
  }
  const proj = await api.createProject("Uploads", "Files attached from chat");
  localStorage.setItem("uploads_project_id", proj.id);
  return proj.id;
}

export async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
