import { useEffect, useState } from "react";
import { FolderKanban, Loader2, Plus, Trash2 } from "lucide-react";
import { api, type Project } from "../lib/api";
import PageHeader from "../components/PageHeader";

/** Real Projects: each one is an actual isolated workspace directory on
 * disk (created via the sandbox), listed/created/deleted through the real
 * /api/projects endpoints — same backing store the "Uploads" auto-project
 * and Library page use. No mock rows, no fake counters. */
export default function ProjectsPage() {
  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setErr("");
    try { setItems(await api.projects()); }
    catch { setErr("Couldn't load projects — check your connection."); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    setCreating(true); setErr("");
    try {
      await api.createProject(name.trim(), desc.trim());
      setName(""); setDesc("");
      await load();
    } catch { setErr("Couldn't create that project — try again."); }
    finally { setCreating(false); }
  };

  const remove = async (id: string) => {
    setBusyId(id);
    try {
      await api.deleteProject(id);
      setItems((prev) => prev.filter((p) => p.id !== id));
    } catch { setErr("Couldn't delete that project — try again."); }
    finally { setBusyId(null); }
  };

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-5xl overflow-y-auto px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Workspace / 03" title="Projects" description="Each project is a real, isolated workspace on disk — files, uploads and generated work live inside it." />

      <div className="arc-card mb-5 rounded-3xl p-4 sm:p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New project name…"
            className="min-w-0 flex-1 rounded-xl border border-white/[.1] bg-white/[.035] px-3.5 py-2.5 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-300/40" />
          <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)"
            className="min-w-0 flex-1 rounded-xl border border-white/[.1] bg-white/[.035] px-3.5 py-2.5 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-300/40" />
          <button onClick={create} disabled={creating || !name.trim()}
            className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-cyan-300 to-violet-500 px-4 py-2.5 text-xs font-bold text-[#10132f] active:scale-[.98] disabled:opacity-40">
            {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}New project
          </button>
        </div>
        {err && <p className="mt-2 text-xs text-rose-300">{err}</p>}
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" />Loading projects…</div>
      ) : items.length === 0 ? (
        <div className="arc-card flex flex-col items-center gap-2 rounded-3xl p-10 text-center">
          <FolderKanban size={28} className="text-slate-600" />
          <p className="text-sm text-slate-400">No projects yet — create one above to get a real isolated workspace.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((p) => (
            <div key={p.id} className="arc-card flex flex-col gap-2 rounded-2xl p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-400/10 text-violet-200"><FolderKanban size={16} /></span>
                  <b className="min-w-0 truncate text-sm text-white">{p.name}</b>
                </div>
                <button onClick={() => remove(p.id)} disabled={busyId === p.id} aria-label="Delete project"
                  className="shrink-0 rounded-lg p-1.5 text-slate-600 hover:bg-rose-400/10 hover:text-rose-300 disabled:opacity-40">
                  {busyId === p.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                </button>
              </div>
              {p.description && <p className="text-xs leading-5 text-slate-500">{p.description}</p>}
              <p className="arc-mono text-[10.5px] text-slate-600">{p.workspace_path}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
