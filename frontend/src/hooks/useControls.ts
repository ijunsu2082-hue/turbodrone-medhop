import { useCallback, useEffect, useRef, useState } from "react";

/* ─────────────────────────────────────────────────────────── */
/*  Shared types                                               */
export type ControlMode = "inc" | "abs" | "mouse";

export interface Axes {
  throttle: number;  // -1 … +1  (down / up)
  yaw:      number;  // -1 … +1  (left / right)
  pitch:    number;  // -1 … +1  (back / fwd)
  roll:     number;  // -1 … +1  (left / right)
}

export interface CommandCapabilities {
  takeoff: boolean;
  land: boolean;
  estop: boolean;
  camera_tilt: boolean;
  camera_switch: boolean;
  speed_control: boolean;
  calibrate: boolean;
}

export type SpeedTier = 0 | 1 | 2;
export type CameraTiltDirection = -1 | 0 | 1;
/* ─────────────────────────────────────────────────────────── */

export function useControls() {
  const API_BASE_URL = "http://localhost:8000";

  /* ------- state refs (mutable) ------- */
  const axesRef = useRef<Axes>({ throttle: 0, yaw: 0, pitch: 0, roll: 0 });
  const modeRef = useRef<ControlMode>("inc");
  const cameraTiltDirectionRef = useRef<CameraTiltDirection>(0);

  /* ------- NEW: websocket ref & lifecycle ------- */
  const ws = useRef<WebSocket | null>(null);
  
  /* ------- Plugin state (event-driven) ------- */
  const pluginRunningRef = useRef<boolean>(false);
  const stoppedPluginOnceRef = useRef<boolean>(false);    // rate-limit stop calls per burst
  const [linkEpoch, setLinkEpoch] = useState<number>(0);

  // Keep the control WS open: reconnect if it drops, close on unmount.
  // Without this, every command is silently lost after a single disconnect.
  useEffect(() => {
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    // The backend can have a plugin running that this page doesn't know about
    // (after a reload or reconnect). Plugin auto-stop on user input relies on it.
    const syncPluginState = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/plugins`);
        if (disposed || !res.ok) return;
        const data = await res.json();
        const running = (data?.running ?? []).length > 0;
        window.dispatchEvent(new CustomEvent(running ? "plugin:running" : "plugin:stopped"));
      } catch {
        // Backend unreachable: the next reconnect syncs again.
      }
    };

    const connect = () => {
      const socket = new WebSocket("ws://localhost:8000/ws");
      ws.current = socket;
      socket.onopen = () => {
        void syncPluginState();
        setLinkEpoch((n) => n + 1);  // re-read capabilities after a backend restart
      };
      socket.onclose = () => {
        if (disposed) return;
        console.warn("[Controls] WebSocket disconnected. Reconnecting...");
        retryTimer = setTimeout(connect, 1000);
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      ws.current?.close();
      ws.current = null;
    };
  }, []);

  // Listen for plugin start/stop events (dispatched from usePlugins and auto-stop)
  useEffect(() => {
    const onStart = () => { pluginRunningRef.current = true; };
    const onStop  = () => { pluginRunningRef.current = false; stoppedPluginOnceRef.current = false; };
    window.addEventListener('plugin:running', onStart as EventListener);
    window.addEventListener('plugin:stopped', onStop as EventListener);
    return () => {
      window.removeEventListener('plugin:running', onStart as EventListener);
      window.removeEventListener('plugin:stopped', onStop as EventListener);
    };
  }, []);

  /* ------- state that triggers re-renders ------- */
  const [axes,  setAxes]  = useState<Axes>(axesRef.current);
  const [mode,  setModeSt] = useState<ControlMode>("inc");
  const [gamepadConnected, setGamepadConnected] = useState<boolean>(false);
  const [droneType, setDroneType] = useState<string>("unknown");
  const [commandCapabilities, setCommandCapabilities] = useState<CommandCapabilities>({
    takeoff: true,
    land: true,
    estop: true,
    camera_tilt: false,
    camera_switch: false,
    speed_control: false,
    calibrate: false,
  });
  const [speedTier, setSpeedTierSt] = useState<SpeedTier>(2);
  const [cameraTiltDirection, setCameraTiltDirectionSt] = useState<CameraTiltDirection>(0);

  // Track previous gamepad status to avoid spam
  const prevGamepadStatus = useRef<boolean>(false);

  /* make setMode update both the ref (for hooks) and the state (for UI) */
  const setMode = useCallback((m: ControlMode) => {
    modeRef.current = m;
    setModeSt(m);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const fetchCapabilities = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/capabilities`);
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled) return;

        setDroneType(data?.drone_type ?? "unknown");
        setCommandCapabilities({
          takeoff: Boolean(data?.commands?.takeoff),
          land: Boolean(data?.commands?.land),
          estop: Boolean(data?.commands?.estop),
          camera_tilt: Boolean(data?.commands?.camera_tilt),
          camera_switch: Boolean(data?.commands?.camera_switch),
          speed_control: Boolean(data?.commands?.speed_control),
          calibrate: Boolean(data?.commands?.calibrate),
        });
      } catch {
        // Keep optimistic defaults when the backend is temporarily unavailable.
      }
    };

    fetchCapabilities();
    return () => {
      cancelled = true;
    };
  }, [linkEpoch]);

  /* --------------- gamepad detection --------------- */
  useEffect(() => {
    const checkGamepad = () => {
      const gamepads = navigator.getGamepads();
      const hasGamepad = Array.from(gamepads).some(gp => gp !== null && gp.connected);
      
      // Only log when status changes
      if (hasGamepad !== prevGamepadStatus.current) {
        console.log(`Gamepad ${hasGamepad ? 'connected' : 'disconnected'}`);
        if (hasGamepad) {
          const connectedGamepads = Array.from(gamepads).filter(gp => gp !== null);
          console.log('Connected gamepads:', connectedGamepads.map(gp => gp?.id));
        }
        prevGamepadStatus.current = hasGamepad;
      }
      
      setGamepadConnected(hasGamepad);
    };

    // Check initially
    checkGamepad();

    // Listen for gamepad connect/disconnect events
    const handleGamepadConnected = () => checkGamepad();
    const handleGamepadDisconnected = () => checkGamepad();

    window.addEventListener('gamepadconnected', handleGamepadConnected);
    window.addEventListener('gamepaddisconnected', handleGamepadDisconnected);

    // Also poll periodically since some browsers don't fire events reliably
    const pollInterval = setInterval(checkGamepad, 1000);

    return () => {
      window.removeEventListener('gamepadconnected', handleGamepadConnected);
      window.removeEventListener('gamepaddisconnected', handleGamepadDisconnected);
      clearInterval(pollInterval);
    };
  }, []);

  /* --------------- keyboard (incremental) --------------- */
  useEffect(() => {
    if (modeRef.current !== "inc") return;           // ignore when in abs mode

    const map: Record<string, { axis: keyof Axes; dir: -1 | 1 }> = {
      w:          { axis: "pitch",    dir: +1 },
      s:          { axis: "pitch",    dir: -1 },
      a:          { axis: "roll",     dir: -1 },
      d:          { axis: "roll",     dir: +1 },
      ArrowUp:    { axis: "throttle", dir: +1 },
      ArrowDown:  { axis: "throttle", dir: -1 },
      ArrowLeft:  { axis: "yaw",      dir: -1 },
      ArrowRight: { axis: "yaw",      dir: +1 },
    };

    // Caps Lock or Shift must not turn "w" into an unmapped "W".
    const keyFor = (e: KeyboardEvent) => (e.key.length === 1 ? e.key.toLowerCase() : e.key);

    const down = (e: KeyboardEvent) => {
      const m = map[keyFor(e)];
      if (!m) return;
      e.preventDefault();  // arrow keys must not scroll the page
      axesRef.current[m.axis] = m.dir;
      setAxes({ ...axesRef.current });
    };

    const up = (e: KeyboardEvent) => {
      const m = map[keyFor(e)];
      if (!m) return;
      if (axesRef.current[m.axis] === m.dir) {
        axesRef.current[m.axis] = 0;
        setAxes({ ...axesRef.current });
      }
    };

    // Switching windows hides the keyup, which would leave the drone moving.
    const releaseAll = () => {
      axesRef.current.throttle = 0;
      axesRef.current.yaw = 0;
      axesRef.current.pitch = 0;
      axesRef.current.roll = 0;
      setAxes({ ...axesRef.current });
    };

    window.addEventListener("keydown", down);
    window.addEventListener("keyup",   up);
    window.addEventListener("blur",    releaseAll);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup",   up);
      window.removeEventListener("blur",    releaseAll);
    };
  }, [mode]);      // re-run effect when mode flips

  /* --------------- camera tilt keyboard hold ---------------- */
  useEffect(() => {
    if (!commandCapabilities.camera_tilt) {
      cameraTiltDirectionRef.current = 0;
      setCameraTiltDirectionSt(0);
      return;
    }

    const map: Record<string, CameraTiltDirection> = {
      PageUp: 1,
      PageDown: -1,
    };

    const down = (e: KeyboardEvent) => {
      const direction = map[e.key];
      if (!direction) return;
      e.preventDefault();
      cameraTiltDirectionRef.current = direction;
      setCameraTiltDirectionSt(direction);
    };

    const up = (e: KeyboardEvent) => {
      const direction = map[e.key];
      if (!direction) return;
      e.preventDefault();
      if (cameraTiltDirectionRef.current === direction) {
        cameraTiltDirectionRef.current = 0;
        setCameraTiltDirectionSt(0);
      }
    };

    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [commandCapabilities.camera_tilt]);

  /* --------------- Xbox-360 game-pad (absolute) --------- */
  useEffect(() => {
    if (modeRef.current !== "abs") return;          // ignore when in inc mode

    const DEADZONE = 0.15; // Adjust this value as needed
    let raf = 0;

    const applyDeadzone = (value: number): number => {
      return Math.abs(value) < DEADZONE ? 0 : value;
    };

    const poll = () => {
      const gp = navigator.getGamepads()[0] as Gamepad | null;
      if (gp) {
        /* Xbox-360 / Chrome mapping -------------------------------------
           Left  stick: axes[0] (X)  axes[1] (Y)
           Right stick: axes[2] (X)  axes[3] (Y)
           Positive Y is *down*  → invert for throttle / pitch
        ------------------------------------------------------------------*/
        axesRef.current.roll     = applyDeadzone(gp.axes[0]);     // left X
        axesRef.current.pitch    = applyDeadzone(-gp.axes[1]);    // left Y  (forward == -1)
        axesRef.current.yaw      = applyDeadzone(gp.axes[2]);     // right X
        axesRef.current.throttle = applyDeadzone(-gp.axes[3]);    // right Y (up == +1)
        setAxes({ ...axesRef.current });
      }
      raf = requestAnimationFrame(poll);
    };
    raf = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(raf);
  }, [mode]);

  /* ---------- TrackPoint / Mouse (relative) ------------------ */
  useEffect(() => {
    if (modeRef.current !== "mouse") return;

    const sensitivity = 0.015;      // tune to taste for TrackPoint
    const decay       = 0.90;       // spring-back to centre when idle
    const axesState = axesRef.current;
    let rafId = 0;

    /* convert mouse deltas → roll / pitch  (-y = pitch forward) */
    const onMove = (e: MouseEvent) => {
      axesRef.current.roll  = Math.max(-1, Math.min(1, axesRef.current.roll  +  e.movementX * sensitivity));
      axesRef.current.pitch = Math.max(-1, Math.min(1, axesRef.current.pitch - e.movementY * sensitivity));
      setAxes({ ...axesRef.current });
    };

    /* gentle recentre so sticks don't stay deflected forever */
    const tick = () => {
      axesRef.current.roll  *= decay;
      axesRef.current.pitch *= decay;
      if (Math.abs(axesRef.current.roll)  < 0.001) axesRef.current.roll  = 0;
      if (Math.abs(axesRef.current.pitch) < 0.001) axesRef.current.pitch = 0;
      setAxes({ ...axesRef.current });
      rafId = requestAnimationFrame(tick);
    };

    /* when we lose pointer-lock (Esc, window blur, etc.) fall back to keyboard */
    const onLockChange = () => {
      if (document.pointerLockElement === null) {
        setMode("inc");
      }
    };

    window.addEventListener("mousemove",        onMove);
    document.addEventListener("pointerlockchange", onLockChange);
    rafId = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("pointerlockchange", onLockChange);
      cancelAnimationFrame(rafId);
      axesState.roll = 0;
      axesState.pitch = 0;
      setAxes((prev) => ({ ...prev, roll: 0, pitch: 0 }));
    };
  }, [mode, setMode]);

  /* ----------- network TX 30 Hz (treat mouse as "abs") ------- */
  useEffect(() => {
    const interval = setInterval(() => {
      if (ws.current?.readyState !== WebSocket.OPEN) return;

      // Also sent while a plugin runs: the backend gives the user priority over
      // the plugin only while these sticks are moved, and tilt works regardless.
      ws.current.send(JSON.stringify({
        type: "axes",
        mode: modeRef.current,
        camera_tilt_direction: cameraTiltDirectionRef.current,
        ...axesRef.current,
      }));
    }, 1000 / 30);
    return () => clearInterval(interval);
  }, []);

  /* ------------- helpers / commands ------------------------- */
  const sendCommand = (type: string, payload = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type, ...payload }));
    } else {
      console.warn("Cannot send command, WebSocket not open.");
    }
  };

  // Land and e-stop end a plugin's flight. Flight keys only pause it.
  const stopRunningPlugins = async () => {
    if (!pluginRunningRef.current || stoppedPluginOnceRef.current) return;
    try {
      // Stop all running plugins for simplicity
      const res = await fetch(`${API_BASE_URL}/plugins`);
      // If plugins are disabled on backend, nothing to stop.
      if (res.status === 404) return;
      if (!res.ok) return;
      const data = await res.json();
      const running: string[] = data?.running ?? [];
      await Promise.all(running.map((name) => fetch(`${API_BASE_URL}/plugins/${name}/stop`, { method: 'POST' })));
      stoppedPluginOnceRef.current = true;
      pluginRunningRef.current = false;
      // notify UI to flip OFF without polling
      window.dispatchEvent(new CustomEvent('plugin:stopped'));
    } catch {
      // Ignore errors when stopping plugins (fire-and-forget)
    }
  };

  // Send first so the command isn't delayed by stopping a running plugin.
  const flightCommand = (type: string) => {
    sendCommand(type);
    stopRunningPlugins();
  };
  const takeOff = () => sendCommand("takeoff");
  const land    = () => flightCommand("land");
  const emergencyStop = () => flightCommand("estop");
  const calibrate = () => sendCommand("calibrate");
  const setSpeedIndex = useCallback((speedIndex: number) => {
    sendCommand("set_speed_index", { speed_index: speedIndex });
  }, []);
  const setSpeedTier = useCallback((tier: SpeedTier) => {
    setSpeedTierSt(tier);
    setSpeedIndex(tier);
  }, [setSpeedIndex]);
  const setCameraTiltDirection = (direction: CameraTiltDirection) => {
    if (!commandCapabilities.camera_tilt) return;
    cameraTiltDirectionRef.current = direction;
    setCameraTiltDirectionSt(direction);
  };

  /* ------------- hook return ------------------------------- */
  return {
    axes,
    mode,
    setMode,
    gamepadConnected,
    droneType,
    commandCapabilities,
    takeOff,
    land,
    emergencyStop,
    calibrate,
    setSpeedIndex,
    speedTier,
    setSpeedTier,
    cameraTiltDirection,
    setCameraTiltDirection,
  };
}
