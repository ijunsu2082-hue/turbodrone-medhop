import { useEffect, useRef, useState } from "react";
import type { CommandCapabilities } from "../hooks/useControls";
import { Panel, focusRing } from "./Panel";

interface CommandButtonsProps {
  capabilities: CommandCapabilities;
  following: boolean;
  onTakeoff: () => void;
  onLand: () => void;
  onEstop: () => void;
  onCalibrate: () => void;
}

// Takeoff and land are one toggle on these drones, so a double click would undo itself.
const ONE_KEY_COOLDOWN_MS = 1000;

const CALIBRATE_WARNING =
  "Calibrate the drone?\n\nOnly do this with the drone on flat, level ground and the motors off.";

const baseButton = `rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors disabled:opacity-40 ${focusRing}`;

export default function CommandButtons({
  capabilities,
  following,
  onTakeoff,
  onLand,
  onEstop,
  onCalibrate,
}: CommandButtonsProps) {
  const [coolingDown, setCoolingDown] = useState(false);
  const cooldownTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(cooldownTimer.current), []);

  const oneKey = (action: () => void) => () => {
    action();
    setCoolingDown(true);
    clearTimeout(cooldownTimer.current);
    cooldownTimer.current = setTimeout(() => setCoolingDown(false), ONE_KEY_COOLDOWN_MS);
  };

  return (
    <Panel title="Flight">
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={oneKey(onTakeoff)}
          disabled={!capabilities.takeoff || coolingDown}
          className={`${baseButton} bg-emerald-600 text-white hover:bg-emerald-500`}
        >
          Takeoff
        </button>
        <button
          type="button"
          onClick={oneKey(onLand)}
          disabled={!capabilities.land || coolingDown}
          className={`${baseButton} bg-white/10 text-white hover:bg-white/20`}
        >
          Land
        </button>
        <button
          type="button"
          onClick={onEstop}
          disabled={!capabilities.estop}
          className={`${baseButton} col-span-2 bg-red-600 text-white hover:bg-red-500`}
          title="Cuts the motors immediately. The drone will drop."
        >
          E-Stop
        </button>
      </div>
      <p className="mt-2 text-xs text-gray-500">
        Takeoff and Land send the same signal. Click once and wait. E-Stop cuts the motors.
      </p>
      {capabilities.calibrate && (
        <button
          type="button"
          disabled={following}
          onClick={() => {
            if (window.confirm(CALIBRATE_WARNING)) onCalibrate();
          }}
          className={`mt-2 w-full rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors hover:bg-white/10 disabled:opacity-40 ${focusRing}`}
          title="Fixes a drone that tilts or drifts. On flat ground only."
        >
          Calibrate level (on the ground)
        </button>
      )}
    </Panel>
  );
}
