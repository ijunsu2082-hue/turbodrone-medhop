import { useEffect, useRef, useState } from "react";

const RETRY_DELAY_MS = 2000;

export function VideoFeed({ src, live }: { src: string; live?: boolean }) {
  const [attempt, setAttempt] = useState(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wasLive = useRef(live);

  useEffect(() => () => clearTimeout(retryTimer.current), []);

  // The backend ends the stream when video stalls, and an <img> never reopens it.
  useEffect(() => {
    if (live && wasLive.current === false) {
      setAttempt((n) => n + 1);
    }
    wasLive.current = live;
  }, [live]);

  return (
    <img
      src={attempt === 0 ? src : `${src}?retry=${attempt}`}
      alt="Drone video feed"
      className="absolute inset-0 h-full w-full object-contain"
      onError={() => {
        clearTimeout(retryTimer.current);
        retryTimer.current = setTimeout(() => setAttempt((n) => n + 1), RETRY_DELAY_MS);
      }}
    />
  );
}
