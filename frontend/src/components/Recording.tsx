import { useRef, useState } from "react";
import { type PageCapture, requestPageStream, startPageCapture } from "./pageCapture";
import { focusRing } from "./Panel";

const API_BASE_URL = "http://localhost:8000";

function formatTime(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function RecordingBadge({ seconds }: { seconds: number }) {
  return (
    <div className="pointer-events-none absolute top-3 right-3 z-20 flex items-center gap-2 rounded-lg bg-black/70 px-3 py-2 backdrop-blur-sm">
      <span aria-hidden="true" className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
      <span className="text-sm font-medium text-white tabular-nums">REC {formatTime(seconds)}</span>
    </div>
  );
}

interface RecordButtonProps {
  recording: { active: boolean; seconds: number };
  videoLive: boolean;
}

export function RecordButton({ recording, videoLive }: RecordButtonProps) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; isError: boolean } | null>(null);

  const pageCapture = useRef<PageCapture | null>(null);

  const start = async () => {
    // The browser only allows this prompt straight from the click, so it comes first.
    const stream = await requestPageStream();
    const response = await fetch(`${API_BASE_URL}/recording/start`, { method: "POST" });
    if (!response.ok) {
      stream?.getTracks().forEach((track) => track.stop());
      const data = await response.json();
      setMessage({ text: data.detail ?? "Recording failed", isError: true });
      return;
    }
    pageCapture.current = stream && (await startPageCapture(stream));
    if (!pageCapture.current) {
      setMessage({ text: "Recording the drone video only. The page isn't being recorded.", isError: false });
    }
  };

  const stop = async () => {
    let pageFailed = false;
    try {
      await pageCapture.current?.finish();
    } catch {
      pageFailed = true;
    } finally {
      pageCapture.current = null;
    }
    const response = await fetch(`${API_BASE_URL}/recording/stop`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) {
      setMessage({ text: data.detail ?? "Recording failed", isError: true });
      return;
    }
    const saved = [data.path, data.page_path].filter(Boolean);
    setMessage(
      pageFailed
        ? { text: saved.length ? `Recording saved, but the page capture is incomplete. Files: ${saved.join(" and ")}` : "The page capture failed and no recording was saved.", isError: true }
        : saved.length
          ? { text: `Saved to ${saved.join(" and ")}`, isError: false }
          : { text: "Nothing saved because no video arrived.", isError: true },
    );
  };

  const toggle = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await (recording.active ? stop() : start());
    } catch {
      setMessage({ text: "Can't reach the backend", isError: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        disabled={busy || (!recording.active && !videoLive)}
        title={!recording.active && !videoLive ? "Connect to the drone to record" : undefined}
        className={`flex w-full items-center justify-center gap-2 rounded-md py-1.5 text-xs font-semibold transition-colors disabled:opacity-40 ${focusRing} ${
          recording.active ? "bg-red-600 text-white hover:bg-red-500" : "bg-white/[0.06] text-gray-200 enabled:hover:bg-white/10"
        }`}
      >
        <span
          aria-hidden="true"
          className={recording.active ? "h-2.5 w-2.5 rounded-sm bg-white" : "h-2.5 w-2.5 rounded-full bg-red-500"}
        />
        {recording.active ? `Stop recording ${formatTime(recording.seconds)}` : "Record video"}
      </button>
      {message && (
        <p className={`mt-1 text-xs break-all ${message.isError ? "text-red-400" : "text-gray-400"}`} aria-live="polite">
          {message.text}
        </p>
      )}
    </div>
  );
}
