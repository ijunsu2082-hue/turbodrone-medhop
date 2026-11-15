import React from "react";
import type { ControlMode } from "../hooks/useControls";
import { focusRing } from "./Panel";

interface Props {
  mode: ControlMode;
  setMode: (m: ControlMode) => void;
  gamepadConnected: boolean;
}

export const ControlSchemeToggle: React.FC<Props> = ({ mode, setMode, gamepadConnected }) => {
  const toKeyboard = () => setMode("inc");

  const toGamepad = () => {
    if (gamepadConnected) setMode("abs");
  };

  const toTrackPoint = () => {
    /* Pointer-Lock must be requested from a user-generated event */
    document.body.requestPointerLock();
    setMode("mouse");
  };

  const options = [
    { label: "Keyboard", active: mode === "inc", onClick: toKeyboard, disabled: false, title: undefined },
    {
      label: "Gamepad",
      active: mode === "abs",
      onClick: toGamepad,
      disabled: !gamepadConnected,
      title: gamepadConnected ? undefined : "Plug in a gamepad and move a stick",
    },
    { label: "TrackPoint", active: mode === "mouse", onClick: toTrackPoint, disabled: false, title: "Esc to release" },
  ];

  return (
    <div className="grid grid-cols-3 gap-1 rounded-lg bg-white/[0.06] p-1" role="group" aria-label="Input device">
      {options.map((option) => (
        <button
          key={option.label}
          type="button"
          onClick={option.onClick}
          disabled={option.disabled}
          title={option.title}
          aria-pressed={option.active}
          className={`rounded-md py-1.5 text-xs font-semibold transition-colors disabled:opacity-40 ${focusRing} ${
            option.active ? "bg-sky-600 text-white" : "text-gray-300 enabled:hover:bg-white/10"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};
