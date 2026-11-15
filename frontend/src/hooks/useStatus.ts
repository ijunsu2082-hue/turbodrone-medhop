import { useEffect, useState } from "react";

const STATUS_WS_URL = "ws://localhost:8000/ws/status";

export type FollowState =
  | "starting"
  | "tracking"
  | "holding"
  | "searching"
  | "lost"
  | "no_video";

export interface FollowStatus {
  state: FollowState;
  paused: boolean;
  fps?: number;
  detection_rate?: number;
  confidence?: number | null;
  offset?: number | null;
  box?: number | null;
  yaw?: number;
  pitch?: number;
  dark?: boolean;
}

export interface BackendStatus {
  connected: boolean;
  videoLive: boolean;
  plugins: string[];
  follow: FollowStatus | null;
  recording: { active: boolean; seconds: number };
}

const DISCONNECTED: BackendStatus = {
  connected: false,
  videoLive: false,
  plugins: [],
  follow: null,
  recording: { active: false, seconds: 0 },
};

export function useStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>(DISCONNECTED);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      socket = new WebSocket(STATUS_WS_URL);
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setStatus({
          connected: true,
          videoLive: Boolean(data.video_live),
          plugins: data.plugins ?? [],
          follow: data.plugin_status?.FollowPlugin ?? null,
          recording: data.recording ?? DISCONNECTED.recording,
        });
      };
      socket.onclose = () => {
        if (disposed) return;
        setStatus(DISCONNECTED);
        retryTimer = setTimeout(connect, 1000);
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return status;
}
