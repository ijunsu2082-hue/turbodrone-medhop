import type { Axes, CameraTiltDirection } from "../hooks/useControls";

function Key({ label, active }: { label: string; active: boolean }) {
  return (
    <kbd
      className={`inline-flex h-6 min-w-6 items-center justify-center rounded border px-1.5 font-sans text-xs ${
        active ? "border-sky-400 bg-sky-500 text-white" : "border-white/15 bg-white/[0.06] text-gray-300"
      }`}
    >
      {label}
    </kbd>
  );
}

function Hint({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {children}
      <span className="text-xs whitespace-nowrap text-gray-500">{label}</span>
    </span>
  );
}

interface KeyHintsProps {
  axes: Axes;
  tilt: CameraTiltDirection;
}

export function KeyHints({ axes, tilt }: KeyHintsProps) {
  return (
    <div className="flex shrink-0 flex-wrap items-center justify-center gap-x-5 gap-y-1.5 border-t border-white/10 px-4 py-2">
      <Hint label="Forward / back">
        <Key label="W" active={axes.pitch > 0} />
        <Key label="S" active={axes.pitch < 0} />
      </Hint>
      <Hint label="Slide">
        <Key label="A" active={axes.roll < 0} />
        <Key label="D" active={axes.roll > 0} />
      </Hint>
      <Hint label="Up / down">
        <Key label="↑" active={axes.throttle > 0} />
        <Key label="↓" active={axes.throttle < 0} />
      </Hint>
      <Hint label="Turn">
        <Key label="←" active={axes.yaw < 0} />
        <Key label="→" active={axes.yaw > 0} />
      </Hint>
      <Hint label="Camera">
        <Key label="Pg Up" active={tilt > 0} />
        <Key label="Pg Dn" active={tilt < 0} />
      </Hint>
    </div>
  );
}
