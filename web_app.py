"""Browser webcam API for the Render-hosted drowsiness demonstration."""

import base64
import binascii
import os
import threading
import time
import uuid
from _thread import RLock
from dataclasses import dataclass, field
from typing import Optional

os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"] = "1228800"

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

from perclos_calculation import PERCLOSCalculator


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

SESSION_TTL_SECONDS = 30 * 60
sessions = {}
sessions_lock = threading.Lock()


@dataclass
class WebSession:
    calculator: PERCLOSCalculator = field(default_factory=PERCLOSCalculator)
    last_seen: float = field(default_factory=time.monotonic)
    head_deviation_since: Optional[float] = None
    lock: RLock = field(default_factory=RLock)


def _session_for(session_id):
    try:
        normalized_id = str(uuid.UUID(session_id))
    except (AttributeError, TypeError, ValueError):
        return None

    now = time.monotonic()
    with sessions_lock:
        expired_ids = [
            key
            for key, state in sessions.items()
            if now - state.last_seen > SESSION_TTL_SECONDS
        ]
        for key in expired_ids:
            del sessions[key]
        state = sessions.get(normalized_id)
        if state is None:
            state = WebSession()
            sessions[normalized_id] = state
        state.last_seen = now
    return state


def _risk_level(metrics, state):
    if not metrics.tracking_reliable:
        state.head_deviation_since = None
        return "Tracking uncertain"

    now = time.monotonic()
    head_angles = [
        abs(value)
        for value in (metrics.head_pitch, metrics.face_roll)
        if value is not None
    ]
    head_angle = max(head_angles) if head_angles else None
    if head_angle is not None and head_angle >= 12:
        if state.head_deviation_since is None:
            state.head_deviation_since = now
    else:
        state.head_deviation_since = None
    head_duration = (
        now - state.head_deviation_since
        if state.head_deviation_since is not None
        else 0.0
    )
    perclos = metrics.perclos or 0.0
    eye_closure_active = metrics.closed_duration > 0
    yawn_count = 0 if metrics.speech_active else metrics.yawn_count
    yawn_duration = 0 if metrics.speech_active else metrics.yawn_duration

    level = "Attentive"
    if (
        (perclos >= 20 and not eye_closure_active)
        or yawn_count >= 2
        or metrics.blink_rate >= 30
        or metrics.closed_duration >= 5
        or yawn_duration >= 3
        or (head_angle is not None and head_angle >= 12 and head_duration >= 5)
    ):
        level = "Level 1"
    if (
        (perclos >= 35 and not eye_closure_active)
        or yawn_count >= 3
        or metrics.closed_duration >= 8
        or yawn_duration >= 6
        or (head_angle is not None and head_angle >= 22 and head_duration >= 8)
    ):
        level = "Level 2"
    if (
        (perclos >= 50 and not eye_closure_active)
        or metrics.closed_duration >= 12
        or yawn_duration >= 10
        or (head_angle is not None and head_angle >= 32 and head_duration >= 12)
    ):
        level = "Level 3"
    return level


def _metric_value(value):
    return None if value is None else round(float(value), 2)


def _metrics_response(metrics, state):
    return {
        "tracking_reliable": metrics.tracking_reliable,
        "tracking_guidance": metrics.tracking_guidance,
        "calibrating": metrics.calibrating,
        "calibrated": metrics.calibrated,
        "pose_calibrated": metrics.pose_calibrated,
        "status": "Calibrating" if metrics.calibrating else _risk_level(metrics, state),
        "ear": _metric_value(metrics.ear),
        "perclos": _metric_value(metrics.perclos),
        "closed_duration": _metric_value(metrics.closed_duration),
        "blink_rate": _metric_value(metrics.blink_rate),
        "mouth_aperture": _metric_value(metrics.mouth_aperture),
        "yawn_count": int(metrics.yawn_count),
        "head_pitch": _metric_value(metrics.head_pitch),
        "head_yaw": _metric_value(metrics.head_yaw),
        "head_roll": _metric_value(metrics.face_roll),
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def health_check():
    return jsonify(status="ok")


@app.post("/api/calibrate")
def calibrate():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="A JSON object is required."), 400
    state = _session_for(payload.get("session_id"))
    if state is None:
        return jsonify(error="A valid session_id is required."), 400
    with state.lock:
        state.calculator.start_calibration()
        state.last_seen = time.monotonic()
    return jsonify(message="Calibration started.", seconds=60)


@app.post("/api/analyze")
def analyze():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="A JSON object is required."), 400
    state = _session_for(payload.get("session_id"))
    if state is None:
        return jsonify(error="A valid session_id is required."), 400

    image_data = payload.get("image")
    prefix = "data:image/jpeg;base64,"
    if not isinstance(image_data, str) or not image_data.startswith(prefix):
        return jsonify(error="A JPEG camera frame is required."), 400

    try:
        image_bytes = base64.b64decode(
            image_data[len(prefix):], validate=True
        )
    except (binascii.Error, ValueError):
        return jsonify(error="The camera frame is not valid base64."), 400
    if not image_bytes or len(image_bytes) > 750_000:
        return jsonify(error="The camera frame is empty or too large."), 400

    frame = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    if frame is None:
        return jsonify(error="The camera frame could not be decoded."), 400
    height, width = frame.shape[:2]
    if width > 1280 or height > 960:
        return jsonify(error="Camera frames must be at most 1280x960."), 400

    try:
        with state.lock:
            metrics = state.calculator.process_frame_for_metrics(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            )
            response = _metrics_response(metrics, state)
            state.last_seen = time.monotonic()
    except (cv2.error, RuntimeError, ValueError):
        app.logger.exception("Failed to process a webcam frame")
        return jsonify(error="Could not process this camera frame."), 500
    return jsonify(response)


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(error="The request is too large."), 413
