import threading
import cv2
import numpy as np
from ultralytics import YOLO
import time
import os
import logging

from ..base import Plugin
from .box_smoother import BoxSmoother
from .follow_controller import FollowController
from .target_tracker import HOLDING, LOST, SEARCHING, TRACKING, Detection, TargetTracker
from control.strategies import DirectStrategy

logger = logging.getLogger(__name__)


class FollowPlugin(Plugin):
    """
    Person-following plugin using YOLO for detection.
    Detects people in video frames and sends yaw/pitch commands to keep them centered.
    """

    # A person filling the frame is found at this size and missed at higher ones.
    CLOSE_RANGE_IMG_SIZE = 160
    # Average frame brightness (0-255) below which tracking and position hold suffer.
    DARK_BRIGHTNESS = 45.0
    # How quickly a follow command may strengthen, in stick percent per second.
    COMMAND_RISE_PER_S = 100.0
    # Each decision without a detection, keep this share of the last command.
    HOLD_DECAY = 0.6

    def _on_start(self):
        # ---- Thread caps for better CPU behavior ----
        try:
            import torch
            torch.set_num_threads(int(os.getenv("TORCH_NUM_THREADS", "2")))
            torch.set_num_interop_threads(1)
        except Exception:
            pass

        try:
            cv2.setNumThreads(1)
        except Exception:
            pass

        os.environ.setdefault("OMP_NUM_THREADS", "2")
        os.environ.setdefault("MKL_NUM_THREADS", "2")

        # ---- Configuration ----
        self.frame_rate = int(os.getenv("FOLLOW_FPS", "20"))
        self.img_size = int(os.getenv("YOLO_IMG_SIZE", "320"))
        self.log_interval = float(os.getenv("FOLLOW_LOG_INTERVAL", "2.0"))
        self.command_timeout = float(os.getenv("FOLLOW_COMMAND_TIMEOUT", "1.0"))

        # ---- Load YOLO model ----
        weights_env = os.getenv("YOLO_WEIGHTS")
        if weights_env and os.path.exists(weights_env):
            weights_path = weights_env
        else:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            default_weights = os.path.join(repo_root, "yolov10n.pt")
            weights_path = default_weights if os.path.exists(default_weights) else "yolov10n.pt"

        self.model = YOLO(weights_path)

        # ---- Follow controller ----
        self.ctrl = FollowController(
            yaw_deadzone=float(os.getenv("FOLLOW_CENTER_DEADZONE", "0.12")),
            pitch_deadzone=float(os.getenv("FOLLOW_PITCH_DEADZONE", "0.02")),
            min_box_width=float(os.getenv("FOLLOW_MIN_BOX_WIDTH", "0.30")),
            max_box_width=float(os.getenv("FOLLOW_MAX_BOX_WIDTH", "0.80")),
            invert_yaw=os.getenv("FOLLOW_INVERT_YAW", "false").lower() in ("1", "true", "yes"),
            invert_pitch=os.getenv("FOLLOW_INVERT_PITCH", "false").lower() in ("1", "true", "yes"),
            yaw_speed=float(os.getenv("FOLLOW_YAW_SPEED", "10.0")),
            pitch_speed=float(os.getenv("FOLLOW_PITCH_SPEED", "15.0")),
            yaw_max_speed=float(os.getenv("FOLLOW_YAW_MAX_SPEED", "30.0")),
            pitch_max_speed=float(os.getenv("FOLLOW_PITCH_MAX_SPEED", "30.0")),
            search_yaw_speed=float(os.getenv("FOLLOW_SEARCH_YAW_SPEED", "15.0")),
            backoff_speed=float(os.getenv("FOLLOW_BACKOFF_SPEED", "20.0")),
        )

        self.smoother = BoxSmoother()

        # ---- Who to follow ----
        self.tracker = TargetTracker(
            acquire_confidence=float(os.getenv("YOLO_CONFIDENCE", "0.35")),
            keep_confidence=float(os.getenv("FOLLOW_KEEP_CONFIDENCE", "0.15")),
            hold_s=float(os.getenv("FOLLOW_HOLD_SECONDS", "0.5")),
            search_s=float(os.getenv("FOLLOW_SEARCH_SECONDS", "2.5")),
        )
        self._detect_failed_logged = False

        # ---- Set DirectStrategy for follow control ----
        self._prev_strategy = getattr(self.fc.model, "strategy", None)
        self._prev_expo = getattr(self.fc.model, "expo_factor", None)

        try:
            self.fc.model.set_strategy(DirectStrategy())
            self.fc.model.expo_factor = 0.0
            logger.info("[FollowPlugin] Started with DirectStrategy, expo=0")
        except Exception as e:
            logger.warning("[FollowPlugin] Warning: %s", e)

        self._steering = False
        self._last_steer_time = time.monotonic()
        self._last_frame_time = time.monotonic()
        self.status = {"state": "starting", "paused": False}

        self.loop_thread = threading.Thread(target=self._loop, daemon=True)
        self.loop_thread.start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _on_stop(self):
        # Hover right away. Nothing else clears these sticks if the page is gone.
        self._hover("follow-stop")

        # Restore previous strategy
        try:
            if self._prev_strategy is not None:
                self.fc.model.set_strategy(self._prev_strategy)
            if self._prev_expo is not None:
                self.fc.model.expo_factor = self._prev_expo
        except Exception:
            pass

        if self.loop_thread:
            self.loop_thread.join(timeout=1.0)

        # In case the loop was mid-decision when the first hover went out.
        self._hover("follow-stop")

    def _steer(self, yaw: float, pitch: float) -> None:
        """Send a follow command, unless the user is flying by hand right now."""
        self._last_steer_time = time.monotonic()
        self._steering = yaw != 0 or pitch != 0
        if self.fc.manual_override_active():
            return

        model = self.fc.model
        if not isinstance(getattr(model, "strategy", None), DirectStrategy):
            model.set_strategy(DirectStrategy())
            model.expo_factor = 0.0

        # The follow speeds are real stick amounts, whatever speed tier the user
        # picked for manual flying. Undo the scale the drone adapter will apply.
        scale = getattr(model, "speed_scale", 1.0)
        self.fc.set_axes_from(
            "follow",
            throttle=0,
            yaw=max(-1.0, min(1.0, yaw / scale)),
            pitch=max(-1.0, min(1.0, pitch / scale)),
            roll=0,
        )

    def _hover(self, source: str) -> None:
        self._steering = False
        self.fc.set_axes_from(source, throttle=0, yaw=0, pitch=0, roll=0)

    def _watchdog(self) -> None:
        """Hover when decisions stop arriving, such as frozen video or a failed detection."""
        while self.running:
            time.sleep(0.1)
            now = time.monotonic()
            if self._steering and now - self._last_steer_time > self.command_timeout:
                logger.warning("[FollowPlugin] No fresh video decision for %.1fs; hovering", self.command_timeout)
                self._hover("follow-timeout")
            if now - self._last_frame_time > self.command_timeout and self.status.get("state") != "no_video":
                self.status = {"state": "no_video", "paused": self.fc.manual_override_active()}

    def _detect_at(self, img: np.ndarray, img_size: int) -> list[Detection]:
        frame_h, frame_w = img.shape[:2]
        detections = []
        results = self.model(
            img,
            stream=True,
            verbose=False,
            classes=[0],  # person class only
            imgsz=img_size,
            conf=self.tracker.keep_confidence,
        )
        for r in results:
            for box in r.boxes or []:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    Detection((x1 / frame_w, y1 / frame_h, x2 / frame_w, y2 / frame_h), float(box.conf[0]))
                )
        return detections

    def _detect(self, img: np.ndarray) -> list[Detection]:
        try:
            return self._detect_at(img, self.img_size) or self._detect_at(img, self.CLOSE_RANGE_IMG_SIZE)
        except Exception as e:
            if not self._detect_failed_logged:
                self._detect_failed_logged = True
                logger.exception("[FollowPlugin] Detection failed: %s", e)
            return []

    def _command_for(self, result, last_command: tuple[float, float]) -> tuple[float, float]:
        if result.state == TRACKING:
            center_x, width = self.smoother.update(result.target.box, time.monotonic())
            return self.ctrl.compute(center_x, width)
        if result.state == HOLDING:
            # Not seeing them right now, so don't keep turning at full strength.
            return last_command[0] * self.HOLD_DECAY, last_command[1] * self.HOLD_DECAY
        self.smoother.reset()
        self.ctrl.reset()
        if result.state == SEARCHING:
            return self.ctrl.recover(result.target.center_x, result.target.width, result.lost_for)
        return 0.0, 0.0

    def _loop(self):
        logger.info("[FollowPlugin] Loop started. Waiting for frames...")
        frame_interval = 1.0 / self.frame_rate
        last_frame_time = 0
        last_log_time = time.time()
        last_command = (0.0, 0.0)
        last_decision_time = time.time()
        window_frames = 0
        window_seen = 0
        fps = 0.0
        detection_rate = 0.0

        for frame in self.frames:
            # Rate limit
            now = time.time()
            if now - last_frame_time < frame_interval:
                continue
            last_frame_time = now

            if not self.running:
                break

            # Decode frame
            if hasattr(frame, "format") and frame.format == "jpeg":
                img = cv2.imdecode(np.frombuffer(frame.data, np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
            elif isinstance(frame, np.ndarray):
                img = frame
            else:
                continue

            self._last_frame_time = time.monotonic()
            detections = self._detect(img)

            # Stopped while detecting: don't send a command after the final hover.
            if not self.running:
                break

            result = self.tracker.update(detections, time.monotonic())
            yaw, pitch = self._command_for(result, last_command)
            max_change = self.COMMAND_RISE_PER_S * min(0.25, now - last_decision_time)
            last_decision_time = now
            yaw = self.ctrl.limit_rise(last_command[0], yaw, max_change)
            pitch = self.ctrl.limit_rise(last_command[1], pitch, max_change)
            last_command = (yaw, pitch)
            self._steer(yaw / 100.0, pitch / 100.0)

            # Show the person, or where they were last seen
            if result.target is not None and result.state != LOST:
                color = "lime" if result.state == TRACKING else "#facc15"
                self.send_overlay([{"type": "rect", "coords": list(result.target.box), "color": color}])
            else:
                self.send_overlay([])

            window_frames += 1
            window_seen += result.state == TRACKING
            elapsed = now - last_log_time
            if elapsed >= self.log_interval:
                fps = window_frames / elapsed
                detection_rate = 100.0 * window_seen / window_frames

            target = result.target
            brightness = float(img[::8, ::8].mean())
            self.status = {
                "state": result.state,
                "paused": self.fc.manual_override_active(),
                "fps": round(fps, 1),
                "detection_rate": round(detection_rate),
                "confidence": round(target.confidence, 2) if target else None,
                "offset": round((target.center_x - 0.5) * 100, 1) if target else None,
                "box": round(target.width * 100, 1) if target else None,
                "yaw": round(yaw, 1),
                "pitch": round(pitch, 1),
                "dark": brightness < self.DARK_BRIGHTNESS,
            }

            # Periodic logging
            if elapsed >= self.log_interval:
                logger.info(
                    "[FollowPlugin] %s %.1ffps seen=%.0f%% conf=%s offset=%s%% box=%s%% yaw=%.0f pitch=%.0f brightness=%.0f paused=%s",
                    result.state,
                    fps,
                    detection_rate,
                    self.status["confidence"],
                    self.status["offset"],
                    self.status["box"],
                    yaw,
                    pitch,
                    brightness,
                    self.status["paused"],
                )
                last_log_time = now
                window_frames = 0
                window_seen = 0
