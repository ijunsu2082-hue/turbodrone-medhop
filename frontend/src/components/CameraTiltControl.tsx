import type { PointerEvent } from "react";
import type { CameraTiltDirection } from "../hooks/useControls";
import { focusRing } from "./Panel";

interface CameraTiltControlProps {
  activeDirection: CameraTiltDirection;
  onTiltChange: (direction: CameraTiltDirection) => void;
}

export default function CameraTiltControl({ activeDirection, onTiltChange }: CameraTiltControlProps) {
  const bindHold = (direction: CameraTiltDirection) => ({
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      event.currentTarget.setPointerCapture(event.pointerId);
      onTiltChange(direction);
    },
    onPointerUp: () => onTiltChange(0),
    onPointerCancel: () => onTiltChange(0),
    onPointerLeave: () => onTiltChange(0),
    onBlur: () => onTiltChange(0),
  });

  const buttonClasses = (direction: CameraTiltDirection) =>
    `rounded-md py-1.5 text-xs font-semibold transition-colors select-none ${focusRing} ${
      activeDirection === direction ? "bg-sky-600 text-white" : "bg-white/[0.06] text-gray-300 hover:bg-white/10"
    }`;

  return (
    <div className="grid grid-cols-2 gap-2">
      <button
        type="button"
        className={buttonClasses(1)}
        title="Hold to keep tilting up (Page Up)"
        aria-pressed={activeDirection === 1}
        {...bindHold(1)}
      >
        Tilt up
      </button>
      <button
        type="button"
        className={buttonClasses(-1)}
        title="Hold to keep tilting down (Page Down)"
        aria-pressed={activeDirection === -1}
        {...bindHold(-1)}
      >
        Tilt down
      </button>
    </div>
  );
}
