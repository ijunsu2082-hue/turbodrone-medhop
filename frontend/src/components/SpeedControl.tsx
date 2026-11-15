import type { SpeedTier } from "../hooks/useControls";
import { focusRing } from "./Panel";

interface SpeedControlProps {
  value: SpeedTier;
  onChange: (tier: SpeedTier) => void;
}

const TIERS: { value: SpeedTier; label: string; help: string }[] = [
  { value: 0, label: "Low", help: "Slow. Best for indoors and learning" },
  { value: 1, label: "Med", help: "Medium" },
  { value: 2, label: "High", help: "Full speed" },
];

export default function SpeedControl({ value, onChange }: SpeedControlProps) {
  return (
    <div className="grid grid-cols-3 gap-1 rounded-lg bg-white/[0.06] p-1" role="group" aria-label="Manual speed">
      {TIERS.map((tier) => {
        const active = value === tier.value;
        return (
          <button
            key={tier.value}
            type="button"
            onClick={() => onChange(tier.value)}
            title={tier.help}
            aria-pressed={active}
            className={`rounded-md py-1.5 text-xs font-semibold transition-colors ${focusRing} ${
              active ? "bg-sky-600 text-white" : "text-gray-300 hover:bg-white/10"
            }`}
          >
            {tier.label}
          </button>
        );
      })}
    </div>
  );
}
