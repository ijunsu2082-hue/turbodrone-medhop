interface Props {
  x: number;           // -1 … +1 (left … right)
  y: number;           // -1 … +1 (down … up)   – positive y = up
  size?: number;
  label?: string;
}

export default function AxisIndicator({ x, y, size = 84, label }: Props) {
  // clamp outside callers just in case
  x = Math.max(-1, Math.min(1, x));
  y = Math.max(-1, Math.min(1, y));

  const radius = size * 0.4;            // max travel inside the square
  const active = x !== 0 || y !== 0;

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="relative rounded-full border border-white/15 bg-black/30"
        style={{ width: size, height: size }}
      >
        <div className="absolute top-1/2 left-0 h-px w-full bg-white/10" />
        <div className="absolute top-0 left-1/2 h-full w-px bg-white/10" />
        <div
          className={`absolute h-3.5 w-3.5 rounded-full ${active ? "bg-sky-400" : "bg-gray-400"}`}
          style={{
            left: `calc(50% + ${x * radius}px)`,
            top: `calc(50% + ${-y * radius}px)`,
            transform: "translate(-50%, -50%)",
          }}
        />
      </div>
      {label && <span className="text-xs text-gray-500">{label}</span>}
    </div>
  );
}
