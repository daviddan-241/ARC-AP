import { useEffect, useState } from "react";
import { Camera, FileText } from "lucide-react";
import { api, uploadsProjectId } from "../lib/api";
import type { FileEntry } from "../lib/api";

const DOC_EXT = [".txt", ".md", ".pdf", ".doc", ".docx"];
const MEDIA_EXT = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4"];

const fmt = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** Library — your real uploaded documents and media from the Uploads workspace. */
export default function Library() {
  const [pid, setPid] = useState("");
  const [files, setFiles] = useState<FileEntry[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const id = await uploadsProjectId();
        setPid(id);
        setFiles(await api.files(id));
      } catch { setFailed(true); }
    })();
  }, []);

  const docs = (files ?? []).filter((f) => !f.dir && DOC_EXT.some((e) => f.name.toLowerCase().endsWith(e)));
  const media = (files ?? []).filter((f) => !f.dir && MEDIA_EXT.some((e) => f.name.toLowerCase().endsWith(e)));
  const cells = [...media.map((f) => f.name), ...Array(Math.max(0, 6 - media.length)).fill(null)].slice(0, 6);

  return (
    <div className="h-full overflow-y-auto px-4 pt-2 pb-8">
      <h1 className="text-[28px] font-bold tracking-tight text-ink">Library</h1>

      <div className="section-label mt-6 mb-2">Documents</div>
      {files === null && !failed && <p className="text-[13px] text-ink-dim py-3">Loading…</p>}
      {failed && <p className="text-[13px] text-ink-dim py-3">Couldn&apos;t load the uploads workspace</p>}
      {files !== null && docs.length === 0 && (
        <div className="rounded-card bg-surface p-8 flex flex-col items-center gap-3">
          <FileText size={40} strokeWidth={1.2} className="text-ink-dim" />
          <p className="text-[15px] text-ink-dim">No documents yet</p>
          <p className="text-[12.5px] text-ink-dim">Attach files in chat and they land here</p>
        </div>
      )}
      {docs.map((f) => (
        <div key={f.name} className="flex items-center gap-3 p-3.5 rounded-2xl hover:bg-surface2 transition-colors">
          <span className="w-10 h-10 rounded-full bg-surface2 flex items-center justify-center shrink-0">
            <FileText size={18} strokeWidth={1.5} className="text-ink" />
          </span>
          <span className="flex-1 min-w-0">
            <span className="block text-[15px] font-medium text-ink truncate">{f.name}</span>
            <span className="block text-[13px] text-ink-dim">{fmt(f.size)}</span>
          </span>
          <a href={api.fileDownloadUrl(pid, f.name)} className="shrink-0 border border-line rounded-full px-3 py-1.5 text-[13px] font-medium text-accent">Download</a>
        </div>
      ))}

      <div className="section-label mt-6 mb-2">Media</div>
      <div className="grid grid-cols-3 gap-2">
        {cells.map((name, i) =>
          name ? (
            <img key={i} src={api.fileDownloadUrl(pid, name)} alt={name} className="aspect-square object-cover rounded-2xl bg-surface2" />
          ) : (
            <div key={i} className="aspect-square rounded-2xl bg-surface2 border border-dashed border-line flex items-center justify-center">
              <Camera size={18} className="text-ink-dim" />
            </div>
          ),
        )}
      </div>
    </div>
  );
}
