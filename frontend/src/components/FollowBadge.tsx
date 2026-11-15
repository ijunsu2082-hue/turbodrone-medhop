import type { FollowStatus } from "../hooks/useStatus";
import { TONE_DOT, describeFollow } from "./FollowStatusText";

export function FollowBadge({ status }: { status: FollowStatus }) {
  const { tone, title, detail } = describeFollow(status);

  return (
    <div className="pointer-events-none absolute top-3 left-3 z-20 flex items-center gap-2.5 rounded-lg bg-black/70 px-3 py-2 backdrop-blur-sm">
      <span aria-hidden="true" className={`h-2.5 w-2.5 shrink-0 rounded-full ${TONE_DOT[tone]}`} />
      <div>
        <div className="text-sm leading-tight font-medium text-white">{title}</div>
        <div className="text-xs leading-tight text-gray-300">{detail}</div>
      </div>
    </div>
  );
}
