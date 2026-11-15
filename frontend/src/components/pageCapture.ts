const API_BASE_URL = "http://localhost:8000";

const FORMATS: Array<[mimeType: string, extension: string]> = [
  ["video/mp4;codecs=avc1", "mp4"],
  ["video/mp4", "mp4"],
  ["video/webm;codecs=h264", "webm"],
  ["video/webm", "webm"],
];

export interface PageCapture {
  /** Stop capturing and wait until everything has reached the backend. */
  finish: () => Promise<void>;
}

/** Ask the browser to share this tab. Must run directly from the click. Null if declined. */
export async function requestPageStream(): Promise<MediaStream | null> {
  try {
    return await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 30 },
      audio: false,
      preferCurrentTab: true,
      selfBrowserSurface: "include",
    } as DisplayMediaStreamOptions);
  } catch {
    return null;
  }
}

/** Stream the shared tab to the backend, which saves it next to the drone video. */
export async function startPageCapture(stream: MediaStream): Promise<PageCapture | null> {
  const stopStream = () => stream.getTracks().forEach((track) => track.stop());
  const format = FORMATS.find(([mimeType]) => MediaRecorder.isTypeSupported(mimeType));
  if (!format) {
    stopStream();
    return null;
  }

  const started = await fetch(`${API_BASE_URL}/recording/page/start?extension=${format[1]}`, { method: "POST" }).catch(
    () => null,
  );
  if (!started?.ok) {
    stopStream();
    return null;
  }

  // One upload at a time, because the pieces must arrive in order.
  let uploads: Promise<void> = Promise.resolve();
  let uploadError: Error | null = null;
  const recorder = new MediaRecorder(stream, { mimeType: format[0], videoBitsPerSecond: 8_000_000 });
  recorder.ondataavailable = ({ data }) => {
    if (data.size === 0) return;
    uploads = uploads.then(async () => {
      const chunkSize = 2 * 1024 * 1024;
      for (let offset = 0; offset < data.size && !uploadError; offset += chunkSize) {
        try {
          const response = await fetch(`${API_BASE_URL}/recording/page/chunk`, {
            method: "POST",
            body: data.slice(offset, offset + chunkSize),
          });
          if (!response.ok) throw new Error("A page recording chunk could not be saved");
        } catch (error) {
          uploadError = error instanceof Error ? error : new Error("A page recording chunk could not be saved");
        }
      }
    });
  };
  const stopped = new Promise<void>((resolve) => {
    recorder.onstop = () => resolve();
  });
  recorder.start(1000);

  return {
    finish: async () => {
      if (recorder.state !== "inactive") recorder.stop();
      await stopped;
      stopStream();
      await uploads;
      if (uploadError) throw uploadError;
    },
  };
}
