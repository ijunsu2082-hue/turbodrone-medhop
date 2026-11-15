import type { BackendStatus } from "../hooks/useStatus";

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs text-gray-300">
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : "bg-gray-500"}`}
      />
      {label}
    </span>
  );
}

interface TopBarProps {
  droneType: string;
  status: BackendStatus;
}

export function TopBar({ droneType, status }: TopBarProps) {
  const droneLabel = droneType === "unknown" ? null : droneType.replace(/_/g, " ").toUpperCase();

  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4">
      <div className="flex items-baseline gap-2.5">
        <h1 className="text-base font-semibold tracking-tight text-white">Turbodrone</h1>
        {droneLabel && <span className="text-xs text-gray-500">{droneLabel}</span>}
      </div>
      <div className="flex items-center gap-2" aria-live="polite">
        <StatusPill ok={status.connected} label={status.connected ? "Backend online" : "Backend offline"} />
        <StatusPill ok={status.videoLive} label={status.videoLive ? "Drone connected" : "No drone video"} />
      </div>
    </header>
  );
}
