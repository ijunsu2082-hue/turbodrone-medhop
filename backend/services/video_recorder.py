"""Save the drone's video to a file on this computer."""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Optional

import cv2
import numpy as np

from utils.dropping_queue import DroppingQueue

logger = logging.getLogger(__name__)


def _reserve_unique_path(directory: str, prefix: str, suffix: str) -> str:
    """Create a unique empty file path without overwriting an earlier recording."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for attempt in range(100):
        path = os.path.join(directory, f"{prefix}-{stamp}-{time.time_ns()}-{attempt}{suffix}")
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        return path
    raise OSError("Could not reserve a unique recording filename")


class RecordingError(Exception):
    """Recording can't start or stop right now."""


class VideoRecorder:
    """
    Writes incoming JPEG frames to an MP4 from a background thread.

    Drone video arrives at an uneven rate, so frames are placed by their arrival
    time in a constant-rate file. That keeps playback at real speed.
    """

    FPS = 15
    CODECS = ("avc1", "mp4v")  # H.264 first; it plays everywhere on a Mac
    MAX_GAP_S = 5.0            # Longer video dropouts are cut from the recording

    def __init__(self, directory: Optional[str] = None) -> None:
        self.directory = os.path.expanduser(directory or os.getenv("RECORDINGS_DIR", "~/Movies/Turbodrone"))
        self._lock = threading.Lock()
        self._queue: Optional[queue.Queue] = None
        self._thread: Optional[threading.Thread] = None
        self._path: Optional[str] = None
        self._started_at = 0.0
        self._frames_written = 0
        self._failed = False

    @property
    def active(self) -> bool:
        return self._queue is not None

    @property
    def seconds(self) -> float:
        return time.monotonic() - self._started_at if self.active else 0.0

    def start(self) -> None:
        with self._lock:
            if self.active:
                raise RecordingError("Already recording")
            try:
                os.makedirs(self.directory, exist_ok=True)
            except OSError as e:
                raise RecordingError(f"Can't create {self.directory}: {e}") from e

            self._path = _reserve_unique_path(self.directory, "turbodrone", ".mp4")
            self._frames_written = 0
            self._failed = False
            self._started_at = time.monotonic()
            frames: queue.Queue = DroppingQueue(maxsize=120)
            self._thread = threading.Thread(target=self._write_frames, args=(frames, self._path), daemon=True)
            self._thread.start()
            self._queue = frames
            logger.info("[Recorder] Recording to %s", self._path)

    def add_frame(self, jpeg: bytes, timestamp: Optional[float] = None) -> None:
        frames = self._queue
        if frames is not None:
            frames.put((time.monotonic() if timestamp is None else timestamp, jpeg))

    def stop(self) -> Optional[str]:
        """Finish the file and return its path, or None if no video was recorded."""
        with self._lock:
            frames = self._queue
            if frames is None:
                raise RecordingError("Not recording")
            self._queue = None
            frames.put(None)
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                raise RecordingError("Timed out finishing the recording")

            if self._failed:
                raise RecordingError("This computer couldn't write the video file")
            if self._frames_written == 0:
                logger.info("[Recorder] Stopped; no video arrived")
                if self._path and os.path.exists(self._path):
                    os.remove(self._path)
                return None
            logger.info("[Recorder] Saved %s (%.1fs)", self._path, self._frames_written / self.FPS)
            return self._path

    def stop_if_active(self) -> None:
        """Finish the file on shutdown. An unfinished MP4 can't be played."""
        if self.active:
            try:
                self.stop()
            except RecordingError as e:
                logger.warning("[Recorder] %s", e)

    def _open_writer(self, path: str, width: int, height: int) -> Optional[cv2.VideoWriter]:
        for codec in self.CODECS:
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*codec), self.FPS, (width, height))
            if writer.isOpened():
                return writer
            writer.release()
        return None

    def _write_frames(self, frames: queue.Queue, path: str) -> None:
        writer = None
        size = (0, 0)
        anchor = 0.0
        written = 0

        while True:
            item = frames.get()
            if item is None:
                break
            if self._failed:
                continue

            timestamp, jpeg = item
            image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue

            if writer is None:
                size = (image.shape[1], image.shape[0])
                writer = self._open_writer(path, *size)
                if writer is None:
                    logger.error("[Recorder] Couldn't open %s for writing", path)
                    self._failed = True
                    continue
                anchor = timestamp
            elif (image.shape[1], image.shape[0]) != size:
                image = cv2.resize(image, size)

            due = int((timestamp - anchor) * self.FPS) + 1
            if due - written > self.MAX_GAP_S * self.FPS:
                anchor = timestamp - written / self.FPS
                due = written + 1
            while written < due:
                writer.write(image)
                written += 1
            self._frames_written = written

        if writer is not None:
            writer.release()


class PageRecording:
    """Saves the recording of the web page that the browser streams to us in pieces."""

    EXTENSIONS = ("mp4", "webm")
    MAX_BYTES = 8 * 1024 * 1024 * 1024

    def __init__(self, directory: Optional[str] = None) -> None:
        self.directory = os.path.expanduser(directory or os.getenv("RECORDINGS_DIR", "~/Movies/Turbodrone"))
        self._lock = threading.Lock()
        self._file = None
        self._path: Optional[str] = None
        self._size = 0

    def start(self, extension: str) -> None:
        if extension not in self.EXTENSIONS:
            raise RecordingError(f"Can't save a page recording as .{extension}")
        with self._lock:
            if self._file is not None:
                raise RecordingError("Already recording the page")
            try:
                os.makedirs(self.directory, exist_ok=True)
                path = _reserve_unique_path(self.directory, "turbodrone-page", f".{extension}")
                self._file = open(path, "wb")
            except OSError as e:
                raise RecordingError(f"Can't create the page recording: {e}") from e
            self._path = path
            self._size = 0
            logger.info("[Recorder] Recording the page to %s", path)

    def append(self, data: bytes) -> None:
        with self._lock:
            if self._file is None:
                raise RecordingError("Not recording the page")
            if self._size + len(data) > self.MAX_BYTES:
                raise RecordingError("The page recording is too large")
            try:
                self._file.write(data)
            except OSError as e:
                raise RecordingError(f"Can't save the page recording: {e}") from e
            self._size += len(data)

    def stop(self) -> Optional[str]:
        """Close the file. Returns its path, or None if nothing was recorded."""
        with self._lock:
            if self._file is None:
                return None
            path, size = self._path, self._size
            self._file.close()
            self._file = None
            self._path = None
        if size == 0:
            os.remove(path)
            return None
        logger.info("[Recorder] Saved the page recording %s (%.1f MB)", path, size / 1e6)
        return path
