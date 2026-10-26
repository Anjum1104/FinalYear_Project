import json
import os
import sys
import tempfile
import threading
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

dlib_stub = types.ModuleType("dlib")


def _fake_detector(*args):
    del args
    return []


def _fake_shape_predictor(model_path):
    del model_path
    return None


dlib_stub.get_frontal_face_detector = lambda: _fake_detector
dlib_stub.shape_predictor = _fake_shape_predictor
sys.modules["dlib"] = dlib_stub

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QImage

from main import DetectionWorker, MainApp
from perclos_calculation import PERCLOSCalculator
import wideScreen
from wideScreen import HMIWindow


class DriverGuardSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance()
        if cls.application is None:
            cls.application = QtWidgets.QApplication([])

    def setUp(self):
        self.window = HMIWindow()
        self.window.drive_simulation.animation_timer.stop()
        self.window.clock_timer.stop()
        self.window.set_sound_enabled(False)

    def tearDown(self):
        self.window.sound_timer.stop()
        self.window.drive_simulation.animation_timer.stop()
        self.window.clock_timer.stop()
        self.window.close()

    def update_window(self, **overrides):
        values = {
            "ear": 0.3,
            "perclos": 0.0,
            "head_angle": 0.0,
            "head_pitch": 0.0,
            "head_yaw": 0.0,
            "head_roll": 0.0,
            "blink_rate": 15.0,
            "mouth_aperture": 0.1,
            "yawn_count": 0,
            "closed_duration": 0.0,
            "tracking_reliable": True,
            "calibrated": True,
            "calibrating": False,
            "drowsiness_level": "None",
        }
        values.update(overrides)
        self.window.update_detection(**values)

    def test_tracking_loss_clears_eye_timer_and_alert(self):
        calculator = PERCLOSCalculator()
        calculator.closed_since = 10.0
        calculator.closed_candidate_frames = 4
        calculator.eye_closed_buffer.append((10.0, True))

        metrics = calculator.reset_for_tracking_loss(
            "Face not found: center your face."
        )

        self.assertFalse(metrics.tracking_reliable)
        self.assertFalse(metrics.eye_closed)
        self.assertEqual(metrics.closed_duration, 0.0)
        self.assertIsNone(calculator.closed_since)
        self.assertEqual(calculator.closed_candidate_frames, 0)
        self.assertEqual(len(calculator.eye_closed_buffer), 0)

        self.update_window(drowsiness_level="Level 1")
        self.assertTrue(self.window.sound_timer.isActive())
        self.update_window(
            ear=None,
            perclos=None,
            head_angle=None,
            head_pitch=None,
            head_yaw=None,
            head_roll=None,
            mouth_aperture=None,
            tracking_reliable=False,
            calibrated=False,
            drowsiness_level="Tracking uncertain",
        )
        self.assertFalse(self.window.sound_timer.isActive())
        self.assertIsNone(self.window.unresponsive_since)
        self.assertEqual(self.window.eye_closure_label.text(), "--")
        self.assertEqual(self.window.level_label.text(), "TRACKING UNCERTAIN")

    def test_calibrated_eye_threshold_stays_below_open_eye_baseline(self):
        calculator = PERCLOSCalculator()
        calculator.eye_baseline = 0.30
        calculator.set_sensitivity(1.5)

        threshold = calculator.get_eye_closure_threshold()

        self.assertAlmostEqual(threshold, 0.24)
        self.assertLess(threshold, calculator.eye_baseline)

    def test_perclos_waits_for_a_nearly_complete_15_second_window(self):
        calculator = PERCLOSCalculator(time_period=15)
        calculator.eye_closed_buffer.extend(
            [(100.0, True), (100.5, True), (101.0, False), (101.5, False)]
        )

        self.assertIsNone(calculator._calculate_perclos(102.0))

        for sample_time in range(102, 116):
            calculator.eye_closed_buffer.append((float(sample_time), False))
        self.assertAlmostEqual(
            calculator._calculate_perclos(115.0),
            100.0 * 2 / len(calculator.eye_closed_buffer),
        )

    def test_calibration_progress_and_result_report_sample_counts(self):
        worker = DetectionWorker()
        worker.perclos_calculator = SimpleNamespace(
            calibration_samples=[0.2] * 17,
            pose_calibration_samples=[(0.0, 0.0, 0.0)] * 6,
            sensitivity=1.0,
        )
        progress_message = worker._calibration_progress_message(
            "Keep your comfortable posture."
        )
        self.assertIn("eyes 17/45", progress_message)
        self.assertIn("posture 6/20", progress_message)

        completion = []
        worker.calibration_finished.connect(
            lambda message, success: completion.append((message, success))
        )
        worker.calibration_in_progress = True
        worker._update_calibration_feedback(
            SimpleNamespace(
                calibrating=False,
                calibrated=False,
                pose_calibrated=False,
                eye_baseline=None,
                eye_closure_threshold=None,
            )
        )
        self.assertEqual(len(completion), 1)
        self.assertFalse(completion[0][1])
        self.assertIn("eyes 17/45", completion[0][0])
        self.assertIn("posture 6/20", completion[0][0])
        self.assertIn("retry", completion[0][0])

    def test_acknowledgement_restarts_unresponsive_timer(self):
        with patch.object(self.window, "_clock_now", return_value=100.0):
            self.window.update_alert_state("Level 1", False)
        self.assertEqual(self.window.unresponsive_since, 100.0)

        with patch.object(self.window, "_clock_now", return_value=125.0):
            self.window.note_driver_response()

        self.assertEqual(self.window.unresponsive_since, 125.0)
        self.assertEqual(self.window.response_label.text(), "Response received")

    def test_accessibility_settings_scale_colors_and_keep_keyboard_focus(self):
        self.update_window()
        self.window.open_settings()
        dialog = self.window.findChild(QtWidgets.QDialog)
        text_size = dialog.findChild(QtWidgets.QComboBox)
        high_contrast = dialog.findChild(QtWidgets.QCheckBox)
        text_size.setCurrentIndex(2)
        high_contrast.setChecked(True)
        high_contrast_style = self.window.level_label.styleSheet()
        self.assertIn("font-size:23px", high_contrast_style)
        self.assertIn("color:#ffffff", high_contrast_style)

        high_contrast.setChecked(False)
        text_size.setCurrentIndex(1)
        standard_contrast_style = self.window.level_label.styleSheet()
        self.assertIn("font-size:21px", standard_contrast_style)
        self.assertIn("color:#57d998", standard_contrast_style)
        self.assertEqual(
            self.window.camera_start_button.focusPolicy(),
            QtCore.Qt.StrongFocus,
        )

    def test_privacy_controls_hide_preview_and_clear_in_memory_history(self):
        self.window.open_settings()
        dialog = self.window.findChild(QtWidgets.QDialog)
        preview_checkbox = next(
            checkbox
            for checkbox in dialog.findChildren(QtWidgets.QCheckBox)
            if checkbox.text() == "Hide live camera preview"
        )
        clear_button = next(
            button
            for button in dialog.findChildren(QtWidgets.QPushButton)
            if button.text() == "Clear session history"
        )

        self.window.camera_state_changed(True)
        image = QImage(8, 8, QImage.Format_RGB32)
        self.window.update_map_frame(image)
        self.assertIsNotNone(self.window.latest_camera_image)

        preview_checkbox.setChecked(True)
        self.assertIsNone(self.window.latest_camera_image)
        self.assertIn("Local analysis is still active", self.window.camera_label.text())
        self.window.update_map_frame(image)
        self.assertIsNone(self.window.latest_camera_image)

        preview_checkbox.setChecked(False)
        self.window.update_map_frame(image)
        self.assertIsNotNone(self.window.latest_camera_image)

        self.window.add_event("Drowsiness warning escalated to Level 1")
        self.window.simulation_count = 2
        self.window.live_tracking_samples = 4
        self.window.reliable_tracking_samples = 3
        self.window.completed_tracking_check = {"frames": 4}
        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.Yes,
        ):
            clear_button.click()
        self.assertEqual(self.window.event_list.count(), 0)
        self.assertEqual(self.window.event_history, [])
        self.assertEqual(self.window.warning_count, 0)
        self.assertEqual(self.window.simulation_count, 0)
        self.assertEqual(self.window.live_tracking_samples, 0)
        self.assertIsNone(self.window.completed_tracking_check)
        self.assertEqual(
            self.window.session_stats_label.text(),
            "Session: 0 warnings · 0 simulated stops",
        )

    def test_guided_tracking_check_reports_eye_and_pose_coverage_by_stage(self):
        self.window.camera_active = True
        self.window.TRACKING_CHECK_STAGE_SECONDS = 2.0
        self.assertFalse(self.window.camera_paused)
        self.assertFalse(self.window.mock_test_active)
        self.window.open_tracking_check()
        self.assertIsNotNone(self.window.tracking_check_started_at)
        self.update_window()
        self.assertIsNotNone(self.window.tracking_check_started_at)
        self.window.tracking_check_started_at -= 2.1
        self.update_window(
            ear=None,
            head_pitch=None,
            head_yaw=None,
            head_roll=None,
            tracking_reliable=False,
        )

        self.assertEqual(self.window.tracking_check_samples[0]["tracked"], 1)
        self.assertEqual(self.window.tracking_check_samples[0]["pose"], 1)
        self.assertEqual(self.window.tracking_check_samples[1]["tracked"], 0)
        self.window._finish_tracking_check()

        report = self.window.tracking_check_report.text()
        self.assertIn("Overall face/eye tracking observed: 50%", report)
        self.assertIn("your usual comfortable posture", report)
        self.assertIn("Face/eyes 0% · pose landmarks 0%", report)
        self.assertFalse(self.window.tracking_check_timer.isActive())

    def test_session_summary_exports_user_selected_json_without_camera_data(self):
        self.window.camera_active = True
        self.update_window()
        self.update_window(
            ear=None,
            perclos=None,
            head_angle=None,
            head_pitch=None,
            head_yaw=None,
            head_roll=None,
            tracking_reliable=False,
            calibrated=False,
        )
        self.window.add_event("Drowsiness warning threshold reached")
        self.window.simulation_count = 1
        summary = self.window.build_session_summary()

        self.assertEqual(summary["summary"]["warnings"], 1)
        self.assertEqual(summary["live_tracking"]["samples"], 2)
        self.assertEqual(
            summary["live_tracking"]["face_eye_coverage_percent"], 50.0
        )
        self.window.open_session_summary()
        dialog = self.window.findChild(QtWidgets.QDialog)
        export_button = next(
            button
            for button in dialog.findChildren(QtWidgets.QPushButton)
            if button.text().startswith("Export summary as JSON")
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            export_path = os.path.join(
                temp_directory, "driverguard-summary.json"
            )
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(export_path, "JSON files (*.json)"),
            ):
                export_button.click()
            with open(export_path, encoding="utf-8") as exported_file:
                exported = json.load(exported_file)

        self.assertEqual(exported["summary"]["simulated_stops"], 1)
        self.assertEqual(len(exported["events"]), 1)
        self.assertFalse(
            exported["privacy"]["contains_camera_images_or_video"]
        )
        self.assertFalse(
            exported["privacy"]["contains_raw_facial_measurements"]
        )
        self.assertNotIn("ear", exported)

    def test_session_event_history_keeps_latest_bounded_records(self):
        self.window.MAX_SESSION_EVENTS = 2
        self.window.add_event("First event")
        self.window.add_event("Second event")
        self.window.add_event("Third event")

        summary = self.window.build_session_summary()
        self.assertTrue(summary["event_history_truncated"])
        self.assertEqual(
            [event["message"] for event in summary["events"]],
            ["Second event", "Third event"],
        )

    def test_tracking_voice_prompt_is_spoken_twice_once_per_loss(self):
        self.window.camera_state_changed(True)
        self.window.set_sound_enabled(True)
        calls = []
        call_finished = threading.Event()

        def fake_speech_process(args, **kwargs):
            calls.append((args, kwargs))
            call_finished.set()
            return SimpleNamespace(returncode=0, stderr="")

        tracking_lost = {
            "ear": None,
            "perclos": None,
            "head_angle": None,
            "head_pitch": None,
            "head_yaw": None,
            "head_roll": None,
            "blink_rate": 0.0,
            "mouth_aperture": None,
            "yawn_count": 0,
            "closed_duration": 0.0,
            "tracking_reliable": False,
            "calibrated": False,
            "calibrating": False,
            "drowsiness_level": "Tracking uncertain",
            "tracking_guidance": "Face not found: center your face.",
        }
        with patch.object(wideScreen.subprocess, "run", fake_speech_process):
            self.window._update_tracking_prompt(
                "Face is off-center: move into the middle of the camera view.",
                True,
            )
            self.assertIsNone(self.window.tracking_prompt_since)

            with patch(
                "wideScreen.time.monotonic",
                side_effect=[100.0, 104.9, 105.1, 106.0],
            ):
                self.window._update_tracking_prompt(
                    "Face/eyes too small or partly out of frame: move closer.",
                    True,
                )
                self.window._update_tracking_prompt(
                    tracking_lost["tracking_guidance"], True
                )
                self.assertEqual(len(calls), 0)
                self.window._update_tracking_prompt(
                    tracking_lost["tracking_guidance"], True
                )
            self.assertTrue(call_finished.wait(2))
            self.window._update_tracking_prompt(
                tracking_lost["tracking_guidance"], True
            )
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                calls[0][0][-1].count(
                    "Speak('Please set the camera properly.')"
                ),
                2,
            )

            self.update_window()
            call_finished.clear()
            with patch(
                "wideScreen.time.monotonic",
                side_effect=[200.0, 205.1],
            ):
                self.window._update_tracking_prompt(
                    tracking_lost["tracking_guidance"], True
                )
                self.window._update_tracking_prompt(
                    tracking_lost["tracking_guidance"], True
                )
            self.assertTrue(call_finished.wait(2))
            self.assertEqual(len(calls), 2)

            self.window.set_sound_enabled(False)
            self.update_window()
            with patch(
                "wideScreen.time.monotonic",
                side_effect=[300.0, 306.0],
            ):
                self.window._update_tracking_prompt(
                    tracking_lost["tracking_guidance"], True
                )
                self.window._update_tracking_prompt(
                    tracking_lost["tracking_guidance"], True
                )
            self.assertEqual(len(calls), 2)

    def test_unresponsive_timeout_starts_visual_parking_simulation(self):
        with patch.object(self.window, "_clock_now", return_value=100.0):
            self.window.update_alert_state("Level 1", False)
        self.window.unresponsive_since = 100.0
        self.window.drive_simulation.reset_simulation()

        with patch.object(self.window, "_clock_now", return_value=146.0):
            self.update_window(drowsiness_level="Level 1")

        self.assertEqual(self.window.drive_simulation.state, "Hazards on")
        self.assertTrue(self.window.parking_triggered)
        self.assertTrue(
            any(
                "Emergency Parking Simulation Started" in item.text()
                for item in self.window.event_list.findItems(
                    "*", QtCore.Qt.MatchWildcard
                )
            )
        )

    def test_sustained_head_deviation_escalates_and_tracking_loss_clears_timer(self):
        controller = SimpleNamespace(
            head_deviation_since=None,
            detection_settings={"yawn_threshold": 2, "blink_threshold": 30.0},
        )
        metrics = SimpleNamespace(
            tracking_reliable=True,
            perclos=0.0,
            yawn_count=0,
            blink_rate=0.0,
            closed_duration=0.0,
            yawn_duration=0.0,
            head_yaw=30.0,
        )
        with patch(
            "main.time.monotonic",
            side_effect=[100.0, 104.9, 105.1, 108.1, 112.1],
        ):
            initial = MainApp.get_drowsiness_level(controller, metrics, 15.0)
            before_grace = MainApp.get_drowsiness_level(
                controller, metrics, 15.0
            )
            sustained = MainApp.get_drowsiness_level(
                controller, metrics, 15.0
            )
            escalated = MainApp.get_drowsiness_level(
                controller, metrics, 25.0
            )
            severe = MainApp.get_drowsiness_level(
                controller, metrics, 35.0
            )
        self.assertEqual(initial, "None")
        self.assertEqual(before_grace, "None")
        self.assertEqual(sustained, "Level 1")
        self.assertEqual(escalated, "Level 2")
        self.assertEqual(severe, "Level 3")

        metrics.head_yaw = 30.0
        self.assertEqual(
            MainApp.get_drowsiness_level(controller, metrics, None),
            "None",
        )

        metrics.tracking_reliable = False
        self.assertEqual(
            MainApp.get_drowsiness_level(controller, metrics, None),
            "Tracking uncertain",
        )
        self.assertIsNone(controller.head_deviation_since)

    def test_brief_eye_closure_stays_quiet_and_sustained_closure_escalates(self):
        controller = SimpleNamespace(
            head_deviation_since=None,
            detection_settings={"yawn_threshold": 2, "blink_threshold": 30.0},
        )
        metrics = SimpleNamespace(
            tracking_reliable=True,
            perclos=25.0,
            yawn_count=0,
            blink_rate=0.0,
            closed_duration=1.0,
            yawn_duration=0.0,
        )
        with patch("main.time.monotonic", return_value=100.0):
            short_closure = MainApp.get_drowsiness_level(
                controller, metrics, None
            )
            metrics.closed_duration = 4.9
            before_grace = MainApp.get_drowsiness_level(
                controller, metrics, None
            )
            metrics.closed_duration = 5.0
            first_warning = MainApp.get_drowsiness_level(
                controller, metrics, None
            )
            metrics.closed_duration = 8.0
            second_warning = MainApp.get_drowsiness_level(
                controller, metrics, None
            )
            metrics.closed_duration = 12.0
            severe_warning = MainApp.get_drowsiness_level(
                controller, metrics, None
            )

        self.assertEqual(short_closure, "None")
        self.assertEqual(before_grace, "None")
        self.assertEqual(first_warning, "Level 1")
        self.assertEqual(second_warning, "Level 2")
        self.assertEqual(severe_warning, "Level 3")

    def test_talking_with_open_eyes_suppresses_yawn_only_alerts(self):
        controller = SimpleNamespace(
            head_deviation_since=None,
            detection_settings={"yawn_threshold": 2, "blink_threshold": 30.0},
        )
        metrics = SimpleNamespace(
            tracking_reliable=True,
            perclos=0.0,
            yawn_count=5,
            blink_rate=10.0,
            closed_duration=0.0,
            yawn_duration=12.0,
            speech_active=True,
        )

        with patch("main.time.monotonic", return_value=100.0):
            self.assertEqual(
                MainApp.get_drowsiness_level(controller, metrics, 0.0),
                "None",
            )

        metrics.closed_duration = 5.0
        with patch("main.time.monotonic", return_value=101.0):
            self.assertEqual(
                MainApp.get_drowsiness_level(controller, metrics, 0.0),
                "Level 1",
            )

    def test_repeated_mouth_open_close_motion_is_classified_as_talking(self):
        calculator = PERCLOSCalculator()
        samples = (
            (0.0, 0.2),
            (0.3, 0.7),
            (0.6, 0.2),
            (0.9, 0.7),
            (1.2, 0.2),
            (1.5, 0.7),
            (1.8, 0.2),
        )
        states = [
            calculator._update_speech_activity(aperture, timestamp)
            for timestamp, aperture in samples
        ]

        self.assertTrue(any(states))
        self.assertTrue(calculator.speech_active)
        calculator._reset_unreliable_frame()
        self.assertFalse(calculator.speech_active)
        self.assertEqual(len(calculator.mouth_history), 0)


if __name__ == "__main__":
    unittest.main()
