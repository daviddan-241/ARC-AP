import { ReactNode } from "react";

export default function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="arc-mono mb-3 text-[10px] uppercase tracking-[.25em] text-[#007AFF]/70">{eyebrow}</p>}
        <h1 className="arc-title text-4xl font-bold text-[#111827] sm:text-5xl">{title}</h1>
        {description && <p className="mt-3 max-w-xl text-sm leading-6 text-[#4B5563]">{description}</p>}
      </div>
      {action}
    </div>
  );
}
