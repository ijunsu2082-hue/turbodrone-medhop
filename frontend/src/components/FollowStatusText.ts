import type { FollowStatus } from "../hooks/useStatus";

export type Tone = "good" | "working" | "bad" | "info";

export const TONE_DOT: Record<Tone, string> = {
  good: "bg-emerald-400",
  working: "bg-amber-400",
  bad: "bg-red-500",
  info: "bg-sky-400",
};

function trackingDetail(status: FollowStatus): string {
  const pitch = status.pitch ?? 0;
  if (pitch < 0) return "Too close, backing up";
  if (pitch > 0) return "Moving closer";
  if (status.yaw) return "Turning to face you";
  return "Right distance, holding";
}

export function describeFollow(status: FollowStatus): { tone: Tone; title: string; detail: string } {
  if (status.paused) {
    return { tone: "info", title: "Paused while you fly", detail: "Resumes a second after you let go" };
  }
  switch (status.state) {
    case "starting":
      return { tone: "working", title: "Starting up", detail: "This can take a few seconds" };
    case "tracking":
      return { tone: "good", title: "Following you", detail: trackingDetail(status) };
    case "holding":
      return { tone: "working", title: "Lost you for a moment", detail: "Carrying on" };
    case "searching":
      return { tone: "working", title: "Looking for you", detail: "Trying to get you back in view" };
    case "lost":
      return { tone: "bad", title: "Can't see you", detail: "Hovering. Step in front of the camera" };
    case "no_video":
      return { tone: "bad", title: "No video", detail: "Hovering until video returns" };
  }
}
