import { usePlugins } from "../hooks/usePlugins";
import type { FollowStatus } from "../hooks/useStatus";
import { TONE_DOT, describeFollow } from "./FollowStatusText";
import { Panel, focusRing } from "./Panel";

const FOLLOW_PLUGIN = "FollowPlugin";

function Toggle({
  label,
  checked,
  onToggle,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onToggle}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${focusRing} ${
        checked ? "bg-emerald-500" : "bg-white/20 hover:bg-white/30"
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
          checked ? "translate-x-5" : ""
        }`}
      />
    </button>
  );
}

function FollowDetails({ status }: { status: FollowStatus }) {
  const { tone, title, detail } = describeFollow(status);
  const hasStats = status.fps !== undefined && status.fps > 0;

  return (
    <div aria-live="polite">
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${TONE_DOT[tone]}`} />
        <span className="text-sm font-medium text-white">{title}</span>
      </div>
      <p className="mt-0.5 text-xs text-gray-400">{detail}</p>
      {hasStats && (
        <p className="mt-1 text-xs text-gray-500 tabular-nums">
          Seen in {status.detection_rate}% of frames at {status.fps} fps
        </p>
      )}
      {status.dark && (
        <p className="mt-1 text-xs text-amber-300">
          The video is dark. More light helps tracking and hovering.
        </p>
      )}
    </div>
  );
}

export function FollowPanel({ status }: { status: FollowStatus | null }) {
  const { pluginsEnabled, availablePlugins, runningPlugins, error, togglePlugin } = usePlugins();

  if (!pluginsEnabled) {
    return null;
  }

  const toggle = async (name: string) => {
    const wasRunning = runningPlugins.has(name);
    await togglePlugin(name);
    window.dispatchEvent(new CustomEvent(wasRunning ? "plugin:stopped" : "plugin:running"));
  };

  const followOn = runningPlugins.has(FOLLOW_PLUGIN);
  const otherPlugins = availablePlugins.filter((name) => name !== FOLLOW_PLUGIN);

  return (
    <Panel
      title="Follow me"
      action={
        availablePlugins.includes(FOLLOW_PLUGIN) && (
          <Toggle label="Follow me" checked={followOn} onToggle={() => toggle(FOLLOW_PLUGIN)} />
        )
      }
    >
      {followOn ? (
        <>
          <FollowDetails status={status ?? { state: "starting", paused: false }} />
          <p className="mt-2 border-t border-white/10 pt-2 text-xs text-gray-500">
            Flight keys take over while you hold them. Land or E-Stop turns follow off.
          </p>
        </>
      ) : (
        <p className="text-xs text-gray-400">Stand in view and turn this on, before or after takeoff.</p>
      )}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      {otherPlugins.length > 0 && (
        <details className="mt-2 text-xs text-gray-500">
          <summary className={`cursor-pointer rounded ${focusRing}`}>Test plugins</summary>
          <ul className="mt-2 space-y-2">
            {otherPlugins.map((name) => (
              <li key={name} className="flex items-center justify-between gap-2 text-gray-300">
                {name}
                <Toggle label={name} checked={runningPlugins.has(name)} onToggle={() => toggle(name)} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
