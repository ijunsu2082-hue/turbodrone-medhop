import os
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from services.video_recorder import PageRecording, RecordingError, VideoRecorder


def jpeg(size=(320, 180), shade=120):
    ok, data = cv2.imencode(".jpg", np.full((size[1], size[0], 3), shade, np.uint8))
    assert ok
    return data.tobytes()


def frame_count(path):
    capture = cv2.VideoCapture(path)
    count = 0
    while capture.read()[0]:
        count += 1
    capture.release()
    return count


class VideoRecorderTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.recorder = VideoRecorder(self.dir.name)
        self.addCleanup(self.recorder.stop_if_active)

    def test_saves_a_playable_file_at_real_speed_from_uneven_frames(self):
        self.recorder.start()
        for t in (10.0, 10.05, 10.4, 10.45, 11.0, 11.3, 12.0):
            self.recorder.add_frame(jpeg(), timestamp=t)
        path = self.recorder.stop()

        self.assertTrue(path.endswith(".mp4"))
        self.assertTrue(os.path.getsize(path) > 0)
        self.assertEqual(frame_count(path), 2 * VideoRecorder.FPS + 1)

    def test_no_video_means_no_file(self):
        self.recorder.start()
        self.assertIsNone(self.recorder.stop())
        self.assertEqual(os.listdir(self.dir.name), [])

    def test_long_dropout_is_cut(self):
        self.recorder.start()
        self.recorder.add_frame(jpeg(), timestamp=0.0)
        self.recorder.add_frame(jpeg(), timestamp=1.0)
        self.recorder.add_frame(jpeg(), timestamp=600.0)
        path = self.recorder.stop()
        self.assertEqual(frame_count(path), VideoRecorder.FPS + 2)

    def test_frame_size_change_does_not_break_the_file(self):
        self.recorder.start()
        self.recorder.add_frame(jpeg((320, 180)), timestamp=0.0)
        self.recorder.add_frame(jpeg((640, 360)), timestamp=0.5)
        path = self.recorder.stop()
        self.assertGreater(frame_count(path), 0)

    def test_corrupt_frame_is_skipped(self):
        self.recorder.start()
        self.recorder.add_frame(b"not a jpeg", timestamp=0.0)
        self.recorder.add_frame(jpeg(), timestamp=0.1)
        self.assertIsNotNone(self.recorder.stop())

    def test_frames_are_ignored_when_not_recording(self):
        self.recorder.add_frame(jpeg())
        self.assertFalse(self.recorder.active)

    def test_cannot_start_twice_or_stop_twice(self):
        self.recorder.start()
        with self.assertRaises(RecordingError):
            self.recorder.start()
        self.recorder.stop()
        with self.assertRaises(RecordingError):
            self.recorder.stop()

    def test_quick_recordings_get_distinct_paths(self):
        paths = []
        for _ in range(2):
            self.recorder.start()
            self.recorder.add_frame(jpeg(), timestamp=0.0)
            paths.append(self.recorder.stop())
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(os.path.exists(path) for path in paths))

    def test_each_recording_gets_finished_on_shutdown(self):
        self.recorder.start()
        self.recorder.add_frame(jpeg(), timestamp=0.0)
        self.recorder.stop_if_active()
        self.assertFalse(self.recorder.active)
        self.assertEqual(len(os.listdir(self.dir.name)), 1)


class PageRecordingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.page = PageRecording(self.dir)

    def test_pieces_are_saved_in_order(self):
        self.page.start("mp4")
        self.page.append(b"one")
        self.page.append(b"two")
        path = self.page.stop()
        self.assertTrue(path.endswith("-page.mp4"))
        with open(path, "rb") as saved:
            self.assertEqual(saved.read(), b"onetwo")

    def test_quick_page_recordings_get_distinct_paths(self):
        paths = []
        for _ in range(2):
            self.page.start("webm")
            self.page.append(b"clip")
            paths.append(self.page.stop())
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(os.path.exists(path) for path in paths))

    def test_nothing_recorded_leaves_no_file(self):
        self.page.start("webm")
        self.assertIsNone(self.page.stop())
        self.assertEqual(os.listdir(self.dir), [])

    def test_only_video_extensions_are_allowed(self):
        for extension in ("exe", "mp4/../../x", ""):
            with self.assertRaises(RecordingError):
                self.page.start(extension)

    def test_piece_without_a_recording_is_refused(self):
        with self.assertRaises(RecordingError):
            self.page.append(b"data")

    def test_stop_without_a_recording_is_harmless(self):
        self.assertIsNone(self.page.stop())


if __name__ == "__main__":
    unittest.main()
