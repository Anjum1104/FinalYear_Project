"""Facial measurements used by the driver drowsiness demonstration."""

import math
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import dlib
import cv2
import numpy as np
from scipy.spatial import distance as dist


_MODEL_PATH = Path(__file__).with_name("shape_predictor_68_face_landmarks.dat")
if not _MODEL_PATH.is_file():
    raise FileNotFoundError(
        f"Required facial-landmark model was not found: {_MODEL_PATH}"
    )

detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(str(_MODEL_PATH))


@dataclass
class DetectionMetrics:
    ear: Optional[float]
    perclos: Optional[float]
    face_roll: Optional[float]
    head_pitch: Optional[float]
    head_yaw: Optional[float]
    eye_closed: bool
    closed_duration: float
    blink_rate: float
    mouth_aperture: Optional[float]
    yawn_count: int
    tracking_reliable: bool
    calibrated: bool
    calibrating: bool
    yawn_duration: float = 0.0
    pose_calibrated: bool = False
    eye_baseline: Optional[float] = None
    eye_closure_threshold: Optional[float] = None
    tracking_guidance: Optional[str] = None
    speech_active: bool = False


class PERCLOSCalculator:
    """Track eye closure and mouth movement from dlib's 68 facial landmarks."""

    CALIBRATION_SECONDS = 60.0
    MIN_CALIBRATED_EAR = 0.05

    def __init__(
        self,
        ear_threshold=0.25,
        alert_threshold=50.0,
        time_period=15,
        fps=30,
    ):
        self.EAR_THRESHOLD = ear_threshold
        self.ALERT_THRESHOLD = alert_threshold
        self.TIME_PERIOD = time_period
        self.frames_for_period = max(1, int(fps * time_period))
        self.eye_closed_buffer = deque()
        self.blink_events = deque()
        self.yawn_events = deque()
        self.eye_baseline = None
        self.calibration_samples = []
        self.pose_calibration_samples = []
        self.pose_baseline = None
        self.pose_history = deque(maxlen=5)
        self.calibrating = False
        self.calibration_started_at = None
        self.closed_since = None
        self.closed_candidate_frames = 0
        self.was_eye_closed = False
        self.yawn_started = None
        self.yawn_active = False
        self.mouth_history = deque()
        self.speech_active = False
        self.last_landmarks = None
        self.sensitivity = 1.0

    def set_sensitivity(self, sensitivity):
        self.sensitivity = min(1.5, max(0.5, float(sensitivity)))

    def get_eye_closure_threshold(self):
        if self.eye_baseline is not None:
            ratio = 0.72 + 0.16 * (self.sensitivity - 1.0)
            return self.eye_baseline * ratio
        return self.EAR_THRESHOLD * (0.8 + 0.2 * self.sensitivity)

    @staticmethod
    def calculate_EAR(eye):
        vertical_a = dist.euclidean(eye[1], eye[5])
        vertical_b = dist.euclidean(eye[2], eye[4])
        horizontal = dist.euclidean(eye[0], eye[3])
        if horizontal <= 0:
            return 0.0
        return (vertical_a + vertical_b) / (2.0 * horizontal)

    @staticmethod
    def calculate_mouth_aperture(landmarks):
        mouth_width = dist.euclidean(landmarks[60], landmarks[64])
        if mouth_width <= 0:
            return 0.0
        inner_opening = (
            dist.euclidean(landmarks[62], landmarks[66])
            + dist.euclidean(landmarks[63], landmarks[65])
        ) / 2.0
        return inner_opening / mouth_width

    def start_calibration(self):
        """Start a guided one-minute personalized eye and posture calibration."""
        self.calibration_samples.clear()
        self.pose_calibration_samples.clear()
        self.pose_baseline = None
        self.pose_history.clear()
        self.calibrating = True
        self.calibration_started_at = time.monotonic()
        self.eye_baseline = None
        self.closed_since = None
        self.closed_candidate_frames = 0
        self.was_eye_closed = False
        self.eye_closed_buffer.clear()
        self.yawn_started = None
        self.yawn_active = False
        self.yawn_events.clear()
        self.mouth_history.clear()
        self.speech_active = False

    def calibration_progress(self, now=None):
        if not self.calibrating or self.calibration_started_at is None:
            return 60, "Calibration is not running"
        if now is None:
            now = time.monotonic()
        elapsed = min(
            self.CALIBRATION_SECONDS,
            max(0.0, now - self.calibration_started_at),
        )
        phases = (
            (
                15,
                "Sit as you naturally do; do not force your head straight. "
                "Keep eyes open while your usual posture is measured.",
            ),
            (
                30,
                "Keep your comfortable head position and blink naturally "
                "while your personal eye ratio is measured.",
            ),
            (42, "Slowly glance left and right, then return to center."),
            (54, "Gently tilt your head left and right, then return to center."),
            (
                60,
                "Return to your usual comfortable head position; do not "
                "correct a natural bend.",
            ),
        )
        prompt = next(
            (text for boundary, text in phases if elapsed < boundary),
            phases[-1][1],
        )
        return int(elapsed), prompt

    def _finish_calibration_if_due(self, now):
        if (
            not self.calibrating
            or self.calibration_started_at is None
            or now - self.calibration_started_at < self.CALIBRATION_SECONDS
        ):
            return

        if len(self.calibration_samples) >= 45:
            ordered = sorted(self.calibration_samples)
            upper_samples = ordered[len(ordered) // 3 :]
            baseline = float(np.median(upper_samples))
            self.eye_baseline = (
                baseline
                if baseline >= self.MIN_CALIBRATED_EAR
                else None
            )
        if len(self.pose_calibration_samples) >= 20:
            self.pose_baseline = tuple(
                float(
                    np.median(
                        [sample[index] for sample in self.pose_calibration_samples]
                    )
                )
                for index in range(3)
            )
        self.calibrating = False
        self.calibration_started_at = None
        self.pose_history.clear()

    def _update_calibration(self, ear, pose, now):
        if not self.calibrating or self.calibration_started_at is None:
            return

        elapsed = now - self.calibration_started_at
        is_baseline_phase = elapsed < 30.0 or elapsed >= 54.0
        if is_baseline_phase and ear >= max(
            self.MIN_CALIBRATED_EAR, self.EAR_THRESHOLD * 0.2
        ):
            self.calibration_samples.append(ear)
        is_neutral_phase = is_baseline_phase
        if is_neutral_phase and pose is not None and all(
            value is not None and math.isfinite(value) for value in pose
        ):
            self.pose_calibration_samples.append(pose)
        self._finish_calibration_if_due(now)

    def _prune_events(self, now):
        while (
            self.eye_closed_buffer
            and now - self.eye_closed_buffer[0][0] > self.TIME_PERIOD
        ):
            self.eye_closed_buffer.popleft()
        while self.blink_events and now - self.blink_events[0] > 60:
            self.blink_events.popleft()
        while self.yawn_events and now - self.yawn_events[0] > 60:
            self.yawn_events.popleft()

    def _calculate_perclos(self, now):
        if (
            not self.eye_closed_buffer
            or now - self.eye_closed_buffer[0][0] < self.TIME_PERIOD * 0.95
        ):
            return None
        return (
            100.0
            * sum(closed for _, closed in self.eye_closed_buffer)
            / len(self.eye_closed_buffer)
        )

    def _reset_unreliable_frame(self):
        self.closed_since = None
        self.closed_candidate_frames = 0
        self.was_eye_closed = False
        self.yawn_started = None
        self.yawn_active = False
        self.mouth_history.clear()
        self.speech_active = False
        self.eye_closed_buffer.clear()
        self.pose_history.clear()
        self.last_landmarks = None

    def _unreliable_metrics(self, tracking_guidance=None):
        self._finish_calibration_if_due(time.monotonic())
        return DetectionMetrics(
            ear=None,
            perclos=None,
            face_roll=None,
            head_pitch=None,
            head_yaw=None,
            eye_closed=False,
            closed_duration=0.0,
            blink_rate=float(len(self.blink_events)),
            mouth_aperture=None,
            yawn_count=len(self.yawn_events),
            tracking_reliable=False,
            calibrated=self.eye_baseline is not None,
            calibrating=self.calibrating,
            pose_calibrated=self.pose_baseline is not None,
            eye_baseline=self.eye_baseline,
            eye_closure_threshold=self.get_eye_closure_threshold(),
            tracking_guidance=tracking_guidance,
        )

    def reset_for_tracking_loss(self, tracking_guidance=None):
        """Discard continuous-condition history when the camera feed is lost."""
        self._reset_unreliable_frame()
        return self._unreliable_metrics(tracking_guidance)

    def _update_speech_activity(self, mouth_aperture, now):
        self.mouth_history.append((now, mouth_aperture))
        while self.mouth_history and now - self.mouth_history[0][0] > 3.0:
            self.mouth_history.popleft()

        transitions = 0
        is_open = False
        for _, aperture in self.mouth_history:
            if not is_open and aperture >= 0.55:
                is_open = True
                transitions += 1
            elif is_open and aperture <= 0.4:
                is_open = False
                transitions += 1
        self.speech_active = transitions >= 4
        return self.speech_active

    def process_frame_for_metrics(self, gray_frame):
        now = time.monotonic()
        self._prune_events(now)
        landmarks = self._detect_landmarks(gray_frame)
        if landmarks is None:
            self._reset_unreliable_frame()
            return self._unreliable_metrics(
                self._tracking_guidance(gray_frame)
            )

        self.last_landmarks = landmarks
        face_width = int(np.ptp(landmarks[:, 0]))
        eye_widths = (
            dist.euclidean(landmarks[42], landmarks[45]),
            dist.euclidean(landmarks[36], landmarks[39]),
        )
        mouth_width = dist.euclidean(landmarks[60], landmarks[64])
        if face_width < 70 or min(eye_widths) < 2 or mouth_width < 2:
            guidance = self._tracking_guidance(gray_frame, landmarks)
            if face_width < 70 or min(eye_widths) < 2:
                guidance = (
                    "Face/eyes too small or partly out of frame: move closer "
                    "and keep your full face visible."
                )
            self._reset_unreliable_frame()
            return self._unreliable_metrics(guidance)

        tracking_guidance = self._tracking_guidance(gray_frame, landmarks)
        left_ear = self.calculate_EAR(landmarks[42:48])
        right_ear = self.calculate_EAR(landmarks[36:42])
        ear = (left_ear + right_ear) / 2.0
        raw_pose = self._estimate_head_pose(
            landmarks, gray_frame.shape[1], gray_frame.shape[0]
        )
        mouth_aperture = self.calculate_mouth_aperture(landmarks)
        speech_active = self._update_speech_activity(mouth_aperture, now)
        self._update_calibration(ear, raw_pose, now)
        if raw_pose is not None and all(
            value is not None and math.isfinite(value) for value in raw_pose
        ):
            pose = (
                tuple(
                    self._angular_delta(value, baseline)
                    for value, baseline in zip(raw_pose, self.pose_baseline)
                )
                if self.pose_baseline is not None
                else raw_pose
            )
            self.pose_history.append(pose)
            smoothed_pose = tuple(
                float(np.median([sample[index] for sample in self.pose_history]))
                for index in range(3)
            )
            head_pitch, head_yaw, face_roll = smoothed_pose
        else:
            self.pose_history.clear()
            head_pitch, head_yaw, face_roll = None, None, None

        if self.calibrating:
            self.closed_candidate_frames = 0
            self.closed_since = None
            eye_closed = False
        else:
            threshold = self.get_eye_closure_threshold()
            if ear < threshold:
                self.closed_candidate_frames += 1
            else:
                self.closed_candidate_frames = 0
            eye_closed = self.closed_candidate_frames >= 3

        if eye_closed and self.closed_since is None:
            self.closed_since = now
        elif not eye_closed and self.closed_since is not None:
            if now - self.closed_since < 1.0:
                self.blink_events.append(now)
            self.closed_since = None

        self.was_eye_closed = eye_closed
        self.eye_closed_buffer.append((now, eye_closed))

        if speech_active:
            self.yawn_started = None
            self.yawn_active = False
        elif mouth_aperture >= 0.55:
            if self.yawn_started is None:
                self.yawn_started = now
            elif now - self.yawn_started >= 1.0 and not self.yawn_active:
                self.yawn_events.append(now)
                self.yawn_active = True
        else:
            self.yawn_started = None
            if mouth_aperture < 0.4:
                self.yawn_active = False

        self._prune_events(now)
        perclos = self._calculate_perclos(now)
        closed_duration = (
            max(0.0, now - self.closed_since)
            if self.closed_since is not None
            else 0.0
        )

        return DetectionMetrics(
            ear=ear,
            perclos=perclos,
            face_roll=face_roll,
            head_pitch=head_pitch,
            head_yaw=head_yaw,
            eye_closed=eye_closed,
            closed_duration=closed_duration,
            blink_rate=float(len(self.blink_events)),
            mouth_aperture=mouth_aperture,
            yawn_count=len(self.yawn_events),
            tracking_reliable=True,
            calibrated=self.eye_baseline is not None,
            calibrating=self.calibrating,
            yawn_duration=(
                max(0.0, now - self.yawn_started)
                if self.yawn_started is not None
                else 0.0
            ),
            pose_calibrated=self.pose_baseline is not None,
            eye_baseline=self.eye_baseline,
            eye_closure_threshold=self.get_eye_closure_threshold(),
            tracking_guidance=tracking_guidance,
            speech_active=speech_active,
        )

    @staticmethod
    def _tracking_guidance(gray_frame, landmarks=None):
        height, width = gray_frame.shape[:2]
        if landmarks is None:
            if float(np.mean(gray_frame)) < 50:
                return (
                    "Scene is very dim: add light in front of your face, "
                    "then check tracking again."
                )
            return (
                "Face not found: center your face, face the camera, and clear "
                "anything covering it."
            )

        x_min = max(0, int(np.min(landmarks[:, 0])))
        x_max = min(width, int(np.max(landmarks[:, 0])) + 1)
        y_min = max(0, int(np.min(landmarks[:, 1])))
        y_max = min(height, int(np.max(landmarks[:, 1])) + 1)
        face_width = x_max - x_min
        face_center_x = (x_min + x_max) / 2.0
        if face_width < width * 0.18:
            return "Face is small in frame: move a little closer to the camera."
        if abs(face_center_x - width / 2.0) > width * 0.2:
            return "Face is off-center: move into the middle of the camera view."
        face_center_y = (y_min + y_max) / 2.0
        if abs(face_center_y - height / 2.0) > height * 0.24:
            return "Face is too high or low in frame: adjust the camera to face level."

        if x_max > x_min and y_max > y_min:
            face_region = gray_frame[y_min:y_max, x_min:x_max]
            brightness = float(np.mean(face_region))
            contrast = float(np.std(face_region))
            if brightness < 55:
                return (
                    "Face lighting is low: add soft light from in front of "
                    "you and avoid a bright light behind you."
                )
            if brightness < 85 and contrast < 18:
                return (
                    "Face detail is low: improve front lighting and check "
                    "that the camera lens is clear."
                )
        return None

    @staticmethod
    def _detect_landmarks(gray_frame):
        height, width = gray_frame.shape[:2]
        center = (width / 2.0, height / 2.0)
        for angle in (None, -25, 25):
            inverse_rotation = None
            detection_frame = gray_frame
            if angle is not None:
                rotation = cv2.getRotationMatrix2D(center, angle, 1.0)
                detection_frame = cv2.warpAffine(
                    gray_frame,
                    rotation,
                    (width, height),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                )
                inverse_rotation = cv2.invertAffineTransform(rotation)

            faces = detector(detection_frame, 0)
            if not faces:
                continue
            face = max(
                faces,
                key=lambda rect: max(0, rect.width()) * max(0, rect.height()),
            )
            shape = predictor(detection_frame, face)
            landmarks = np.array(
                [[point.x, point.y] for point in shape.parts()],
                dtype=np.float64,
            )
            if inverse_rotation is not None:
                landmarks = cv2.transform(
                    landmarks[None, :, :], inverse_rotation
                )[0]
            landmarks = np.rint(landmarks).astype(np.int32)

            face_width = int(np.ptp(landmarks[:, 0]))
            eye_widths = (
                dist.euclidean(landmarks[42], landmarks[45]),
                dist.euclidean(landmarks[36], landmarks[39]),
            )
            mouth_width = dist.euclidean(landmarks[60], landmarks[64])
            if face_width >= 70 and min(eye_widths) >= 2 and mouth_width >= 2:
                return landmarks
        return None

    @staticmethod
    def _angular_delta(value, baseline):
        return (value - baseline + 180.0) % 360.0 - 180.0

    @staticmethod
    def _estimate_head_pose(landmarks, width, height):
        image_points = np.array(
            [
                landmarks[30],
                landmarks[8],
                landmarks[36],
                landmarks[45],
                landmarks[48],
                landmarks[54],
            ],
            dtype=np.float64,
        )
        model_points = np.array(
            [
                (0.0, 0.0, 0.0),
                (0.0, -330.0, -65.0),
                (-225.0, 170.0, -135.0),
                (225.0, 170.0, -135.0),
                (-150.0, -150.0, -125.0),
                (150.0, -150.0, -125.0),
            ],
            dtype=np.float64,
        )
        focal_length = float(width)
        camera_matrix = np.array(
            [
                [focal_length, 0.0, width / 2.0],
                [0.0, focal_length, height / 2.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        success, rotation_vector, _ = cv2.solvePnP(
            model_points,
            image_points,
            camera_matrix,
            np.zeros((4, 1), dtype=np.float64),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return None, None, None
        rotation, _ = cv2.Rodrigues(rotation_vector)
        sy = math.sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2)
        singular = sy < 1e-6
        if singular:
            pitch = math.atan2(-rotation[1, 2], rotation[1, 1])
            yaw = math.atan2(-rotation[2, 0], sy)
            roll = 0.0
        else:
            pitch = math.atan2(rotation[2, 1], rotation[2, 2])
            yaw = math.atan2(-rotation[2, 0], sy)
            roll = math.atan2(rotation[1, 0], rotation[0, 0])
        return tuple(
            math.degrees(value) for value in (pitch, yaw, roll)
        )

    def draw_landmarks(self, frame, metrics=None, mirrored=False):
        if self.last_landmarks is None:
            return frame

        points = self.last_landmarks.astype(np.int32)
        if mirrored:
            points[:, 0] = frame.shape[1] - 1 - points[:, 0]
        face_hull = cv2.convexHull(points)
        _, _, width, height = cv2.boundingRect(face_hull)
        subdivisions = cv2.Subdiv2D(
            (0, 0, frame.shape[1], frame.shape[0])
        )
        inserted_points = set()
        for point_x, point_y in points:
            point = (
                min(frame.shape[1] - 1, max(0, int(point_x))),
                min(frame.shape[0] - 1, max(0, int(point_y))),
            )
            if point not in inserted_points:
                subdivisions.insert(point)
                inserted_points.add(point)
        mesh = frame.copy()
        maximum_edge = math.hypot(width, height) * 0.38
        for triangle in subdivisions.getTriangleList():
            vertices = triangle.reshape(3, 2)
            center = tuple(vertices.mean(axis=0).astype(float))
            if cv2.pointPolygonTest(face_hull, center, False) < 0:
                continue
            if max(
                math.dist(vertices[index], vertices[(index + 1) % 3])
                for index in range(3)
            ) > maximum_edge:
                continue
            polygon = np.rint(vertices).astype(np.int32)
            cv2.polylines(
                mesh,
                [polygon],
                True,
                (125, 220, 238),
                1,
                cv2.LINE_AA,
            )
        cv2.addWeighted(mesh, 0.22, frame, 0.78, 0, dst=frame)

        def draw_contour(contour, color, thickness=2):
            cv2.polylines(
                frame,
                [contour.astype(np.int32)],
                False,
                color,
                thickness,
                cv2.LINE_AA,
            )

        draw_contour(points[0:17], (70, 225, 242), 1)
        draw_contour(points[17:22], (75, 148, 255), 1)
        draw_contour(points[22:27], (220, 100, 238), 1)
        draw_contour(points[27:31], (90, 205, 230), 1)
        draw_contour(points[31:36], (90, 205, 230), 1)

        eyes_color = (
            (255, 72, 72)
            if metrics is not None and metrics.eye_closed
            else (74, 158, 255)
        )
        for first, last, color in (
            (36, 42, eyes_color),
            (42, 48, (220, 100, 238) if metrics is None or not metrics.eye_closed else eyes_color),
        ):
            contour = points[first:last]
            cv2.polylines(frame, [contour], True, color, 1, cv2.LINE_AA)
            for point_x, point_y in contour:
                cv2.circle(frame, (int(point_x), int(point_y)), 1, color, -1)

        mouth_color = (65, 220, 235)
        outer_mouth = points[48:60]
        inner_mouth = points[60:68]
        cv2.polylines(
            frame, [outer_mouth], True, mouth_color, 1, cv2.LINE_AA
        )
        cv2.polylines(
            frame, [inner_mouth], True, (255, 190, 80), 1, cv2.LINE_AA
        )

        left_eye_center = points[36:42].mean(axis=0)
        right_eye_center = points[42:48].mean(axis=0)
        eye_axis = right_eye_center - left_eye_center
        eye_axis_length = float(np.linalg.norm(eye_axis))
        if eye_axis_length > 0:
            eye_axis /= eye_axis_length
            down_axis = np.array([-eye_axis[1], eye_axis[0]])
            if down_axis[1] < 0:
                down_axis *= -1
            face_width = float(np.linalg.norm(points[0] - points[16]))
            chin = points[8].astype(float)
            neck_center = chin + down_axis * face_width * 0.28
            neck_half_width = face_width * 0.20
            neck_left = neck_center - eye_axis * neck_half_width
            neck_right = neck_center + eye_axis * neck_half_width
            shoulder_drop = down_axis * face_width * 0.48
            shoulder_left = neck_center - eye_axis * face_width * 0.62 + shoulder_drop
            shoulder_right = neck_center + eye_axis * face_width * 0.62 + shoulder_drop
            guide_color = (75, 195, 210)
            for start, end in (
                (points[4], neck_left),
                (points[12], neck_right),
                (neck_left, neck_right),
                (neck_left, shoulder_left),
                (neck_right, shoulder_right),
                (shoulder_left, shoulder_right),
            ):
                cv2.line(
                    frame,
                    tuple(np.rint(start).astype(int)),
                    tuple(np.rint(end).astype(int)),
                    guide_color,
                    1,
                    cv2.LINE_AA,
                )
            guide_origin = tuple(np.rint(shoulder_left).astype(int))
            self._draw_overlay_label(
                frame, "NECK GUIDE · ESTIMATED", guide_origin, guide_color
            )

        eye_center = points[36:48].mean(axis=0).astype(int)
        mouth_center = points[48:60].mean(axis=0).astype(int)
        eye_text = (
            "EYES CLOSED"
            if metrics is not None and metrics.eye_closed
            else "EYES OPEN"
        )
        self._draw_overlay_label(
            frame, eye_text, (int(eye_center[0]), int(eye_center[1]) - 20),
            eyes_color,
        )
        self._draw_overlay_label(
            frame, "LIPS", (int(mouth_center[0]), int(mouth_center[1]) + 32),
            mouth_color,
        )
        if metrics is not None and metrics.head_pitch is not None:
            pose_prefix = "Δ" if metrics.pose_calibrated else ""
            pose_text = (
                f"{pose_prefix}P {metrics.head_pitch:+.0f}°  "
                f"Y {metrics.head_yaw:+.0f}°  "
                f"{pose_prefix}R {metrics.face_roll:+.0f}°"
            )
            pose_color = (
                (75, 165, 255)
                if metrics.pose_calibrated
                and max(abs(metrics.head_pitch), abs(metrics.face_roll or 0)) >= 12
                else (90, 220, 190)
            )
            self._draw_overlay_label(
                frame, pose_text, (12, frame.shape[0] - 16), pose_color
            )
        return frame

    @staticmethod
    def _draw_overlay_label(frame, text, origin, color):
        cv2.putText(
            frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.48,
            (10, 17, 28), 3, cv2.LINE_AA,
        )
        cv2.putText(
            frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.48,
            color, 1, cv2.LINE_AA,
        )

    def process_frame_for_perclos(self, gray_frame):
        """Retain the original two-value interface for existing callers."""
        metrics = self.process_frame_for_metrics(gray_frame)
        return metrics.ear or 0.0, metrics.perclos or 0.0
