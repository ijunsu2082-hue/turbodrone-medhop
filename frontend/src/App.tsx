import { useEffect } from 'react';
import { useControls } from './hooks/useControls';
import { useStatus } from './hooks/useStatus';
import AxisIndicator from './components/AxisIndicator';
import CameraTiltControl from './components/CameraTiltControl';
import CommandButtons from './components/CommandButtons';
import { ControlSchemeToggle } from './components/ControlSchemeToggle';
import { DrawingOverlay } from './components/DrawingOverlay';
import { FollowBadge } from './components/FollowBadge';
import { FollowPanel } from './components/FollowPanel';
import { KeyHints } from './components/KeyHints';
import { NoVideo } from './components/NoVideo';
import { RecordButton, RecordingBadge } from './components/Recording';
import { Panel } from './components/Panel';
import SpeedControl from './components/SpeedControl';
import { TopBar } from './components/TopBar';
import { VideoFeed } from './components/VideoFeed';

function App() {
  const {
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
    speedTier,
    setSpeedTier,
    cameraTiltDirection,
    setCameraTiltDirection,
  } = useControls();
  const status = useStatus();
  const pluginRunning = status.plugins.length > 0;

  // Keep every hook in step with the backend, however a plugin was started or stopped.
  useEffect(() => {
    if (status.connected) {
      window.dispatchEvent(new CustomEvent(pluginRunning ? 'plugin:running' : 'plugin:stopped'));
    }
  }, [status.connected, pluginRunning]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-y-auto bg-[#0b0d10] text-gray-200 lg:overflow-hidden">
      <TopBar droneType={droneType} status={status} />

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="flex min-h-[60vh] min-w-0 flex-1 flex-col lg:min-h-0">
          <div className="relative min-h-0 flex-1 bg-black">
            <VideoFeed src="http://localhost:8000/mjpeg" live={status.videoLive} />
            <DrawingOverlay />
            {!status.videoLive && <NoVideo backendConnected={status.connected} />}
            {status.videoLive && status.follow && <FollowBadge status={status.follow} />}
            {status.recording.active && <RecordingBadge seconds={status.recording.seconds} />}
          </div>
          <KeyHints axes={axes} tilt={cameraTiltDirection} />
        </main>

        <aside className="flex w-full shrink-0 flex-col gap-2.5 border-white/10 p-2.5 lg:w-80 lg:overflow-y-auto lg:border-l">
          <FollowPanel status={status.follow} />

          <CommandButtons
            capabilities={commandCapabilities}
            following={pluginRunning}
            onTakeoff={takeOff}
            onLand={land}
            onEstop={emergencyStop}
            onCalibrate={calibrate}
          />

          {commandCapabilities.speed_control && (
            <Panel title="Manual speed">
              <SpeedControl value={speedTier} onChange={setSpeedTier} />
            </Panel>
          )}

          <Panel title="Camera">
            <div className="flex flex-col gap-2">
              <RecordButton recording={status.recording} videoLive={status.videoLive} />
              {commandCapabilities.camera_tilt && (
                <CameraTiltControl activeDirection={cameraTiltDirection} onTiltChange={setCameraTiltDirection} />
              )}
            </div>
          </Panel>

          <Panel title="Sticks">
            <div className="flex justify-around">
              <AxisIndicator x={axes.roll} y={axes.pitch} label="Move" />
              <AxisIndicator x={axes.yaw} y={axes.throttle} label="Turn / height" />
            </div>
            <div className="mt-2.5">
              <ControlSchemeToggle mode={mode} setMode={setMode} gamepadConnected={gamepadConnected} />
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

export default App;
