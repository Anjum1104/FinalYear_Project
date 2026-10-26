"""Interactive PyQt dashboard for the webcam and software driving demo."""

import array
import io
import json
import math
import re
import sys
import subprocess
import threading
import time
import wave
from datetime import datetime

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)


class DriveSimulationWidget(QtWidgets.QWidget):
    """An illustrative road and cabin animation; it never controls a vehicle."""

    state_changed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()
    speed_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.state = "Driving"
        self.road_offset = 0.0
        self.parking_started_at = None
        self.speed = 62.0
        self.mode = "Day"
        self.weather = "Clear"
        self.driver_condition = "Attentive"
        self.time_scale = 1.0
        self._last_tick = time.monotonic()
        self._hazard_phase = False
        self.animation_timer = QtCore.QTimer(self)
        self.animation_timer.timeout.connect(self.advance_simulation)
        self.animation_timer.start(80)

    def start_parking_demo(self):
        if self.state in ("Hazards on", "Pulling over", "Parked"):
            return
        self.parking_started_at = time.monotonic()
        self.speed = max(self.speed, 62.0)
        self._last_tick = time.monotonic()
        self._set_state("Hazards on")

    def reset_simulation(self):
        self.parking_started_at = None
        self.road_offset = 0.0
        self.speed = 62.0
        self._set_state("Driving")

    def set_drive_mode(self, mode, weather):
        self.mode = mode
        self.weather = weather
        self.update()

    def set_driver_condition(self, condition):
        self.driver_condition = condition
        self.update()

    def set_time_scale(self, scale):
        self.time_scale = max(1.0, float(scale))

    def _set_state(self, state):
        if self.state != state:
            self.state = state
            self.state_changed.emit(state)
        self.update()

    def advance_simulation(self):
        now = time.monotonic()
        elapsed = (now - self._last_tick) * self.time_scale
        self._last_tick = now
        if self.state == "Driving":
            self.road_offset = (self.road_offset + 3.0) % 40.0
            self.speed = min(62.0, self.speed + elapsed * 15.0)
        elif self.parking_started_at is not None:
            elapsed = (now - self.parking_started_at) * self.time_scale
            self.road_offset = (self.road_offset + max(0.3, self.speed / 62.0 * 3.0)) % 40.0
            self.speed = max(0.0, 62.0 * (1.0 - elapsed / 5.0))
            self.speed_changed.emit(round(self.speed))
            if elapsed >= 5.0:
                self._set_state("Parked")
                self.speed = 0.0
                self.finished.emit()
            elif elapsed >= 2.0:
                self._set_state("Pulling over")
            self._hazard_phase = not self._hazard_phase
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect()
        width = bounds.width()
        height = bounds.height()

        night = self.mode == "Night"
        sky_top = QColor("#101827") if night else QColor("#71b6df")
        sky_bottom = QColor("#26394c") if night else QColor("#d3e9ee")
        sky = QLinearGradient(0, 0, 0, height * 0.68)
        sky.setColorAt(0, sky_top)
        sky.setColorAt(1, sky_bottom)
        painter.fillRect(bounds, QColor("#151b22"))
        painter.fillRect(0, 0, width, int(height * 0.68), sky)

        center = width / 2
        horizon = height * 0.31
        shoulder = QColor("#283a36") if not night else QColor("#172526")
        painter.setPen(Qt.NoPen)
        painter.setBrush(shoulder)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(0, horizon),
                    QPointF(width * 0.2, horizon * 0.78),
                    QPointF(width * 0.35, horizon),
                    QPointF(width * 0.5, horizon * 0.73),
                    QPointF(width * 0.69, horizon),
                    QPointF(width, horizon * 0.8),
                    QPointF(width, height * 0.69),
                    QPointF(0, height * 0.69),
                ]
            )
        )
        road_top = horizon + 7
        road_bottom = height * 0.75
        painter.setBrush(QColor("#354149") if not night else QColor("#252d37"))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(center - width * 0.075, road_top),
                    QPointF(center + width * 0.075, road_top),
                    QPointF(width * 0.86, road_bottom),
                    QPointF(width * 0.14, road_bottom),
                ]
            )
        )
        road_glow = QColor("#edcf8a") if night else QColor("#f4e8c9")
        painter.setPen(QPen(road_glow, 1.5))
        painter.drawLine(
            int(center - width * 0.075), int(road_top),
            int(width * 0.14), int(road_bottom),
        )
        painter.drawLine(
            int(center + width * 0.075), int(road_top),
            int(width * 0.86), int(road_bottom),
        )

        for index in range(8):
            progress = ((index * 34 + self.road_offset) % 272) / 272
            y = road_top + progress * (road_bottom - road_top)
            dash_height = 2 + progress * 10
            dash_width = 1 + progress * 5
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#f2e6bf"))
            painter.drawRoundedRect(
                int(center - dash_width / 2), int(y),
                int(dash_width), int(dash_height), 2, 2,
            )

        if night:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 237, 168, 28))
            painter.drawEllipse(
                int(center - width * 0.24), int(road_top),
                int(width * 0.48), int(height * 0.48),
            )

        if self.weather in ("Rain", "Fog"):
            if self.weather == "Fog":
                painter.fillRect(
                    0, int(horizon * 0.72), width, int(height * 0.5),
                    QColor(215, 225, 226, 105),
                )
            else:
                painter.setPen(QPen(QColor(202, 224, 244, 130), 1))
                for index in range(24):
                    x = (index * 37 + int(self.road_offset * 4)) % max(width, 1)
                    y = (index * 23 + int(self.road_offset * 5)) % int(height * 0.7)
                    painter.drawLine(x, y, x - 5, y + 12)

        # Cabin shell, windshield frame, side windows and mirror.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#202c39"))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(0, 0), QPointF(width * 0.25, 0),
                    QPointF(width * 0.2, height * 0.13),
                    QPointF(width * 0.09, height * 0.5),
                    QPointF(0, height * 0.57),
                ]
            )
        )
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(width, 0), QPointF(width * 0.75, 0),
                    QPointF(width * 0.8, height * 0.13),
                    QPointF(width * 0.91, height * 0.5),
                    QPointF(width, height * 0.57),
                ]
            )
        )
        painter.setBrush(QColor("#31465a"))
        painter.drawRoundedRect(
            int(center - width * 0.075), int(height * 0.07),
            int(width * 0.15), int(height * 0.035), 7, 7,
        )
        painter.setPen(QPen(QColor("#111a24"), 5))
        painter.drawLine(int(width * .2), int(height * .13), int(width * .08), int(height * .59))
        painter.drawLine(int(width * .8), int(height * .13), int(width * .92), int(height * .59))

        # Driver is an illustration only, never a detected camera subject.
        avatar_x = center
        avatar_y = height * 0.53
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#17202b"))
        painter.drawEllipse(
            int(avatar_x - width * .105), int(avatar_y - height * .19),
            int(width * .21), int(height * .39),
        )
        painter.setBrush(QColor("#25374a"))
        painter.drawRoundedRect(
            int(avatar_x - width * .105), int(avatar_y + height * .04),
            int(width * .21), int(height * .21), 18, 18,
        )
        skin = QColor("#bd8063")
        painter.setBrush(skin)
        face_rect = (
            int(avatar_x - width * .075), int(avatar_y - height * .18),
            int(width * .15), int(height * .19),
        )
        painter.drawRoundedRect(*face_rect, 18, 18)
        painter.setBrush(QColor("#382a27"))
        painter.drawArc(
            int(avatar_x - width * .081), int(avatar_y - height * .21),
            int(width * .162), int(height * .10), 0, 180 * 16,
        )
        painter.setBrush(skin.lighter(108))
        painter.drawEllipse(
            int(avatar_x - width * .083), int(avatar_y - height * .115),
            int(width * .018), int(height * .045),
        )
        painter.drawEllipse(
            int(avatar_x + width * .065), int(avatar_y - height * .115),
            int(width * .018), int(height * .045),
        )
        eye_y = int(avatar_y - height * .112)
        eye_color = QColor("#4b3025")
        painter.setPen(QPen(eye_color, max(2, int(width * .004))))
        if self.driver_condition in ("Drowsy", "Critical"):
            painter.drawLine(
                int(avatar_x - width * .045), eye_y,
                int(avatar_x - width * .014), eye_y + 2,
            )
            painter.drawLine(
                int(avatar_x + width * .014), eye_y + 2,
                int(avatar_x + width * .045), eye_y,
            )
        else:
            eye_size = max(4, int(width * .012))
            painter.drawEllipse(
                int(avatar_x - width * .045), eye_y, eye_size, eye_size
            )
            painter.drawEllipse(
                int(avatar_x + width * .03), eye_y, eye_size, eye_size
            )
        painter.setPen(QPen(QColor("#733d3a"), 2))
        painter.drawLine(
            int(avatar_x - width * .009), int(avatar_y - height * .075),
            int(avatar_x + width * .009), int(avatar_y - height * .075),
        )
        painter.setPen(Qt.NoPen)

        # Arms and hands rest on a visible steering wheel.
        painter.setPen(QPen(QColor("#bd8063"), max(5, int(width * .014))))
        painter.drawLine(
            int(avatar_x - width * .07), int(avatar_y + height * .14),
            int(avatar_x - width * .14), int(height * .68),
        )
        painter.drawLine(
            int(avatar_x + width * .07), int(avatar_y + height * .14),
            int(avatar_x + width * .14), int(height * .68),
        )
        wheel_color = QColor("#111820")
        painter.setPen(QPen(wheel_color, max(7, int(width * .025))))
        painter.drawArc(
            int(center - width * .2), int(height * .51),
            int(width * .4), int(height * .55), 0, 180 * 16,
        )
        painter.drawLine(
            int(center), int(height * .78), int(center), int(height * .66)
        )
        painter.setPen(QPen(QColor("#bd8063"), max(5, int(width * .014))))
        painter.drawLine(
            int(center - width * .14), int(height * .68),
            int(center - width * .15), int(height * .65),
        )
        painter.drawLine(
            int(center + width * .14), int(height * .68),
            int(center + width * .15), int(height * .65),
        )

        # Dashboard and instrument cluster foreground.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#111820"))
        painter.drawRoundedRect(
            int(width * .07), int(height * .75),
            int(width * .86), int(height * .27), 16, 16,
        )
        painter.setBrush(QColor("#243543"))
        painter.drawRoundedRect(
            int(width * .4), int(height * .81),
            int(width * .2), int(height * .035), 6, 6,
        )
        painter.setPen(QPen(QColor("#6de1bd"), 2))
        painter.drawArc(
            int(width * .17), int(height * .79),
            int(width * .13), int(height * .16), 0, 270 * 16,
        )
        painter.setPen(QColor("#d5e2ef"))
        painter.drawText(
            int(width * .19), int(height * .89),
            f"{round(self.speed):02d}",
        )

        status_color = (
            QColor("#ff5555")
            if self.state in ("Hazards on", "Pulling over")
            else QColor("#ffd43b")
            if self.state == "Parked"
            else QColor("#57d998")
        )
        painter.setPen(status_color)
        painter.drawText(
            12, 20,
            f"ILLUSTRATION ONLY  |  {self.state.upper()}  |  {self.mode.upper()} / {self.weather.upper()}",
        )
        if self.state in ("Hazards on", "Pulling over") and self._hazard_phase:
            painter.setPen(QPen(QColor("#ff633f"), 5))
            painter.drawPoint(int(width * .11), int(height * .71))
            painter.drawPoint(int(width * .89), int(height * .71))
        if self.state in ("Hazards on", "Pulling over"):
            painter.setPen(QColor("#ffcc4d"))
            painter.drawText(
                int(width * .55), int(height * .91),
                f"HAZARDS ON  ·  {round(self.speed)} km/h",
            )
        elif self.state == "Parked":
            painter.setPen(QColor("#ffd43b"))
            painter.drawText(
                int(width * .55), int(height * .91),
                "VEHICLE STOPPED — SIMULATION COMPLETE",
            )

class HMIWindow(QtWidgets.QMainWindow):
    MAX_SESSION_EVENTS = 1000
    TRACKING_PROMPT_GRACE_SECONDS = 5.0
    TRACKING_CHECK_STAGE_SECONDS = 6.0
    TRACKING_CHECK_STAGES = (
        "Sit in your usual comfortable posture and face the camera.",
        "Keep your natural eye shape; blink normally without forcing eyes wide.",
        "Gently glance left and right, then return to your usual position.",
        "Gently tilt or bend your head as it naturally moves when tired.",
        "Keep usual glasses on if you wear them; finish in your normal posture.",
    )

    calibration_requested = QtCore.pyqtSignal()
    acknowledge_requested = QtCore.pyqtSignal()
    demo_parking_requested = QtCore.pyqtSignal()
    camera_start_requested = QtCore.pyqtSignal()
    camera_stop_requested = QtCore.pyqtSignal()
    camera_pause_requested = QtCore.pyqtSignal()
    camera_resume_requested = QtCore.pyqtSignal()
    camera_view_requested = QtCore.pyqtSignal(str)
    settings_changed = QtCore.pyqtSignal(object)
    scenario_requested = QtCore.pyqtSignal(str, bool)
    scenario_stop_requested = QtCore.pyqtSignal()
    reset_alert_requested = QtCore.pyqtSignal()
    audio_error = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Driver Safety | Live Monitor & Simulation")
        self.session_started_at = datetime.now().astimezone()
        self.session_started_monotonic = time.monotonic()
        self.setMinimumSize(980, 720)
        screen = QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        if available is None:
            self.resize(1280, 800)
        else:
            self.resize(
                max(self.minimumWidth(), min(1440, available.width() - 32)),
                max(self.minimumHeight(), min(920, available.height() - 64)),
            )
        self.sound_enabled = True
        self.text_scale = 1.0
        self.high_contrast_mode = False
        self.audio_lock = threading.Lock()
        self.tracking_prompt_lock = threading.Lock()
        self.tracking_prompted = False
        self.tracking_prompt_since = None
        self.last_alert_key = None
        self.current_alert_interval = 2500
        self.current_alert_critical = False
        self.parking_triggered = False
        self.unresponsive_since = None
        self.critical_eye_seconds = 35.0
        self.parking_seconds = 45.0
        self.critical_repeat_ms = 1000
        self.blink_threshold = 30.0
        self.yawn_threshold = 2
        self.sensitivity = 1.0
        self.demo_time_scale = 1.0
        self._test_clock_started = None
        self._test_clock_scale = 1.0
        self.mock_test_active = False
        self.event_history = []
        self.event_history_truncated = False
        self.live_tracking_samples = 0
        self.reliable_tracking_samples = 0
        self.personal_calibration_completed = False
        self.completed_tracking_check = None
        self.warning_count = 0
        self.simulation_count = 0
        self.camera_paused = False
        self.camera_active = False
        self.camera_preview_hidden = False
        self.latest_tracking_reliable = False
        self.latest_drowsiness_level = "Tracking uncertain"
        self.latest_critical = False
        self.latest_camera_image = None
        self.tracking_check_started_at = None
        self.tracking_check_samples = []
        self.tracking_check_dialog = None

        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #0b1220;
                color: #e8eef7;
                font-family: Arial;
            }
            QPushButton:focus, QComboBox:focus, QCheckBox:focus,
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #8cc8ff;
            }
            QFrame#panel {
                background-color: #151f30;
                border: 1px solid #2b3b52;
                border-radius: 14px;
            }
            QLabel#header {
                color: #e8eef7;
                font-size: 24px;
                font-weight: bold;
            }
            QLabel#subtitle, QLabel#muted {
                color: #99abc1;
                font-size: 12px;
            }
            QLabel#metricTitle {
                color: #91a7c2;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#metricValue {
                color: #f4f7fb;
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#metricTitle { font-size: 11px; }
            QLabel#metricValue { font-size: 17px; }
            QLabel { background: transparent; }
            QPushButton {
                background-color: #25354b;
                color: #f4f7fb;
                border: 1px solid #354a65;
                border-radius: 9px;
                padding: 6px 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #31577c; }
            QPushButton:pressed { background-color: #1b3d5c; }
            QListWidget {
                background-color: #101927;
                border: 1px solid #2b3b52;
                border-radius: 8px;
                padding: 4px;
                color: #c7d4e3;
                font-size: 11px;
            }
            QStatusBar { color: #a9b8ca; }
            """
        )

        self.init_ui()
        self._apply_accessibility_styles()
        self.calibration_hide_timer = QtCore.QTimer(self)
        self.calibration_hide_timer.setSingleShot(True)
        self.calibration_hide_timer.timeout.connect(
            self._hide_calibration_status
        )
        self.clock_timer = QtCore.QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()

        self.sound_timer = QtCore.QTimer(self)
        self.sound_timer.timeout.connect(self.play_alert_beep)
        self.tracking_check_timer = QtCore.QTimer(self)
        self.tracking_check_timer.setInterval(100)
        self.tracking_check_timer.timeout.connect(
            self._update_tracking_check_progress
        )
        self.audio_error.connect(
            lambda message: self.statusBar().showMessage(message, 5000)
        )

    def init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)

        header = QtWidgets.QFrame()
        header.setObjectName("panel")
        header_layout = QtWidgets.QHBoxLayout(header)
        title_layout = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("DRIVER SAFETY MONITOR")
        title.setObjectName("header")
        subtitle = QtWidgets.QLabel(
            "Live driver monitor  |  Software-only simulation"
        )
        subtitle.setObjectName("subtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        self.clock_label = QtWidgets.QLabel()
        self.clock_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.clock_label.setObjectName("muted")
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        header_layout.addWidget(self.clock_label)
        root.addWidget(header)

        content = QtWidgets.QHBoxLayout()
        content.setSpacing(8)

        camera_panel = QtWidgets.QFrame()
        camera_panel.setObjectName("panel")
        camera_layout = QtWidgets.QVBoxLayout(camera_panel)
        camera_layout.setContentsMargins(10, 8, 10, 8)
        camera_layout.setSpacing(5)
        camera_title = QtWidgets.QLabel("FRONT-FACING DRIVER CAMERA")
        camera_title.setStyleSheet("font-weight:bold; color:#8cc8ff;")
        self.tracking_label = QtWidgets.QLabel("Webcam stopped")
        self.tracking_label.setWordWrap(True)
        self.tracking_label.setObjectName("muted")
        self.source_label = QtWidgets.QLabel(
            "NO LIVE DATA"
        )
        self.source_label.setStyleSheet(
            "color:#aebdce; font-size:10px; font-weight:bold;"
        )
        self.source_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        camera_status = QtWidgets.QHBoxLayout()
        camera_status.setSpacing(8)
        camera_status.addWidget(self.tracking_label, 1)
        camera_status.addWidget(self.source_label)
        self.camera_view_combo = QtWidgets.QComboBox()
        self.camera_view_combo.addItems(["Full camera", "Face close-up"])
        self.camera_view_combo.setToolTip(
            "Choose a full webcam view or crop around the detected face. "
            "This changes only the preview, not the detection."
        )
        self.camera_view_combo.currentTextChanged.connect(
            self.camera_view_requested.emit
        )
        camera_status.addWidget(self.camera_view_combo)
        self.quality_guidance_label = QtWidgets.QLabel()
        self.quality_guidance_label.setWordWrap(True)
        self.quality_guidance_label.setStyleSheet(
            "color:#ffd43b; font-size:10px; font-weight:bold;"
        )
        self.quality_guidance_label.hide()
        self.calibration_label = QtWidgets.QLabel()
        self.calibration_label.setWordWrap(True)
        self.calibration_label.setStyleSheet(
            "color:#ffd43b; font-size:11px; font-weight:bold;"
        )
        self.calibration_label.hide()
        self.calibration_progress_bar = QtWidgets.QProgressBar()
        self.calibration_progress_bar.setRange(0, 60)
        self.calibration_progress_bar.setFormat("%v / 60 sec")
        self.calibration_progress_bar.setMaximumHeight(12)
        self.calibration_progress_bar.hide()
        self.camera_label = QtWidgets.QLabel("Waiting for webcam...")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(260, 150)
        self.camera_label.setWordWrap(True)
        self.camera_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        self.camera_label.setStyleSheet(
            "background-color:#080d15; border:1px solid #30415a; "
            "border-radius:10px; color:#8193a9;"
        )
        self.camera_label.setToolTip(
            "Live mirrored webcam view. Face close-up enlarges the real camera "
            "image when a face is tracked."
        )
        self.response_label = QtWidgets.QLabel("Driver response: waiting")
        self.response_label.setObjectName("muted")
        self.response_label.setStyleSheet(
            "color:#c2d1e2; font-size:10px;"
        )
        camera_buttons = QtWidgets.QHBoxLayout()
        self.calibrate_button = QtWidgets.QPushButton("Calibrate eyes + pose")
        self.calibrate_button.setToolTip(
            "Run the guided one-minute setup in your usual comfortable driving "
            "posture. Do not force your head straight. It learns your personal "
            "eye ratio and habitual head angle, then prompts natural blinks, "
            "gentle glances and tilts."
        )
        self.calibrate_button.clicked.connect(
            lambda: self.calibration_requested.emit()
        )
        self.tracking_check_button = QtWidgets.QPushButton(
            "Check tracking"
        )
        self.tracking_check_button.setToolTip(
            "Measure face and eye tracking across a short guided series of "
            "normal posture, eye, and head movements. This is diagnostic only."
        )
        self.tracking_check_button.clicked.connect(self.open_tracking_check)
        self.acknowledge_button = QtWidgets.QPushButton("I'm alert")
        self.acknowledge_button.clicked.connect(
            lambda: self.acknowledge_requested.emit()
        )
        camera_buttons.addWidget(self.calibrate_button)
        camera_buttons.addWidget(self.tracking_check_button)
        camera_buttons.addWidget(self.acknowledge_button)
        camera_layout.addWidget(camera_title)
        camera_layout.addLayout(camera_status)
        camera_layout.addWidget(self.quality_guidance_label)
        camera_layout.addWidget(self.calibration_label)
        camera_layout.addWidget(self.calibration_progress_bar)
        camera_layout.addWidget(self.camera_label, 1)
        camera_layout.addLayout(camera_buttons)

        camera_controls = QtWidgets.QHBoxLayout()
        self.camera_start_button = QtWidgets.QPushButton("Start webcam")
        self.camera_start_button.clicked.connect(
            lambda: self.camera_start_requested.emit()
        )
        self.camera_pause_button = QtWidgets.QPushButton("Pause")
        self.camera_pause_button.clicked.connect(
            self.request_camera_pause
        )
        self.camera_resume_button = QtWidgets.QPushButton("Resume")
        self.camera_resume_button.clicked.connect(
            self.request_camera_resume
        )
        self.camera_stop_button = QtWidgets.QPushButton("Stop")
        self.camera_stop_button.clicked.connect(
            lambda: self.camera_stop_requested.emit()
        )
        self.camera_pause_button.setEnabled(False)
        self.camera_resume_button.setEnabled(False)
        self.camera_stop_button.setEnabled(False)
        camera_controls.addWidget(self.camera_start_button)
        camera_controls.addWidget(self.camera_pause_button)
        camera_controls.addWidget(self.camera_resume_button)
        camera_controls.addWidget(self.camera_stop_button)
        camera_layout.addLayout(camera_controls)
        content.addWidget(camera_panel, 5)

        right_column = QtWidgets.QVBoxLayout()
        right_column.setSpacing(6)
        simulation_panel = QtWidgets.QFrame()
        simulation_panel.setObjectName("panel")
        simulation_layout = QtWidgets.QVBoxLayout(simulation_panel)
        simulation_layout.setContentsMargins(8, 6, 8, 6)
        simulation_layout.setSpacing(4)
        simulation_title = QtWidgets.QLabel(
            "DRIVER IN-CAR VIEW  ·  ILLUSTRATION ONLY"
        )
        simulation_title.setStyleSheet(
            "font-weight:bold; color:#8cc8ff; font-size:11px;"
        )
        self.drive_simulation = DriveSimulationWidget()
        self.drive_simulation.state_changed.connect(self.on_simulation_state_changed)
        simulation_layout.addWidget(simulation_title)
        simulation_layout.addWidget(self.drive_simulation)
        right_column.addWidget(simulation_panel)

        metrics_panel = QtWidgets.QFrame()
        metrics_panel.setObjectName("panel")
        metrics_layout = QtWidgets.QGridLayout(metrics_panel)
        metrics_layout.setContentsMargins(6, 5, 6, 5)
        metrics_layout.setHorizontalSpacing(6)
        metrics_layout.setVerticalSpacing(5)
        for row in range(4):
            metrics_layout.setRowMinimumHeight(row, 38)
        self.ear_label = self.create_metric(metrics_layout, 0, 0, "EAR RATIO", "--")
        self.perclos_label = self.create_metric(
            metrics_layout, 0, 1, "PERCLOS · 15s", "--"
        )
        self.blink_label = self.create_metric(
            metrics_layout, 1, 0, "BLINKS /MIN", "0"
        )
        self.mouth_label = self.create_metric(
            metrics_layout, 1, 1, "MOUTH OPEN", "--"
        )
        self.mouth_label.parentWidget().setToolTip("Mouth aperture ratio")
        self.yawn_label = self.create_metric(
            metrics_layout, 2, 0, "YAWNS · /MIN", "0"
        )
        self.head_angle_label = self.create_metric(
            metrics_layout, 2, 1, "HEAD BEND ° / %", "--"
        )
        self.head_angle_label.parentWidget().setToolTip(
            "Calibrated pitch/roll deviation in degrees and as a percentage "
            "of the 25° posture-warning reference."
        )
        self.eye_closure_label = self.create_metric(
            metrics_layout, 3, 0, "EYES CLOSED", "--"
        )
        self.pose_label = self.create_metric(
            metrics_layout, 3, 1, "PITCH / YAW / ROLL", "--/--/--"
        )
        self.pose_label.setMinimumWidth(120)
        self.pose_label.setStyleSheet("font-size:11px; font-weight:bold;")
        self.pose_label.setToolTip(
            "Head pitch / yaw / roll in degrees; after eye calibration, "
            "values show deviation from your neutral pose"
        )
        self.ear_label.parentWidget().setToolTip("Eye Aspect Ratio (EAR)")
        self.perclos_label.parentWidget().setToolTip(
            "Percentage of time eyes were closed in the past 15 seconds"
        )

        scene_controls = QtWidgets.QHBoxLayout()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Day", "Night"])
        self.weather_combo = QtWidgets.QComboBox()
        self.weather_combo.addItems(["Clear", "Rain", "Fog"])
        self.mode_combo.currentTextChanged.connect(self.update_scene_mode)
        self.weather_combo.currentTextChanged.connect(self.update_scene_mode)
        scene_controls.addWidget(QtWidgets.QLabel("Scene:"))
        scene_controls.addWidget(self.mode_combo)
        scene_controls.addWidget(self.weather_combo)
        scene_controls.addStretch()
        right_column.addLayout(scene_controls)
        right_column.addWidget(metrics_panel, 1)
        content.addLayout(right_column, 4)
        root.addLayout(content, 1)

        status_panel = QtWidgets.QFrame()
        status_panel.setObjectName("panel")
        status_layout = QtWidgets.QHBoxLayout(status_panel)
        self.level_label = QtWidgets.QLabel("ATTENTIVE")
        self.level_label.setStyleSheet(
            "color:#57d998; font-size:18px; font-weight:bold;"
        )
        self.alert_detail_label = QtWidgets.QLabel(
            "No warning · No vehicle control"
        )
        self.alert_detail_label.setObjectName("muted")
        self.alert_detail_label.setStyleSheet("font-size:10px;")
        status_layout.addWidget(self.level_label)
        status_layout.addSpacing(10)
        status_layout.addWidget(self.alert_detail_label, 1)
        status_layout.addWidget(self.response_label)
        root.addWidget(status_panel)

        bottom = QtWidgets.QHBoxLayout()
        bottom.setSpacing(8)
        events_panel = QtWidgets.QFrame()
        events_panel.setObjectName("panel")
        events_layout = QtWidgets.QVBoxLayout(events_panel)
        events_layout.setContentsMargins(8, 6, 8, 6)
        events_layout.setSpacing(5)
        events_title = QtWidgets.QLabel("LIVE EVENTS")
        events_title.setStyleSheet(
            "font-weight:bold; color:#8cc8ff; font-size:14px;"
        )
        self.event_list = QtWidgets.QListWidget()
        self.event_list.setMinimumHeight(115)
        self.event_list.setStyleSheet(
            "font-size:12px; background-color:#101927; "
            "border:1px solid #2b3b52; border-radius:8px; padding:4px;"
        )
        self.event_list.setWordWrap(True)
        events_layout.addWidget(events_title)
        events_layout.addWidget(self.event_list)
        self.session_stats_label = QtWidgets.QLabel(
            "Session: 0 warnings · 0 simulated stops"
        )
        self.session_stats_label.setObjectName("muted")
        self.session_stats_label.setStyleSheet(
            "color:#b4c4d8; font-size:10px; font-weight:bold;"
        )
        events_layout.addWidget(self.session_stats_label)
        self.session_summary_button = QtWidgets.QPushButton(
            "Session summary / Export JSON"
        )
        self.session_summary_button.clicked.connect(
            self.open_session_summary
        )
        events_layout.addWidget(self.session_summary_button)
        bottom.addWidget(events_panel, 1)

        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(5)
        self.parking_button = QtWidgets.QPushButton("Emergency park demo")
        self.parking_button.setToolTip(
            "Simulate Emergency Parking — visual software demo only"
        )
        self.parking_button.clicked.connect(
            lambda: self.demo_parking_requested.emit()
        )
        self.reset_simulation_button = QtWidgets.QPushButton("Reset scene")
        self.reset_simulation_button.setToolTip("Reset the simulated drive")
        self.reset_simulation_button.clicked.connect(self.reset_simulation)
        self.sound_button = QtWidgets.QPushButton("Sound: ON")
        self.sound_button.clicked.connect(self.toggle_sound)
        self.settings_button = QtWidgets.QPushButton("Settings / help")
        self.settings_button.clicked.connect(self.open_settings)
        self.reset_alert_button = QtWidgets.QPushButton("Reset alert state")
        self.reset_alert_button.clicked.connect(
            lambda: self.reset_alert_requested.emit()
        )
        self.scenario_combo = QtWidgets.QComboBox()
        self.scenario_combo.addItems(
            [
                "Normal attentive driving",
                "Mild drowsiness",
                "Prolonged eye closure",
                "Repeated yawning",
                "Head tilt",
                "Face tracking loss",
                "Critical alert escalation",
                "Unresponsive driver",
                "Recovery after opening eyes",
                "Emergency parking",
            ]
        )
        self.fast_test_checkbox = QtWidgets.QCheckBox("Accelerated test")
        self.fast_test_checkbox.setChecked(True)
        self.test_button = QtWidgets.QPushButton("Run test scenario")
        self.test_button.clicked.connect(self.start_selected_scenario)
        self.stop_test_button = QtWidgets.QPushButton("Stop test")
        self.stop_test_button.clicked.connect(
            lambda: self.scenario_stop_requested.emit()
        )
        controls.addWidget(self.parking_button, 0, 0)
        controls.addWidget(self.reset_simulation_button, 0, 1)
        controls.addWidget(self.scenario_combo, 1, 0, 1, 2)
        controls.addWidget(self.fast_test_checkbox, 2, 0, 1, 2)
        controls.addWidget(self.test_button, 3, 0)
        controls.addWidget(self.stop_test_button, 3, 1)
        controls.addWidget(self.sound_button, 4, 0)
        controls.addWidget(self.settings_button, 4, 1)
        controls.addWidget(self.reset_alert_button, 5, 0, 1, 2)
        bottom.setStretch(0, 3)
        bottom.setStretch(1, 2)
        bottom.addLayout(controls)
        root.addLayout(bottom)

        self.statusBar().showMessage(
            "F1: Help  |  F8: Sound test  |  Esc: Exit  |  No vehicle control"
        )
        self.shortcut_help = QtWidgets.QShortcut(QtCore.Qt.Key_F1, self)
        self.shortcut_help.activated.connect(self.show_help)
        self.shortcut_sound = QtWidgets.QShortcut(QtCore.Qt.Key_F8, self)
        self.shortcut_sound.activated.connect(self.test_sound)
        self.shortcut_escape = QtWidgets.QShortcut(QtCore.Qt.Key_Escape, self)
        self.shortcut_escape.activated.connect(self.close)
        for widget in self.findChildren(QtWidgets.QWidget):
            if isinstance(
                widget,
                (
                QtWidgets.QPushButton,
                QtWidgets.QComboBox,
                QtWidgets.QCheckBox,
                QtWidgets.QSpinBox,
                QtWidgets.QDoubleSpinBox,
                ),
            ):
                widget.setFocusPolicy(Qt.StrongFocus)

    def _style_for_accessibility(self, stylesheet):
        stylesheet = re.sub(
            r"font-size\s*:\s*(\d+(?:\.\d+)?)px",
            lambda match: (
                f"font-size:{max(9, round(float(match.group(1)) * self.text_scale))}px"
            ),
            stylesheet,
        )
        if not self.high_contrast_mode:
            return stylesheet

        stylesheet = re.sub(
            r"(?i)(background-color|background)\s*:\s*#[0-9a-f]{3,8}",
            r"\1:#000000",
            stylesheet,
        )
        stylesheet = re.sub(
            r"(?i)(?<![\w-])color\s*:\s*#[0-9a-f]{3,8}",
            "color:#ffffff",
            stylesheet,
        )
        return re.sub(
            r"(?i)(border(?:-[\w]+)?\s*:\s*)\d+px\s+solid\s+#[0-9a-f]{3,8}",
            r"\g<1>2px solid #ffffff",
            stylesheet,
        )

    def _apply_accessibility_styles(self):
        widgets = [self, *self.findChildren(QtWidgets.QWidget)]
        for widget in widgets:
            if not widget.property("driverguardBaseStyleCaptured"):
                widget.setProperty(
                    "driverguardBaseStyleSheet", widget.styleSheet()
                )
                widget.setProperty("driverguardBaseStyleCaptured", True)
            base_style = widget.property("driverguardBaseStyleSheet") or ""
            styled = self._style_for_accessibility(base_style)
            if widget.styleSheet() != styled:
                widget.setStyleSheet(styled)

    def _set_accessible_style(self, widget, stylesheet):
        widget.setProperty("driverguardBaseStyleSheet", stylesheet)
        widget.setProperty("driverguardBaseStyleCaptured", True)
        widget.setStyleSheet(self._style_for_accessibility(stylesheet))

    def apply_accessibility_settings(self, text_scale, high_contrast):
        self.text_scale = float(text_scale)
        self.high_contrast_mode = bool(high_contrast)
        self._apply_accessibility_styles()
        self.statusBar().showMessage(
            "Accessibility display settings applied", 3000
        )

    def create_metric(self, grid, row, column, title, value):
        panel = QtWidgets.QFrame()
        panel.setStyleSheet(
            "background-color:#101927; border:1px solid #28394f; "
            "border-radius:9px;"
        )
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(7, 2, 7, 2)
        layout.setSpacing(5)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("metricTitle")
        title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        value_label = QtWidgets.QLabel(value)
        value_label.setObjectName("metricValue")
        value_label.setMinimumWidth(72)
        value_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        panel.setToolTip(title)
        layout.addWidget(title_label, 1)
        layout.addWidget(value_label)
        grid.addWidget(panel, row, column)
        return value_label

    def update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%d %b %Y  |  %I:%M:%S %p"))

    def _clock_now(self):
        now = time.monotonic()
        if self._test_clock_started is None:
            return now
        return now + (now - self._test_clock_started) * (
            self._test_clock_scale - 1.0
        )

    def open_tracking_check(self):
        if (
            not self.camera_active
            or self.camera_paused
            or self.mock_test_active
        ):
            self.statusBar().showMessage(
                "Use a live, active webcam (not a simulated test) to check tracking",
                4000,
            )
            return
        if self.tracking_check_started_at is not None:
            self.tracking_check_dialog.raise_()
            self.tracking_check_dialog.activateWindow()
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Face and eye tracking check")
        dialog.setModal(False)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(dialog)
        self.tracking_check_prompt = QtWidgets.QLabel()
        self.tracking_check_prompt.setWordWrap(True)
        self.tracking_check_progress = QtWidgets.QProgressBar()
        self.tracking_check_progress.setRange(0, 100)
        self.tracking_check_coverage = QtWidgets.QLabel()
        self.tracking_check_coverage.setWordWrap(True)
        self.tracking_check_report = QtWidgets.QLabel()
        self.tracking_check_report.setWordWrap(True)
        self.tracking_check_report.hide()
        self.tracking_check_close_button = QtWidgets.QPushButton(
            "Cancel check"
        )
        self.tracking_check_close_button.clicked.connect(
            self._tracking_check_dialog_button
        )
        layout.addWidget(self.tracking_check_prompt)
        layout.addWidget(self.tracking_check_progress)
        layout.addWidget(self.tracking_check_coverage)
        layout.addWidget(self.tracking_check_report)
        layout.addWidget(self.tracking_check_close_button)
        dialog.finished.connect(self._tracking_check_dialog_finished)

        self.tracking_check_dialog = dialog
        self.tracking_check_started_at = time.monotonic()
        self.tracking_check_samples = [
            {"frames": 0, "tracked": 0, "pose": 0}
            for _ in self.TRACKING_CHECK_STAGES
        ]
        self.tracking_check_timer.start()
        self._update_tracking_check_progress()
        dialog.show()
        self._apply_accessibility_styles()

    def _record_tracking_check_sample(
        self, ear, head_pitch, head_yaw, head_roll, tracking_reliable
    ):
        if self.tracking_check_started_at is None:
            return
        elapsed = time.monotonic() - self.tracking_check_started_at
        total_duration = (
            self.TRACKING_CHECK_STAGE_SECONDS
            * len(self.TRACKING_CHECK_STAGES)
        )
        if elapsed >= total_duration:
            self._finish_tracking_check()
            return
        stage_index = min(
            int(elapsed / self.TRACKING_CHECK_STAGE_SECONDS),
            len(self.tracking_check_samples) - 1,
        )
        counts = self.tracking_check_samples[stage_index]
        counts["frames"] += 1
        has_eye_measurement = tracking_reliable and ear is not None
        counts["tracked"] += int(has_eye_measurement)
        has_pose = has_eye_measurement and all(
            value is not None for value in (head_pitch, head_yaw, head_roll)
        )
        counts["pose"] += int(has_pose)

    def _update_tracking_check_progress(self):
        if self.tracking_check_started_at is None:
            return
        elapsed = max(0.0, time.monotonic() - self.tracking_check_started_at)
        total_duration = (
            self.TRACKING_CHECK_STAGE_SECONDS
            * len(self.TRACKING_CHECK_STAGES)
        )
        if elapsed >= total_duration:
            self._finish_tracking_check()
            return
        stage_index = min(
            int(elapsed / self.TRACKING_CHECK_STAGE_SECONDS),
            len(self.TRACKING_CHECK_STAGES) - 1,
        )
        stage_counts = self.tracking_check_samples[stage_index]
        if stage_counts["frames"]:
            coverage = (
                100 * stage_counts["tracked"] / stage_counts["frames"]
            )
            observed = (
                f"Face/eye tracking this step: {coverage:.0f}% "
                f"({stage_counts['tracked']}/{stage_counts['frames']} frames)"
            )
        else:
            observed = "Waiting for camera measurements…"
        self.tracking_check_prompt.setText(
            f"Step {stage_index + 1}/{len(self.TRACKING_CHECK_STAGES)}\n"
            f"{self.TRACKING_CHECK_STAGES[stage_index]}"
        )
        self.tracking_check_progress.setValue(
            int(100 * elapsed / total_duration)
        )
        self.tracking_check_coverage.setText(observed)

    def _finish_tracking_check(self):
        if self.tracking_check_started_at is None:
            return
        duration_seconds = max(
            0.0, time.monotonic() - self.tracking_check_started_at
        )
        self.tracking_check_timer.stop()
        self.tracking_check_started_at = None
        total_frames = sum(
            counts["frames"] for counts in self.tracking_check_samples
        )
        tracked_frames = sum(
            counts["tracked"] for counts in self.tracking_check_samples
        )
        stages = []
        for index, counts in enumerate(self.tracking_check_samples):
            frames = counts["frames"]
            stages.append(
                {
                    "step": self.TRACKING_CHECK_STAGES[index],
                    "frames": frames,
                    "reliable_face_eye_frames": counts["tracked"],
                    "face_eye_coverage_percent": (
                        round(100 * counts["tracked"] / frames, 1)
                        if frames
                        else None
                    ),
                    "pose_landmark_coverage_percent": (
                        round(100 * counts["pose"] / frames, 1)
                        if frames
                        else None
                    ),
                }
            )
        self.completed_tracking_check = {
            "completed_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "duration_seconds": round(duration_seconds, 1),
            "frames": total_frames,
            "reliable_face_eye_frames": tracked_frames,
            "face_eye_coverage_percent": (
                round(100 * tracked_frames / total_frames, 1)
                if total_frames
                else None
            ),
            "stages": stages,
        }
        if total_frames:
            total_coverage = 100 * tracked_frames / total_frames
            overall = (
                f"Overall face/eye tracking observed: {total_coverage:.0f}% "
                f"({tracked_frames}/{total_frames} frames)."
            )
        else:
            overall = (
                "No camera measurements were received during the check. "
                "Confirm the webcam is active and retry."
            )

        stage_results = []
        for index, stage in enumerate(stages):
            if stage["frames"]:
                coverage = stage["face_eye_coverage_percent"]
                pose = stage["pose_landmark_coverage_percent"]
                pose_display = (
                    f"{pose:.0f}%" if pose is not None else "n/a"
                )
                result = (
                    f"{index + 1}. {self.TRACKING_CHECK_STAGES[index]} "
                    f"Face/eyes {coverage:.0f}% · "
                    f"pose landmarks {pose_display} "
                    f"({stage['frames']} frames)"
                )
            else:
                result = (
                    f"{index + 1}. {self.TRACKING_CHECK_STAGES[index]} "
                    "No measurements received"
                )
            stage_results.append(result)

        self.tracking_check_progress.setValue(100)
        self.tracking_check_prompt.setText(
            "Tracking check complete. Use the stage results to see which "
            "movement or position needs better lighting/framing."
        )
        self.tracking_check_coverage.clear()
        self.tracking_check_report.setText(
            f"{overall}\n" + "\n".join(stage_results)
            + "\nDiagnostic only — this short check does not validate safety. "
            "No images are saved."
        )
        self.tracking_check_report.show()
        self.tracking_check_close_button.setText("Close report")
        self.statusBar().showMessage("Tracking check complete", 4000)

    def _tracking_check_dialog_button(self):
        if self.tracking_check_started_at is not None:
            self.tracking_check_timer.stop()
            self.tracking_check_started_at = None
            self.statusBar().showMessage("Tracking check cancelled", 3000)
            if self.tracking_check_dialog is not None:
                self.tracking_check_dialog.reject()
            return
        if self.tracking_check_dialog is not None:
            self.tracking_check_dialog.accept()

    def _tracking_check_dialog_finished(self, result):
        del result
        self.tracking_check_timer.stop()
        self.tracking_check_started_at = None
        self.tracking_check_dialog = None

    def _cancel_tracking_check(self):
        if self.tracking_check_started_at is None:
            return
        self.tracking_check_timer.stop()
        self.tracking_check_started_at = None
        if self.tracking_check_dialog is not None:
            self.tracking_check_dialog.reject()

    def update_map_frame(self, q_img):
        if q_img is None or q_img.isNull():
            return
        if self.camera_preview_hidden:
            return
        self.latest_camera_image = q_img
        self._fit_camera_image()

    def update_calibration_progress(self, prompt, elapsed_seconds):
        self.calibration_hide_timer.stop()
        self.calibration_label.setText(prompt)
        self.calibration_label.setStyleSheet(
            "color:#ffd43b; font-size:10px; font-weight:bold;"
        )
        self.calibration_progress_bar.setValue(elapsed_seconds)
        self.calibration_label.show()
        self.calibration_progress_bar.show()
        self.calibrate_button.setEnabled(False)

    def finish_calibration(self, message, success):
        self.calibration_label.setText(message)
        color = "#57d998" if success else "#ff9f1c"
        self.calibration_label.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:bold;"
        )
        self.calibration_progress_bar.setValue(60)
        self.calibrate_button.setEnabled(True)
        self.calibration_hide_timer.start(12000)

    def _hide_calibration_status(self):
        self.calibration_label.hide()
        self.calibration_progress_bar.hide()

    def _fit_camera_image(self):
        if self.camera_preview_hidden or self.latest_camera_image is None:
            return
        if self.camera_label.width() <= 0 or self.camera_label.height() <= 0:
            return
        pixmap = QPixmap.fromImage(self.latest_camera_image)
        fitted = pixmap.scaled(
            self.camera_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.camera_label.setPixmap(fitted)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_camera_image()

    def set_tracking_status(self, message, color="#99abc1"):
        display_messages = {
            "Webcam stopped": "WEBCAM STOPPED",
            "Camera paused": "CAMERA PAUSED",
            "Camera active — looking for a face": "LOOKING FOR FACE",
            "Camera unavailable — simulation only": "CAMERA UNAVAILABLE",
            "Camera frame unavailable — retrying": "CAMERA FRAME LOST · RETRYING",
            "Calibration unavailable — webcam not active": "START CAMERA TO CALIBRATE",
            "Personal calibration in progress":
                "PERSONAL CALIBRATION · FOLLOW PROMPT",
            "Start the webcam before resuming": "START CAMERA TO RESUME",
        }
        display_message = display_messages.get(message)
        if display_message is None and message.startswith("Face tracked"):
            display_message = "FACE TRACKED"
        elif display_message is None and message.startswith("Face / eyes"):
            display_message = "TRACKING UNCERTAIN"
        elif display_message is None and message.startswith("Calibrating"):
            display_message = "CALIBRATING · LOOK STRAIGHT AHEAD"
        self.tracking_label.setText(display_message or message)
        self.tracking_label.setToolTip(message)
        self._set_accessible_style(
            self.tracking_label, f"color:{color}; font-weight:bold;"
        )

    def camera_state_changed(self, active):
        self.camera_active = bool(active)
        self.camera_start_button.setEnabled(not active)
        self.camera_pause_button.setEnabled(active and not self.camera_paused)
        self.camera_resume_button.setEnabled(active and self.camera_paused)
        self.camera_stop_button.setEnabled(active)
        if not active:
            self._cancel_tracking_check()
        if not active:
            self.tracking_prompted = False
            self.tracking_prompt_since = None
        if not active:
            self.camera_paused = False
            self.calibrate_button.setEnabled(True)
            self.calibration_hide_timer.stop()
            self._hide_calibration_status()
            self.latest_camera_image = None
            self.camera_label.setPixmap(QPixmap())
            self.camera_label.setText(
                "Camera preview hidden · webcam stopped"
                if self.camera_preview_hidden
                else "Webcam stopped"
            )
            self._show_unknown_camera_metrics()
        elif self.camera_preview_hidden:
            self.latest_camera_image = None
            self.camera_label.setPixmap(QPixmap())
            self.camera_label.setText(
                "Camera preview hidden\n"
                "Local analysis is still active · Stop webcam to stop capture"
            )

    def set_camera_preview_hidden(self, hidden):
        self.camera_preview_hidden = bool(hidden)
        self.latest_camera_image = None
        self.camera_label.setPixmap(QPixmap())
        if self.camera_preview_hidden:
            status = (
                "Camera preview hidden\n"
                "Local analysis is still active · Stop webcam to stop capture"
                if self.camera_active and not self.camera_paused
                else "Camera preview hidden · webcam is not analyzing"
            )
            self.camera_label.setText(status)
        elif self.camera_paused:
            self.camera_label.setText("Camera paused")
        elif self.camera_active:
            self.camera_label.setText("Waiting for next webcam frame")
        else:
            self.camera_label.setText("Webcam stopped")

    def _show_unknown_camera_metrics(self):
        if self.mock_test_active:
            return
        self.update_detection(
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

    def request_camera_pause(self):
        self.camera_paused = True
        self._cancel_tracking_check()
        self.tracking_prompt_since = None
        self.camera_pause_requested.emit()
        self.camera_pause_button.setEnabled(False)
        self.camera_resume_button.setEnabled(True)
        self.latest_camera_image = None
        self.camera_label.setPixmap(QPixmap())
        self.camera_label.setText(
            "Camera preview hidden · camera paused"
            if self.camera_preview_hidden
            else "Camera paused"
        )
        self._show_unknown_camera_metrics()

    def request_camera_resume(self):
        self.camera_paused = False
        self.camera_resume_requested.emit()
        self.camera_pause_button.setEnabled(True)
        self.camera_resume_button.setEnabled(False)
        self.camera_label.setText(
            "Camera preview hidden\n"
            "Local analysis is still active · Stop webcam to stop capture"
            if self.camera_preview_hidden
            else "Waiting for next webcam frame"
        )

    def update_scene_mode(self, *_):
        self.drive_simulation.set_drive_mode(
            self.mode_combo.currentText(), self.weather_combo.currentText()
        )

    def start_selected_scenario(self):
        self._cancel_tracking_check()
        if self.mock_test_active:
            self.scenario_stop_requested.emit()
        fast = self.fast_test_checkbox.isChecked()
        self.scenario_requested.emit(self.scenario_combo.currentText(), fast)

    def set_response_status(self, message):
        display_messages = {
            "no active warning": "Response: waiting",
            "please respond to warning": "Response needed",
            "Response received": "Response received",
            "alert state reset": "Alert reset",
        }
        self.response_label.setText(
            display_messages.get(message, f"Response: {message}")
        )
        self.response_label.setToolTip(f"Driver response: {message}")

    def update_detection(
        self,
        ear,
        perclos,
        head_angle,
        head_pitch,
        head_yaw,
        head_roll,
        blink_rate,
        mouth_aperture,
        yawn_count,
        closed_duration,
        tracking_reliable,
        calibrated,
        calibrating,
        drowsiness_level,
        yawn_duration=0.0,
        pose_calibrated=False,
        ear_baseline=None,
        eye_closure_threshold=None,
        tracking_guidance=None,
        speech_active=False,
    ):
        self._record_tracking_check_sample(
            ear,
            head_pitch,
            head_yaw,
            head_roll,
            tracking_reliable,
        )
        if self.camera_active and not self.mock_test_active:
            self.live_tracking_samples += 1
            if tracking_reliable and ear is not None:
                self.reliable_tracking_samples += 1
        if not self.mock_test_active and calibrated and pose_calibrated:
            self.personal_calibration_completed = True
        if tracking_guidance:
            self.quality_guidance_label.setText(
                f"CAMERA CHECK  ·  {tracking_guidance}"
            )
            self.quality_guidance_label.setToolTip(tracking_guidance)
            self.quality_guidance_label.show()
        else:
            self.quality_guidance_label.clear()
            self.quality_guidance_label.hide()
        if tracking_reliable:
            self.tracking_prompted = False
            self.tracking_prompt_since = None
        else:
            self._update_tracking_prompt(
                tracking_guidance,
                not self.mock_test_active
                and self.camera_start_button.isEnabled() is False,
            )
        self.latest_tracking_reliable = tracking_reliable
        self.latest_drowsiness_level = drowsiness_level
        self.latest_critical = (
            tracking_reliable and closed_duration > self.critical_eye_seconds
        )
        self.ear_label.setText(
            "--" if not tracking_reliable or ear is None else f"{ear:.3f}"
        )
        ear_tooltip = "Live Eye Aspect Ratio (EAR)."
        if ear_baseline is not None and eye_closure_threshold is not None:
            ear_tooltip += (
                f" Personal open-eye baseline: {ear_baseline:.3f}; "
                f"current closure threshold: {eye_closure_threshold:.3f}."
            )
        else:
            ear_tooltip += " Run the one-minute calibration to personalize it."
        self.ear_label.parentWidget().setToolTip(ear_tooltip)
        self.ear_label.setToolTip(ear_tooltip)
        self.perclos_label.setText(
            "--"
            if not tracking_reliable or perclos is None
            else f"{perclos:.0f}%"
        )
        self.head_angle_label.setText(
            "--"
            if not tracking_reliable or head_angle is None
            else f"{head_angle:.0f}° / {min(100, head_angle / 25 * 100):.0f}%"
        )
        self.eye_closure_label.setText(
            f"{closed_duration:.0f}s" if tracking_reliable else "--"
        )
        if tracking_reliable:
            self.blink_label.setText(f"{blink_rate:.0f}")
            self.yawn_label.setText(str(yawn_count))
            self.mouth_label.setText(
                "--"
                if mouth_aperture is None
                else f"{mouth_aperture:.2f}"
            )
            self.mouth_label.setToolTip(
                "Repeated open/close mouth motion looks like conversation; "
                "yawn warnings are suppressed."
                if speech_active
                else "Mouth aperture ratio"
            )
        else:
            self.blink_label.setText("--")
            self.yawn_label.setText("--")
            self.mouth_label.setText("--")
        if tracking_reliable and all(
            value is not None for value in (head_pitch, head_yaw, head_roll)
        ):
            self.pose_label.setText(
                f"{head_pitch:.0f}/{head_yaw:.0f}/{head_roll:.0f}"
            )
        else:
            self.pose_label.setText("--/--/--")
        if calibrating:
            self.set_tracking_status(
                "Personal calibration running — follow the on-screen prompts",
                "#ffd43b",
            )
        elif tracking_reliable:
            if calibrated and pose_calibrated:
                calibration_text = "personal eye ratio + usual posture learned"
            elif calibrated:
                calibration_text = "eyes calibrated · usual posture not captured"
            else:
                calibration_text = "calibrate personal eyes + usual posture"
            self.set_tracking_status(
                f"Face tracked · {calibration_text}", "#57d998"
            )
        else:
            self.set_tracking_status(
                "Face / eyes not tracked reliably — drowsiness is unknown",
                "#ff9f1c",
            )
            self.parking_triggered = False

        if self.mock_test_active:
            self.source_label.setText(
                "SIMULATED TEST"
            )
            self._set_accessible_style(
                self.source_label,
                "color:#ffd43b; font-size:10px; font-weight:bold;"
            )
        elif tracking_reliable:
            self.source_label.setText("LIVE WEBCAM")
            self._set_accessible_style(
                self.source_label,
                "color:#57d998; font-size:10px; font-weight:bold;"
            )
        else:
            self.source_label.setText(
                "NO LIVE DATA"
            )
            self._set_accessible_style(
                self.source_label,
                "color:#ffb74d; font-size:10px; font-weight:bold;"
            )

        if not tracking_reliable:
            self.level_label.setText("TRACKING UNCERTAIN")
            self._set_accessible_style(
                self.level_label,
                "color:#ffb74d; font-size:18px; font-weight:bold;"
            )
            self.alert_detail_label.setText(
                "Adjust lighting/position · eyes unknown"
            )
            self.update_alert_state("None", False)
            return

        critical = closed_duration > self.critical_eye_seconds
        if critical:
            self.level_label.setText("CRITICAL EYE CLOSURE")
            self._set_accessible_style(
                self.level_label,
                "color:#ff4545; font-size:16px; font-weight:bold;"
            )
            self.alert_detail_label.setText(
                f"Eyes closed {closed_duration:.0f}s · urgent beeps active"
            )
        else:
            level_colors = {
                "None": "#57d998",
                "Level 1": "#ffd43b",
                "Level 2": "#ff9f1c",
                "Level 3": "#ff5555",
            }
            labels = {
                "None": "ATTENTIVE",
                "Level 1": "CAUTION",
                "Level 2": "HIGH RISK",
                "Level 3": "SEVERE",
            }
            self.level_label.setText(labels.get(drowsiness_level, drowsiness_level))
            self._set_accessible_style(
                self.level_label,
                "color:{}; font-size:18px; font-weight:bold;".format(
                    level_colors.get(drowsiness_level, "#e8eef7")
                )
            )
            self.alert_detail_label.setText(
                "Eyes {:.0f}s · yawn {:.0f}s · head {}°".format(
                    closed_duration,
                    yawn_duration,
                    "--" if head_angle is None else f"{head_angle:.0f}",
                )
            )

        self.update_alert_state(drowsiness_level, critical)
        if drowsiness_level == "None" and not critical:
            self.parking_triggered = False
            self.unresponsive_since = None

        closure_timeout = closed_duration > self.parking_seconds
        response_timeout = (
            self.unresponsive_since is not None
            and self._clock_now() - self.unresponsive_since
            > self.parking_seconds
        )
        if (
            (closure_timeout or response_timeout)
            and not self.parking_triggered
        ):
            self.begin_automatic_parking()

    def update_alert_state(self, level, critical):
        alert_key = (level, critical)
        if alert_key == self.last_alert_key:
            return

        previous_key = self.last_alert_key
        self.last_alert_key = alert_key
        if level == "None" and not critical:
            self.unresponsive_since = None
            self.current_alert_critical = False
            self.set_response_status("no active warning")
            self.sound_timer.stop()
            if previous_key is not None and previous_key != ("None", False):
                self.add_event("Alert cleared — normal tracking resumed")
            return

        if previous_key in (None, ("None", False)):
            self.unresponsive_since = self._clock_now()
        self.set_response_status("please respond to warning")
        interval = self.critical_repeat_ms if critical else {
            "Level 1": 3000,
            "Level 2": 1400,
            "Level 3": 850,
        }.get(level, 2500)
        self.current_alert_interval = interval
        self.current_alert_critical = critical
        self.sound_timer.start(interval)
        self.play_alert_beep()
        if critical:
            self.add_event(
                f"{self.critical_eye_seconds:g}-second eye-closure threshold — "
                "urgent beeps active"
            )
        elif level in ("Level 1", "Level 2", "Level 3"):
            self.add_event(f"Drowsiness warning escalated to {level}")

    def note_driver_response(self):
        self.set_response_status("Response received")
        if self.last_alert_key not in (None, ("None", False)):
            self.unresponsive_since = self._clock_now()
            self.add_event("Driver acknowledged warning; response timer restarted")
        else:
            self.add_event("Driver response recorded — no active warning")

    def reset_alert_state(self):
        if (
            not self.latest_tracking_reliable
            or self.latest_drowsiness_level != "None"
            or self.latest_critical
        ):
            self.statusBar().showMessage(
                "Cannot reset while risk is active or tracking is uncertain",
                4000,
            )
            return
        self.sound_timer.stop()
        self.last_alert_key = ("None", False)
        self.unresponsive_since = None
        self.parking_triggered = False
        self.set_response_status("alert state reset")
        self.add_event("Alert state reset after recovery")

    def begin_automatic_parking(self):
        self.parking_triggered = True
        if self.drive_simulation.state in ("Driving",):
            self.add_event(
                "Emergency Parking Simulation Started — unresponsive timeout"
            )
            self.drive_simulation.start_parking_demo()

    def play_alert_beep(self):
        if not self.sound_enabled:
            return
        alert_level = (
            self.last_alert_key[0]
            if self.last_alert_key not in (None, ("None", False))
            else "Level 2"
        )
        if self.current_alert_critical:
            pattern = [(1500, 220), (1850, 220), (2100, 220)]
            amplitude = 0.82
        elif alert_level == "Level 3":
            pattern = [(1300, 150), (1650, 150), (1950, 150)]
            amplitude = 0.68
        elif alert_level == "Level 2":
            pattern = [(1100, 180), (1450, 180)]
            amplitude = 0.45
        else:
            pattern = [(900, 240)]
            amplitude = 0.25
        try:
            import winsound
        except ImportError:
            QtWidgets.QApplication.beep()
            return
        threading.Thread(
            target=self._play_windows_beep,
            args=(pattern, amplitude, winsound),
            daemon=True,
        ).start()

    def _update_tracking_prompt(self, guidance, camera_running):
        guidance_text = (guidance or "").lower()
        needs_reframing = guidance_text.startswith(
            (
                "face not found:",
                "face/eyes too small or partly out of frame:",
            )
        )
        if (
            not camera_running
            or not needs_reframing
            or self.mock_test_active
        ):
            self.tracking_prompt_since = None
            return
        if self.tracking_prompt_since is None:
            self.tracking_prompt_since = time.monotonic()
            return
        if (
            time.monotonic() - self.tracking_prompt_since
            >= self.TRACKING_PROMPT_GRACE_SECONDS
        ):
            self._request_tracking_voice_prompt()

    def _request_tracking_voice_prompt(self):
        if not self.sound_enabled or self.tracking_prompted:
            return
        self.tracking_prompted = True
        self.tracking_prompt_since = None
        self.add_event(
            "Camera framing reminder spoken twice after sustained face loss"
        )
        threading.Thread(
            target=self._speak_tracking_voice_prompt,
            daemon=True,
        ).start()

    def _speak_tracking_voice_prompt(self):
        if not self.tracking_prompt_lock.acquire(blocking=False):
            return
        try:
            script = (
                "$ErrorActionPreference='Stop'; "
                "Add-Type -AssemblyName System.Speech; "
                "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$speaker.Volume=100; "
                "$speaker.Speak('Please set the camera properly.'); "
                "Start-Sleep -Milliseconds 350; "
                "$speaker.Speak('Please set the camera properly.'); "
                "$speaker.Dispose()"
            )
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or "Windows speech synthesis failed"
                self.audio_error.emit(
                    f"Camera guidance speech unavailable: {detail}"
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            self.audio_error.emit(
                f"Camera guidance speech unavailable: {error}"
            )
        finally:
            self.tracking_prompt_lock.release()

    @staticmethod
    def _build_alert_wave(pattern, amplitude):
        sample_rate = 22050
        samples = array.array("h")
        fade_samples = int(sample_rate * 0.005)
        for tone_index, (frequency, duration_ms) in enumerate(pattern):
            sample_count = int(sample_rate * duration_ms / 1000)
            for index in range(sample_count):
                envelope = min(
                    1.0,
                    index / max(1, fade_samples),
                    (sample_count - index - 1) / max(1, fade_samples),
                )
                value = amplitude * envelope * math.sin(
                    2.0 * math.pi * frequency * index / sample_rate
                )
                samples.append(round(32767 * value))
            if tone_index < len(pattern) - 1:
                samples.extend(array.array("h", [0]) * int(sample_rate * 0.08))

        if sys.byteorder != "little":
            samples.byteswap()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(samples.tobytes())
        return buffer.getvalue()

    def _play_windows_beep(self, pattern, amplitude, winsound):
        if not self.audio_lock.acquire(blocking=False):
            return
        try:
            audio = self._build_alert_wave(pattern, amplitude)
            winsound.PlaySound(audio, winsound.SND_MEMORY)
        except (OSError, RuntimeError) as error:
            self.audio_error.emit(f"Warning audio unavailable: {error}")
        finally:
            self.audio_lock.release()

    def add_event(self, message):
        event_time = datetime.now().astimezone()
        item = QtWidgets.QListWidgetItem(
            f"{event_time.strftime('%H:%M:%S')}  {message}"
        )
        item.setToolTip(message)
        self.event_list.insertItem(0, item)
        while self.event_list.count() > 8:
            self.event_list.takeItem(self.event_list.count() - 1)
        self.event_history.append(
            {
                "timestamp": event_time.isoformat(timespec="seconds"),
                "message": message,
            }
        )
        if len(self.event_history) > self.MAX_SESSION_EVENTS:
            del self.event_history[0]
            self.event_history_truncated = True
        if "warning" in message.lower() or "threshold" in message.lower():
            self.warning_count += 1
        self._update_session_stats()

    def _update_session_stats(self):
        self.session_stats_label.setText(
            f"Session: {self.warning_count} warnings · "
            f"{self.simulation_count} simulated stops"
        )

    def clear_session_history(self):
        self.event_list.clear()
        self.event_history.clear()
        self.event_history_truncated = False
        self.warning_count = 0
        self.simulation_count = 0
        self.live_tracking_samples = 0
        self.reliable_tracking_samples = 0
        self.completed_tracking_check = None
        self.tracking_check_samples = []
        self._cancel_tracking_check()
        self.personal_calibration_completed = False
        self.session_started_at = datetime.now().astimezone()
        self.session_started_monotonic = time.monotonic()
        self._update_session_stats()
        self.statusBar().showMessage(
            "In-memory session history cleared", 3000
        )

    def confirm_clear_session_history(self):
        answer = QtWidgets.QMessageBox.question(
            self,
            "Clear session history?",
            "This removes the current in-memory event list and session "
            "counters. This action cannot be undone.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer == QtWidgets.QMessageBox.Yes:
            self.clear_session_history()

    def build_session_summary(self):
        tracking_coverage = (
            round(
                100 * self.reliable_tracking_samples
                / self.live_tracking_samples,
                1,
            )
            if self.live_tracking_samples
            else None
        )
        return {
            "schema_version": 1,
            "session_started_at": self.session_started_at.isoformat(
                timespec="seconds"
            ),
            "generated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "duration_seconds": round(
                time.monotonic() - self.session_started_monotonic, 1
            ),
            "summary": {
                "warnings": self.warning_count,
                "simulated_stops": self.simulation_count,
            },
            "live_tracking": {
                "samples": self.live_tracking_samples,
                "reliable_face_eye_samples": self.reliable_tracking_samples,
                "face_eye_coverage_percent": tracking_coverage,
            },
            "personalized_eye_posture_calibration_completed": (
                self.personal_calibration_completed
            ),
            "latest_guided_tracking_check": self.completed_tracking_check,
            "events": list(self.event_history),
            "event_history_truncated": self.event_history_truncated,
            "privacy": {
                "contains_camera_images_or_video": False,
                "contains_raw_facial_measurements": False,
                "exported_only_after_user_action": True,
            },
        }

    @staticmethod
    def _format_session_summary(summary):
        live_tracking = summary["live_tracking"]
        coverage = live_tracking["face_eye_coverage_percent"]
        coverage_text = (
            f"{coverage:.1f}%"
            if coverage is not None
            else "not available (no live samples)"
        )
        lines = [
            "DRIVERGUARD SESSION SUMMARY",
            f"Started: {summary['session_started_at']}",
            f"Snapshot created: {summary['generated_at']}",
            f"Duration: {summary['duration_seconds']:.1f} seconds",
            "",
            f"Warnings: {summary['summary']['warnings']}",
            f"Simulated stops: {summary['summary']['simulated_stops']}",
            (
                "Personalized eye/posture calibration: "
                + (
                    "complete"
                    if summary[
                        "personalized_eye_posture_calibration_completed"
                    ]
                    else "not complete"
                )
            ),
            (
                f"Live face/eye tracking coverage: {coverage_text} "
                f"({live_tracking['reliable_face_eye_samples']}/"
                f"{live_tracking['samples']} samples)"
            ),
            "",
            "LATEST GUIDED TRACKING CHECK",
        ]
        check = summary["latest_guided_tracking_check"]
        if check is None:
            lines.append("No completed guided tracking check.")
        else:
            check_coverage = check["face_eye_coverage_percent"]
            lines.append(
                "Face/eye coverage: "
                + (
                    f"{check_coverage:.1f}%"
                    if check_coverage is not None
                    else "not available"
                )
            )
            for stage in check["stages"]:
                stage_coverage = stage["face_eye_coverage_percent"]
                pose_coverage = stage[
                    "pose_landmark_coverage_percent"
                ]
                coverage_label = (
                    f"{stage_coverage:.1f}%"
                    if stage_coverage is not None
                    else "not available"
                )
                pose_label = (
                    f"{pose_coverage:.1f}%"
                    if pose_coverage is not None
                    else "not available"
                )
                lines.append(
                    f"- {stage['step']}: face/eyes {coverage_label}, "
                    f"pose {pose_label} "
                    f"({stage['reliable_face_eye_frames']}/"
                    f"{stage['frames']} frames)"
                )
        lines.extend(("", "TIMESTAMPED EVENTS"))
        if summary["event_history_truncated"]:
            lines.append(
                f"History is limited to the most recent "
                f"{HMIWindow.MAX_SESSION_EVENTS} events."
            )
        if summary["events"]:
            for event in reversed(summary["events"]):
                lines.append(
                    f"{event['timestamp']}  {event['message']}"
                )
        else:
            lines.append("No events recorded.")
        lines.extend(
            (
                "",
                "Diagnostic summary only; not a safety certification.",
                "No camera images, video, or raw facial measurements are included.",
            )
        )
        return "\n".join(lines)

    def open_session_summary(self):
        summary = self.build_session_summary()
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Session summary")
        dialog.setModal(False)
        layout = QtWidgets.QVBoxLayout(dialog)
        summary_text = QtWidgets.QPlainTextEdit()
        summary_text.setReadOnly(True)
        summary_text.setPlainText(self._format_session_summary(summary))
        export_button = QtWidgets.QPushButton("Export summary as JSON…")
        export_button.clicked.connect(
            lambda: self.export_session_summary(summary)
        )
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(summary_text)
        layout.addWidget(export_button)
        layout.addWidget(close_button)
        dialog.resize(720, 560)
        dialog.show()
        self._apply_accessibility_styles()

    def export_session_summary(self, summary):
        default_name = (
            "DriverGuard-session-"
            f"{datetime.now():%Y%m%d-%H%M%S}.json"
        )
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export session summary",
            default_name,
            "JSON files (*.json)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as output:
                json.dump(summary, output, ensure_ascii=False, indent=2)
                output.write("\n")
        except OSError as error:
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                f"Could not write the session summary: {error}",
            )
            return
        self.statusBar().showMessage(
            f"Session summary exported to {file_path}", 6000
        )

    def on_simulation_state_changed(self, state):
        if state == "Hazards on":
            self.add_event("Simulation: hazard lights activated")
        elif state == "Pulling over":
            self.add_event("Simulation: vehicle moving to roadside")
        elif state == "Parked":
            self.add_event("Vehicle Stopped — Simulation Complete")
            self.simulation_count += 1
            self.session_stats_label.setText(
                f"Session: {self.warning_count} warnings · "
                f"{self.simulation_count} simulated stops"
            )

    def reset_simulation(self):
        self.drive_simulation.reset_simulation()
        self.parking_triggered = False
        self.unresponsive_since = (
            self._clock_now()
            if self.last_alert_key not in (None, ("None", False))
            else None
        )
        self.add_event("Drive simulation reset")

    def toggle_sound(self):
        self.set_sound_enabled(not self.sound_enabled)
        self.statusBar().showMessage(
            "Warning sound enabled" if self.sound_enabled else "Warning sound muted",
            3000,
        )

    def open_settings(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Safety monitor settings")
        dialog.setModal(False)
        layout = QtWidgets.QVBoxLayout(dialog)
        form = QtWidgets.QFormLayout()
        sensitivity = QtWidgets.QDoubleSpinBox()
        sensitivity.setRange(0.5, 1.5)
        sensitivity.setSingleStep(0.1)
        sensitivity.setValue(self.sensitivity)
        blink_threshold = QtWidgets.QDoubleSpinBox()
        blink_threshold.setRange(10, 80)
        blink_threshold.setSuffix(" blinks/min")
        blink_threshold.setValue(self.blink_threshold)
        yawn_threshold = QtWidgets.QSpinBox()
        yawn_threshold.setRange(1, 10)
        yawn_threshold.setSuffix(" yawns/min")
        yawn_threshold.setValue(self.yawn_threshold)
        eye_seconds = QtWidgets.QDoubleSpinBox()
        eye_seconds.setRange(1, 120)
        eye_seconds.setSuffix(" seconds")
        eye_seconds.setValue(self.critical_eye_seconds)
        parking_seconds = QtWidgets.QDoubleSpinBox()
        parking_seconds.setRange(2, 180)
        parking_seconds.setSuffix(" seconds")
        parking_seconds.setValue(self.parking_seconds)
        repeat_ms = QtWidgets.QSpinBox()
        repeat_ms.setRange(800, 5000)
        repeat_ms.setSuffix(" ms")
        repeat_ms.setValue(self.critical_repeat_ms)
        text_size = QtWidgets.QComboBox()
        text_sizes = (
            ("Standard", 1.0),
            ("Large (115%)", 1.15),
            ("Extra large (130%)", 1.3),
        )
        for label, scale in text_sizes:
            text_size.addItem(label, scale)
        text_size.setCurrentIndex(
            max(0, text_size.findData(self.text_scale))
        )
        high_contrast = QtWidgets.QCheckBox("Use high-contrast colors")
        high_contrast.setChecked(self.high_contrast_mode)
        text_size.currentIndexChanged.connect(
            lambda index: self.apply_accessibility_settings(
                text_size.itemData(index), high_contrast.isChecked()
            )
        )
        high_contrast.toggled.connect(
            lambda enabled: self.apply_accessibility_settings(
                text_size.currentData(), enabled
            )
        )
        privacy_group = QtWidgets.QGroupBox("Privacy controls")
        privacy_layout = QtWidgets.QVBoxLayout(privacy_group)
        preview_checkbox = QtWidgets.QCheckBox("Hide live camera preview")
        preview_checkbox.setChecked(self.camera_preview_hidden)
        preview_checkbox.setToolTip(
            "Hides the displayed face image. Webcam capture and local analysis "
            "continue until you stop or pause the camera."
        )
        preview_checkbox.toggled.connect(self.set_camera_preview_hidden)
        privacy_notice = QtWidgets.QLabel(
            "Frames are processed locally and never recorded or exported. "
            "Session events stay in memory unless you explicitly export a JSON "
            "summary. Hiding the preview does not stop capture; use Stop webcam "
            "to release the camera."
        )
        privacy_notice.setWordWrap(True)
        clear_history_button = QtWidgets.QPushButton(
            "Clear session history"
        )
        clear_history_button.clicked.connect(
            self.confirm_clear_session_history
        )
        privacy_layout.addWidget(preview_checkbox)
        privacy_layout.addWidget(privacy_notice)
        privacy_layout.addWidget(clear_history_button)
        form.addRow("Eye sensitivity", sensitivity)
        form.addRow("Frequent blink threshold", blink_threshold)
        form.addRow("Repeated yawn threshold", yawn_threshold)
        form.addRow("Critical eye closure demo", eye_seconds)
        form.addRow("Parking/unresponsive demo", parking_seconds)
        form.addRow("Critical beep interval", repeat_ms)
        form.addRow("Text size", text_size)
        form.addRow("Contrast", high_contrast)
        sound_checkbox = QtWidgets.QCheckBox("Enable escalating warning beeps")
        sound_checkbox.setChecked(self.sound_enabled)
        sound_checkbox.toggled.connect(self.set_sound_enabled)
        test_button = QtWidgets.QPushButton("Test warning sound")
        test_button.clicked.connect(self.test_sound)
        thresholds = QtWidgets.QLabel(
            "Demo thresholds: urgent repeated beeps after "
            f"{self.critical_eye_seconds:g}s of continuous eye closure; "
            f"software parking after {self.parking_seconds:g}s of continuous "
            "closure or no response to an active warning. These are not safe "
            "real-world reaction times. No vehicle controls are connected."
        )
        thresholds.setWordWrap(True)
        keyboard_help = QtWidgets.QLabel(
            "Keyboard: Tab / Shift+Tab moves between controls; Enter or Space "
            "activates the focused control. F1 opens Help, F8 tests sound, "
            "and Esc closes the dashboard."
        )
        keyboard_help.setWordWrap(True)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        apply_button = QtWidgets.QPushButton("Apply settings")
        apply_button.clicked.connect(
            lambda: self.apply_settings(
                sensitivity.value(),
                blink_threshold.value(),
                yawn_threshold.value(),
                eye_seconds.value(),
                parking_seconds.value(),
                repeat_ms.value(),
            )
        )
        layout.addLayout(form)
        layout.addWidget(privacy_group)
        layout.addWidget(sound_checkbox)
        layout.addWidget(test_button)
        layout.addWidget(thresholds)
        layout.addWidget(keyboard_help)
        layout.addWidget(apply_button)
        layout.addWidget(close_button)
        dialog.show()
        self._apply_accessibility_styles()

    def apply_settings(
        self, sensitivity, blink_threshold, yawn_threshold,
        eye_seconds, parking_seconds, repeat_ms,
    ):
        if parking_seconds <= eye_seconds:
            self.statusBar().showMessage(
                "Parking timeout must be longer than the critical eye-closure timeout",
                5000,
            )
            return
        self.sensitivity = sensitivity
        self.blink_threshold = blink_threshold
        self.yawn_threshold = yawn_threshold
        self.critical_eye_seconds = eye_seconds
        self.parking_seconds = parking_seconds
        self.critical_repeat_ms = max(800, int(repeat_ms))
        self.current_alert_interval = self.critical_repeat_ms
        if self.last_alert_key not in (None, ("None", False)):
            self.sound_timer.start(self.critical_repeat_ms)
        self.settings_changed.emit(
            {
                "sensitivity": sensitivity,
                "blink_threshold": blink_threshold,
                "yawn_threshold": yawn_threshold,
            }
        )
        self.statusBar().showMessage("Detection settings applied", 3000)

    def set_sound_enabled(self, enabled):
        self.sound_enabled = enabled
        self.sound_button.setText("Sound: ON" if enabled else "Sound: OFF")
        if not enabled:
            self.sound_timer.stop()
        elif self.last_alert_key not in (None, ("None", False)):
            self.sound_timer.start(self.current_alert_interval)

    def test_sound(self):
        if self.sound_enabled:
            self.play_alert_beep()
            self.statusBar().showMessage("Sound test requested", 3000)
        else:
            self.statusBar().showMessage("Warning sound is muted", 3000)

    def show_help(self):
        QtWidgets.QMessageBox.information(
            self,
            "Dashboard help",
            "Run Calibrate eyes + pose for the guided one-minute setup in "
            "your usual comfortable posture; do not force your head straight. "
            "Follow each on-screen prompt. It personalizes open-eye EAR and "
            "your habitual head-angle reference using natural blinks and "
            "gentle glances/tilts. The webcam tracks EAR, blinks, PERCLOS, mouth "
            "aperture/yawns, and head deviation. Use I'm alert to record a "
            "response, Run parking demo "
            "to preview the software-only maneuver, and Reset drive simulation "
            "to return to the road. Unreliable face tracking is shown as "
            "uncertain, not as eye closure.\n\n"
            "The 35s / 45s thresholds are demonstration requirements, not "
            "safe reaction times. This application does not control a vehicle."
        )

    def closeEvent(self, event):
        self.sound_timer.stop()
        self.clock_timer.stop()
        self.drive_simulation.animation_timer.stop()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = HMIWindow()
    window.show()
    sys.exit(app.exec_())
