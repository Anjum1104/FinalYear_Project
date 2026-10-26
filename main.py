"""Run the webcam-backed drowsiness monitor and software driving demo."""

import ctypes
import sys
import time

import cv2

from perclos_calculation import DetectionMetrics, PERCLOSCalculator

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QImage

from wideScreen import HMIWindow


EYE_CLOSURE_ALERT_SECONDS = (5.0, 8.0, 12.0)
HEAD_DEVIATION_ALERT_SECONDS = (5.0, 8.0, 12.0)


class DetectionWorker(QtCore.QObject):
    """Run webcam I/O and computer vision away from the responsive GUI thread."""

    frame_ready = QtCore.pyqtSignal(QImage)
    detection_ready = QtCore.pyqtSignal(object)
    tracking_status = QtCore.pyqtSignal(str, str)
    event_message = QtCore.pyqtSignal(str)
    camera_started = QtCore.pyqtSignal(bool)
    calibration_progress = QtCore.pyqtSignal(str, int)
    calibration_finished = QtCore.pyqtSignal(str, bool)
    settings_requested = QtCore.pyqtSignal(object)
    def __init__(self):
        super().__init__()
        self.cap = None
        self.frame_timer = None
        self.perclos_calculator = None
        self.last_camera_status = ""
        self.calibration_in_progress = False
        self.paused = False
        self.camera_view = "Full camera"
        self.settings = {"sensitivity": 1.0}
        self.settings_requested.connect(self.update_settings)

    @QtCore.pyqtSlot()
    def start(self):
        if self.cap is not None and self.cap.isOpened():
            return
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            self.camera_started.emit(False)
            self._set_camera_status(
                "Camera unavailable — simulation only", "#ff9f1c"
            )
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 30
        self.perclos_calculator = PERCLOSCalculator(fps=fps)
        self.calibration_in_progress = False
        self.perclos_calculator.set_sensitivity(
            self.settings.get("sensitivity", 1.0)
        )
        self._set_camera_status(
            "Camera active — looking for a face", "#ffd43b"
        )
        if self.frame_timer is None:
            self.frame_timer = QtCore.QTimer(self)
            self.frame_timer.timeout.connect(self.process_frame)
        self.frame_timer.start(40)
        self.paused = False
        self.camera_started.emit(True)

    @QtCore.pyqtSlot()
    def pause(self):
        if self.frame_timer is not None:
            self.frame_timer.stop()
        self.paused = True
        self._set_camera_status("Camera paused", "#ffd43b")

    @QtCore.pyqtSlot()
    def resume(self):
        if self.cap is None:
            self._set_camera_status(
                "Start the webcam before resuming", "#ff9f1c"
            )
            return
        if self.frame_timer is not None:
            self.frame_timer.start(40)
        self.paused = False
        self._set_camera_status("Camera active — looking for a face", "#ffd43b")

    @QtCore.pyqtSlot(object)
    def update_settings(self, settings):
        self.settings.update(settings)
        if self.perclos_calculator is not None:
            self.perclos_calculator.set_sensitivity(
                self.settings.get("sensitivity", 1.0)
            )

    @QtCore.pyqtSlot(str)
    def set_camera_view(self, view):
        self.camera_view = view

    @QtCore.pyqtSlot()
    def start_calibration(self):
        if self.perclos_calculator is None:
            self._set_camera_status(
                "Calibration unavailable — webcam not active", "#ff9f1c"
            )
            return

        self.perclos_calculator.start_calibration()
        self.calibration_in_progress = True
        elapsed, prompt = self.perclos_calculator.calibration_progress()
        self.calibration_progress.emit(
            self._calibration_progress_message(prompt), elapsed
        )
        self.event_message.emit(
            "Personal calibration started — guided one-minute eye and posture setup"
        )
        self._set_camera_status(
            "Personal calibration in progress", "#ffd43b"
        )

    def _update_calibration_feedback(self, metrics):
        if not self.calibration_in_progress:
            return
        if metrics.calibrating:
            elapsed, prompt = self.perclos_calculator.calibration_progress()
            self.calibration_progress.emit(
                self._calibration_progress_message(prompt), elapsed
            )
            return

        self.calibration_in_progress = False
        eye_samples = len(self.perclos_calculator.calibration_samples)
        pose_samples = len(self.perclos_calculator.pose_calibration_samples)
        sample_summary = (
            f"Valid samples: eyes {eye_samples}/45, "
            f"posture {pose_samples}/20."
        )
        if (
            metrics.calibrated
            and metrics.pose_calibrated
            and metrics.eye_baseline is not None
            and metrics.eye_closure_threshold is not None
        ):
            baseline = metrics.eye_baseline
            threshold = metrics.eye_closure_threshold
            message = (
                f"Personal calibration complete — open-eye EAR {baseline:.3f}, "
                f"closure threshold {threshold:.3f}, usual head posture saved. "
                f"{sample_summary}"
            )
        elif metrics.calibrated:
            message = (
                "Eye ratio calibrated; usual head posture not captured — "
                f"repeat with your face visible. {sample_summary}"
            )
        elif metrics.pose_calibrated:
            message = (
                "Usual head posture saved; eye ratio not captured — "
                f"repeat with eyes visible in good lighting. {sample_summary}"
            )
        else:
            message = (
                "Calibration incomplete — not enough reliable face samples; "
                f"check camera framing and lighting, then retry. {sample_summary}"
            )
        success = metrics.calibrated and metrics.pose_calibrated
        self.calibration_finished.emit(message, success)
        self.event_message.emit(message)

    def _calibration_progress_message(self, prompt):
        eye_samples = len(self.perclos_calculator.calibration_samples)
        pose_samples = len(self.perclos_calculator.pose_calibration_samples)
        return (
            f"{prompt}\nValid samples: eyes {eye_samples}/45 · "
            f"posture {pose_samples}/20"
        )

    @QtCore.pyqtSlot()
    def process_frame(self):
        if self.cap is None or self.perclos_calculator is None:
            return

        success, frame = self.cap.read()
        if not success:
            metrics = self.perclos_calculator.reset_for_tracking_loss(
                "No camera frame received: check webcam connection or restart "
                "camera access."
            )
            self._update_calibration_feedback(metrics)
            self.detection_ready.emit(metrics)
            self._set_camera_status(
                "Camera frame unavailable — retrying", "#ff9f1c"
            )
            return

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        metrics = self.perclos_calculator.process_frame_for_metrics(gray_frame)
        self._update_calibration_feedback(metrics)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame = cv2.flip(rgb_frame, 1)
        rgb_frame = self.perclos_calculator.draw_landmarks(
            rgb_frame, metrics, mirrored=True
        )
        if self.camera_view == "Face close-up":
            rgb_frame = self._crop_face_preview(rgb_frame)
        rgb_frame = rgb_frame.copy(order="C")
        height, width = rgb_frame.shape[:2]
        image = QImage(width, height, QImage.Format_RGB888)
        image_address = int(image.bits())
        row_bytes = width * 3
        for row in range(height):
            ctypes.memmove(
                image_address + row * image.bytesPerLine(),
                rgb_frame[row].ctypes.data,
                row_bytes,
            )
        self.frame_ready.emit(image)
        self.detection_ready.emit(metrics)

        self._set_camera_status(
            "Camera active — looking for a face", "#ffd43b"
        )

    def _crop_face_preview(self, frame):
        landmarks = self.perclos_calculator.last_landmarks
        if landmarks is None:
            return frame

        points = landmarks.astype("int32").copy()
        points[:, 0] = frame.shape[1] - 1 - points[:, 0]
        x, y, face_width, face_height = cv2.boundingRect(
            cv2.convexHull(points)
        )
        if face_width <= 0 or face_height <= 0:
            return frame

        frame_height, frame_width = frame.shape[:2]
        crop_height = min(frame_height, max(int(face_height * 1.35), int(frame_height * 0.38)))
        crop_width = min(frame_width, int(crop_height * frame_width / frame_height))
        crop_height = min(frame_height, int(crop_width * frame_height / frame_width))
        center_x = x + face_width // 2
        center_y = y + face_height // 2
        left = min(max(0, center_x - crop_width // 2), frame_width - crop_width)
        top = min(max(0, center_y - crop_height // 2), frame_height - crop_height)
        return frame[top : top + crop_height, left : left + crop_width]

    def _set_camera_status(self, message, color):
        if message != self.last_camera_status:
            self.last_camera_status = message
            self.tracking_status.emit(message, color)

    @QtCore.pyqtSlot()
    def stop(self):
        if self.frame_timer is not None:
            self.frame_timer.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.paused = False
        self.calibration_in_progress = False
        self.camera_started.emit(False)
        self._set_camera_status("Webcam stopped", "#99abc1")


class MainApp(QtCore.QObject):
    """Connect worker results and interactive controls to the dashboard."""

    stop_requested = QtCore.pyqtSignal()

    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        super().__init__()

        self.window = HMIWindow()
        self.worker_thread = QtCore.QThread(self)
        self.detection_worker = DetectionWorker()
        self.detection_worker.moveToThread(self.worker_thread)

        self.window.calibration_requested.connect(
            self.detection_worker.start_calibration
        )
        self.window.camera_start_requested.connect(self.detection_worker.start)
        self.window.camera_stop_requested.connect(self.detection_worker.stop)
        self.window.camera_pause_requested.connect(self.detection_worker.pause)
        self.window.camera_resume_requested.connect(self.detection_worker.resume)
        self.window.camera_view_requested.connect(
            self.detection_worker.set_camera_view
        )
        self.detection_worker.calibration_progress.connect(
            self.window.update_calibration_progress
        )
        self.detection_worker.calibration_finished.connect(
            self.window.finish_calibration
        )
        self.window.settings_changed.connect(self.update_settings)
        self.window.acknowledge_requested.connect(self.acknowledge_alert)
        self.window.demo_parking_requested.connect(self.run_parking_demo)
        self.window.reset_alert_requested.connect(
            self.window.reset_alert_state
        )
        self.window.scenario_requested.connect(self.start_scenario)
        self.window.scenario_stop_requested.connect(self.stop_scenario)
        self.detection_worker.frame_ready.connect(self.window.update_map_frame)
        self.detection_worker.detection_ready.connect(self.update_detection)
        self.detection_worker.tracking_status.connect(
            self.window.set_tracking_status
        )
        self.detection_worker.camera_started.connect(
            self.window.camera_state_changed
        )
        self.detection_worker.event_message.connect(self.window.add_event)
        self.stop_requested.connect(
            self.detection_worker.stop,
            QtCore.Qt.BlockingQueuedConnection,
        )
        self.worker_thread.finished.connect(self.detection_worker.deleteLater)

        self.shutdown_started = False
        self.scenario_timer = QtCore.QTimer(self)
        self.scenario_timer.setInterval(250)
        self.scenario_timer.timeout.connect(self.advance_scenario)
        self.active_scenario = None
        self.scenario_started_at = None
        self.scenario_time_scale = 1.0
        self.head_deviation_since = None
        self.detection_settings = {
            "blink_threshold": self.window.blink_threshold,
            "yawn_threshold": self.window.yawn_threshold,
        }
        self.window.show()
        self.worker_thread.start()

    def get_drowsiness_level(self, metrics, head_angle):
        if not metrics.tracking_reliable:
            self.head_deviation_since = None
            return "Tracking uncertain"

        now = time.monotonic()
        if head_angle is not None and head_angle >= 12:
            if self.head_deviation_since is None:
                self.head_deviation_since = now
        else:
            self.head_deviation_since = None
        head_deviation_duration = (
            now - self.head_deviation_since
            if self.head_deviation_since is not None
            else 0.0
        )
        perclos = metrics.perclos or 0.0
        eye_closure_active = metrics.closed_duration > 0.0
        perclos_alert = perclos >= 20 and not eye_closure_active
        talking = getattr(metrics, "speech_active", False)
        yawn_count = 0 if talking else metrics.yawn_count
        yawn_duration = 0.0 if talking else metrics.yawn_duration
        level = "None"
        if (
            perclos_alert
            or yawn_count >= self.detection_settings["yawn_threshold"]
            or metrics.blink_rate >= self.detection_settings["blink_threshold"]
            or metrics.closed_duration >= EYE_CLOSURE_ALERT_SECONDS[0]
            or yawn_duration >= 3.0
            or head_angle is not None
            and head_angle >= 12
            and head_deviation_duration >= HEAD_DEVIATION_ALERT_SECONDS[0]
        ):
            level = "Level 1"
        if (
            perclos >= 35 and not eye_closure_active
            or yawn_count >= self.detection_settings["yawn_threshold"] + 1
            or metrics.closed_duration >= EYE_CLOSURE_ALERT_SECONDS[1]
            or yawn_duration >= 6.0
            or head_angle is not None
            and head_angle >= 22
            and head_deviation_duration >= HEAD_DEVIATION_ALERT_SECONDS[1]
        ):
            level = "Level 2"
        if (
            perclos >= 50 and not eye_closure_active
            or metrics.closed_duration >= EYE_CLOSURE_ALERT_SECONDS[2]
            or yawn_duration >= 10.0
            or head_angle is not None
            and head_angle >= 32
            and head_deviation_duration >= HEAD_DEVIATION_ALERT_SECONDS[2]
        ):
            level = "Level 3"
        return level

    @QtCore.pyqtSlot(object)
    def update_detection(self, metrics: DetectionMetrics):
        if self.active_scenario is not None:
            return
        pose_deviations = (
            [
                abs(value)
                for value in (metrics.head_pitch, metrics.face_roll)
                if value is not None
            ]
            if metrics.pose_calibrated
            else []
        )
        reliable_head_angle = (
            max(pose_deviations)
            if metrics.tracking_reliable and pose_deviations
            else None
        )
        level = self.get_drowsiness_level(metrics, reliable_head_angle)
        condition = (
            "Unknown"
            if not metrics.tracking_reliable
            else "Critical"
            if metrics.closed_duration > self.window.critical_eye_seconds
            else "Drowsy"
            if level != "None"
            else "Attentive"
        )
        self.window.drive_simulation.set_driver_condition(condition)
        self.window.update_detection(
            ear=metrics.ear,
            perclos=metrics.perclos,
            head_angle=reliable_head_angle,
            head_pitch=metrics.head_pitch,
            head_yaw=metrics.head_yaw,
            head_roll=metrics.face_roll,
            blink_rate=metrics.blink_rate,
            mouth_aperture=metrics.mouth_aperture,
            yawn_count=metrics.yawn_count,
            yawn_duration=metrics.yawn_duration,
            closed_duration=metrics.closed_duration,
            tracking_reliable=metrics.tracking_reliable,
            calibrated=metrics.calibrated,
            calibrating=metrics.calibrating,
            drowsiness_level=level,
            pose_calibrated=metrics.pose_calibrated,
            ear_baseline=metrics.eye_baseline,
            eye_closure_threshold=metrics.eye_closure_threshold,
            tracking_guidance=metrics.tracking_guidance,
            speech_active=metrics.speech_active,
        )

    @QtCore.pyqtSlot(object)
    def update_settings(self, settings):
        self.detection_settings.update(settings)
        self.detection_worker.settings_requested.emit(settings)

    def pause_camera(self):
        self.window.camera_paused = True

    def resume_camera(self):
        self.window.camera_paused = False

    @QtCore.pyqtSlot(str, bool)
    def start_scenario(self, name, fast):
        self.scenario_timer.stop()
        self.active_scenario = name
        self.scenario_started_at = time.monotonic()
        self.scenario_time_scale = 10.0 if fast else 1.0
        self.window.mock_test_active = True
        self.window._test_clock_started = time.monotonic()
        self.window._test_clock_scale = self.scenario_time_scale
        self.window.parking_triggered = False
        if name == "Emergency parking":
            if self.window.drive_simulation.state != "Driving":
                self.window.drive_simulation.reset_simulation()
            self.window.drive_simulation.set_time_scale(
                self.scenario_time_scale
            )
            self.window.drive_simulation.start_parking_demo()
            self.window.add_event(
                "SIMULATED TEST: manual emergency-parking demonstration"
            )
            self.scenario_timer.start()
            return
        self.window.drive_simulation.reset_simulation()
        self.window.drive_simulation.set_time_scale(self.scenario_time_scale)
        self.window.add_event(
            f"SIMULATED TEST started: {name}"
            + (" (accelerated)" if fast else "")
        )
        self.scenario_timer.start()
        self.advance_scenario()

    @QtCore.pyqtSlot()
    def stop_scenario(self):
        if self.active_scenario is None:
            return
        self.scenario_timer.stop()
        self.active_scenario = None
        self.scenario_started_at = None
        self.scenario_time_scale = 1.0
        self.window.mock_test_active = False
        self.window._test_clock_started = None
        self.window._test_clock_scale = 1.0
        self.window.drive_simulation.set_time_scale(1.0)
        self.window.add_event("Simulated test stopped")
        self.window.update_alert_state("None", False)
        self.window.update_detection(
            ear=None,
            perclos=None,
            head_angle=None,
            head_pitch=None,
            head_yaw=None,
            head_roll=None,
            blink_rate=0.0,
            mouth_aperture=None,
            yawn_count=0,
            closed_duration=0.0,
            tracking_reliable=False,
            calibrated=False,
            calibrating=False,
            drowsiness_level="Tracking uncertain",
        )

    def advance_scenario(self):
        if self.active_scenario is None or self.scenario_started_at is None:
            return
        elapsed = (time.monotonic() - self.scenario_started_at) * self.scenario_time_scale
        name = self.active_scenario
        reliable = name != "Face tracking loss"
        closed_duration = 0.0
        perclos = 4.0
        blink_rate = 15.0
        mouth = 0.18
        yawns = 0
        yawn_duration = 0.0
        head_angle = 0.0
        eye_closed = False

        if name == "Mild drowsiness":
            perclos, blink_rate = 24.0, 34.0
        elif name in ("Prolonged eye closure", "Critical alert escalation"):
            closed_duration = elapsed
            perclos, eye_closed = min(100.0, elapsed * 2.0), True
        elif name == "Repeated yawning":
            mouth, yawns, perclos = 0.72, min(4, int(elapsed // 2) + 1), 25.0
            yawn_duration = elapsed
        elif name == "Head tilt":
            head_angle, perclos = 42.0, 15.0
        elif name == "Unresponsive driver":
            perclos = 55.0
        elif name == "Recovery after opening eyes":
            if elapsed < 4.0:
                closed_duration, perclos, eye_closed = elapsed, 30.0, True
            else:
                perclos, blink_rate = 8.0, 16.0
        elif name == "Normal attentive driving":
            perclos = 5.0

        metrics = DetectionMetrics(
            ear=0.16 if eye_closed else 0.31,
            perclos=perclos,
            face_roll=0.0,
            head_pitch=42.0 if name == "Head tilt" else 2.0,
            head_yaw=3.0,
            eye_closed=eye_closed,
            closed_duration=closed_duration,
            blink_rate=blink_rate,
            mouth_aperture=mouth,
            yawn_count=yawns,
            tracking_reliable=reliable,
            calibrated=True,
            calibrating=False,
            yawn_duration=yawn_duration,
            pose_calibrated=True,
        )
        self.window.update_detection(
            ear=metrics.ear,
            perclos=metrics.perclos,
            head_angle=head_angle if reliable else None,
            head_pitch=metrics.head_pitch if reliable else None,
            head_yaw=metrics.head_yaw if reliable else None,
            head_roll=metrics.face_roll if reliable else None,
            blink_rate=metrics.blink_rate,
            mouth_aperture=metrics.mouth_aperture,
            yawn_count=metrics.yawn_count,
            yawn_duration=metrics.yawn_duration,
            closed_duration=metrics.closed_duration,
            tracking_reliable=metrics.tracking_reliable,
            calibrated=metrics.calibrated,
            calibrating=False,
            drowsiness_level=self.get_drowsiness_level(
                metrics, head_angle if reliable else None
            ),
        )
        condition = (
            "Unknown"
            if not reliable
            else "Critical"
            if closed_duration > self.window.critical_eye_seconds
            else "Drowsy"
            if self.get_drowsiness_level(
                metrics, head_angle if reliable else None
            ) != "None"
            else "Attentive"
        )
        self.window.drive_simulation.set_driver_condition(condition)
        if name == "Recovery after opening eyes" and elapsed >= 7.0:
            self.stop_scenario()
        elif name == "Emergency parking" and self.window.drive_simulation.state == "Parked":
            self.stop_scenario()

    def acknowledge_alert(self):
        self.window.note_driver_response()

    def run_parking_demo(self):
        self.window.add_event("Emergency Parking Simulation Started — manual test")
        self.window.drive_simulation.start_parking_demo()

    def run(self):
        try:
            return self.app.exec_()
        finally:
            self.close_event()

    def close_event(self):
        if self.shutdown_started:
            return
        self.shutdown_started = True
        self.scenario_timer.stop()
        if self.worker_thread.isRunning():
            self.stop_requested.emit()
            self.worker_thread.quit()
            self.worker_thread.wait()


if __name__ == "__main__":
    application = MainApp()
    sys.exit(application.run())
