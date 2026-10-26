# POSTURE DEVIATION MODULE
# Developed by : EL HANNACH Walid

# Overview:
# This module is designed to analyze posture deviation using a webcam feed. 
# It leverages MediaPipe to detect human pose landmarks and calculates 
# the angle of the head relative to the shoulders to assess posture deviation.
# The main functionalities include pose detection and angle calculation.

import mediapipe as mp # MediaPipe library for real-time pose estimation
import numpy as np  # Library for numerical operations
import cv2 # OpenCV library for computer vision tasks
from typing import Optional
 
mp_pose = mp.solutions.pose
pose = mp_pose.Pose()
mp_drawing = mp.solutions.drawing_utils

def calculate_head_angle(landmarks) -> Optional[float]:

    """
    Calculate the angle of the head relative to the shoulders.

    Parameters:
    landmarks (list): List of pose landmarks detected by MediaPipe.

    Returns:
    Optional[float]: Deviation from the shoulder-relative upright axis, or None
        when the required landmarks are not visible with sufficient confidence.
    """
        
    left = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
    right = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
    nose = landmarks[mp_pose.PoseLandmark.NOSE]
    if min(left.visibility, right.visibility, nose.visibility) < 0.5:
        return None

    left_shoulder = np.array([left.x, left.y])
    right_shoulder = np.array([right.x, right.y])
    nose_position = np.array([nose.x, nose.y])
    shoulder_axis = right_shoulder - left_shoulder
    shoulder_width = np.linalg.norm(shoulder_axis)
    if shoulder_width < 0.02:
        return None

    shoulder_midpoint = (left_shoulder + right_shoulder) / 2
    head_vector = nose_position - shoulder_midpoint
    head_length = np.linalg.norm(head_vector)
    if head_length < 1e-6:
        return None

    upward_normal = np.array([shoulder_axis[1], -shoulder_axis[0]])
    if upward_normal[1] > 0:
        upward_normal = -upward_normal
    cosine_angle = np.dot(head_vector, upward_normal) / (
        head_length * shoulder_width
    )
    angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
    return np.degrees(angle)

def process_frame_for_posture(frame):
    """
    Process a video frame to detect pose landmarks and calculate head angle.

    Parameters:
    frame (numpy.ndarray): The input image frame from the video feed.

    Returns:
    tuple: A tuple containing the processed frame and the calculated head angle.
    """
     
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = pose.process(rgb_frame)
    
    head_angle = None
    if result.pose_landmarks:
        mp_drawing.draw_landmarks(rgb_frame, result.pose_landmarks, mp_pose.POSE_CONNECTIONS)
        landmarks = result.pose_landmarks.landmark
        head_angle = calculate_head_angle(landmarks)
    
    return rgb_frame, head_angle
