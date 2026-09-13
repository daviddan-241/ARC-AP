import { useEffect, useMemo, useRef, useState } from "react";
import { Download, FileText, ImageIcon, Loader2, Search, Upload } from "lucide-react";
import { api, uploadsProjectId } from "../lib/api";
import type { FileEntry } from "../lib/api";
import PageHeader from "../components/PageHeader";

const IMAGES = /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i;

/** The real library: files actually uploaded to the server's Uploads project,
 * with real download links. Nothing is a mock entry. */
export default function LibraryPage() {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const pid = await uploadsProjectId();
      setProjectId(pid);
      setFiles(await api.files(pid));
    } catch { /* gate handles auth */ }
    finally { setLoaded(true); }
  };
  useEffect(() => { load(); }, []);

  const upload = async (file: File) => {
    if (!projectId || uploading) return;
    setUploading(true);
    try { await api.uploadFile(projectId, file); await load(); } finally { setUploading(false); }
  };

  const filtered = useMemo(() => files.filter((f) => !f.dir && f.name.toLowerCase().includes(query.toLowerCase())), [files, query]);
  const docs = filtered.filter((f) => !IMAGES.test(f.name));
  const images = filtered.filter((f) => IMAGES.test(f.name));

  return (
    <div className="arc-page-scroll mx-auto h-full max-w-5xl overflow-y-auto px-4 py-8 pb-24 sm:px-8 lg:px-12">
      <PageHeader eyebrow="Memory / 05" title="Library" description="Files you've attached and the agent has produced — stored on the server, downloadable anytime." action={
        <button onClick={() => fileRef.current?.click()} disabled={uploading}
          className="flex items-center gap-2 rounded-xl border border-[#E5E7EB] bg-black/[.04] px-4 py-2.5 text-xs font-bold text-[#111827] hover:bg-black/[.06] disabled:opacity-40">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}Add to library
        </button>
      } />
      <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />

      <div className="mb-8 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-3 text-[#9CA3AF]" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search your library"
            className="arc-focus w-full rounded-xl border border-[#E5E7EB] bg-black/[.03] py-2.5 pl-9 pr-3 text-sm text-[#111827] outline-none placeholder:text-[#9CA3AF]" />
        </div>
      </div>

      <section className="mb-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[#111827]">Documents</h2>
          <span className="text-xs text-[#9CA3AF]">{docs.length} items</span>
        </div>
        {loaded && filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#E5E7EB] px-6 py-12 text-center">
            <FileText size={24} className="mx-auto mb-3 text-[#9CA3AF]" />
            <p className="text-sm text-[#374151]">{files.length === 0 ? "No documents yet" : "No matching documents"}</p>
            <p className="mt-2 text-xs text-[#9CA3AF]">Attach a file in Chat or upload one here — it goes to the server for real.</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {docs.map((f) => (
              <div key={f.name} className="arc-card flex items-center gap-3 rounded-2xl p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#6366F1]/10 text-[#6366F1]"><FileText size={17} /></div>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-sm text-[#111827]">{f.name}</b>
                  <small className="text-xs text-[#9CA3AF]">{(f.size / 1024).toFixed(1)} KB</small>
                </span>
                {projectId && <a href={api.fileDownloadUrl(projectId, f.name)} download aria-label={`Download ${f.name}`}
                  className="flex h-9 w-9 items-center justify-center rounded-xl text-[#4B5563] hover:bg-black/[.05] hover:text-[#111827]"><Download size={16} /></a>}
              </div>
            ))}
          </div>
        )}
      </section>

      {images.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#111827]">Media</h2>
            <span className="text-xs text-[#9CA3AF]">{images.length} images</span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {images.map((f) => projectId ? (
              <a key={f.name} href={api.fileDownloadUrl(projectId, f.name)} target="_blank" rel="noreferrer"
                className="group flex aspect-[1.3] items-center justify-center rounded-2xl border border-[#E5E7EB] bg-black/[.02] hover:border-[#6366F1]/40">
                <ImageIcon size={20} className="text-[#9CA3AF] group-hover:text-[#6366F1]" />
              </a>
            ) : null)}
          </div>
        </section>
      )}
    </div>
  );
}
