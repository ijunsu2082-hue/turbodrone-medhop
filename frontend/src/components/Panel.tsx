import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}

export function Panel({ title, action, children }: PanelProps) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.035] p-3">
      <div className="mb-2 flex min-h-6 items-center justify-between gap-2">
        <h2 className="text-xs font-semibold tracking-wide text-gray-400 uppercase">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0b0d10]";
