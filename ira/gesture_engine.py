"""IRA Gesture Engine — MediaPipe face mesh + hand landmarks for gesture recognition."""

from __future__ import annotations

import json
import math
import os
import sys
import time
import threading
import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import cv2
import numpy as np

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GESTURE_CONFIG = os.path.join(ROOT_DIR, "gesture_config.json")


# ── Gesture Types ──────────────────────────────────────────

class GestureType(Enum):
    HAND = "hand"
    FACE = "face"
    CLAP = "clap"


@dataclass
class DetectedGesture:
    name: str
    gesture_type: GestureType
    confidence: float
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ── Hand Gesture Definitions ───────────────────────────────

def _distance(p1, p2) -> float:
    """Euclidean distance between two landmarks."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def _angle(p1, p2) -> float:
    """Angle between two points in degrees."""
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))


class HandGestureRecognizer:
    """Recognizes hand gestures from MediaPipe hand landmarks."""

    GESTURE_NAMES = [
        "open_palm", "fist", "thumbs_up", "thumbs_down",
        "point_up", "point_down", "point_left", "point_right",
        "peace", "rock", "ok_sign", "pinch",
        "wave", "grab", "swipe_left", "swipe_right",
    ]

    def __init__(self):
        self._prev_landmarks = None
        self._prev_time = 0
        self._wave_history = []

    def get_hand_state(self, landmarks, handedness: str = "Right") -> dict:
        """Return continuous hand state for HUD pointer and drawing controls."""
        lm = landmarks.landmark
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]

        fingers_up = []
        if handedness == "Right":
            fingers_up.append(lm[4].x < lm[3].x)
        else:
            fingers_up.append(lm[4].x > lm[3].x)
        for i in range(1, 5):
            fingers_up.append(lm[tips[i]].y < lm[pips[i]].y)

        total_up = sum(fingers_up)
        pinch_dist = _distance(lm[4], lm[8])
        palm = lm[9]
        index = lm[8]
        wrist = lm[0]
        tip_avg_dist = sum(_distance(lm[t], palm) for t in tips) / 5
        return {
            "handedness": handedness,
            "fingers_up": fingers_up,
            "total_up": total_up,
            "pinch": pinch_dist < 0.045,
            "pinch_distance": round(pinch_dist, 4),
            "grab": tip_avg_dist < 0.09 and total_up <= 2,
            "fist": total_up == 0,
            "open_palm": total_up == 5,
            "index": {"x": index.x, "y": index.y, "z": index.z},
            "palm": {"x": palm.x, "y": palm.y, "z": palm.z},
            "wrist": {"x": wrist.x, "y": wrist.y, "z": wrist.z},
        }

    def recognize(self, landmarks, handedness: str = "Right") -> list[DetectedGesture]:
        """Recognize gestures from hand landmarks. Returns list of detected gestures."""
        gestures = []
        if not landmarks:
            return gestures

        lm = landmarks.landmark
        now = time.time()
        state = self.get_hand_state(landmarks, handedness)

        # Finger tip and base indices
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]

        # Check which fingers are extended
        fingers_up = []

        # Thumb — check x-axis (left/right based on hand)
        if handedness == "Right":
            fingers_up.append(lm[tips[0]].x < lm[pips[0]].x)
        else:
            fingers_up.append(lm[tips[0]].x > lm[pips[0]].x)

        # Other 4 fingers — check y-axis (tip above PIP = extended)
        for i in range(1, 5):
            fingers_up.append(lm[tips[i]].y < lm[pips[i]].y)

        total_up = sum(fingers_up)
        fingers_up = state["fingers_up"]
        total_up = state["total_up"]

        # Open Palm — all 5 fingers extended
        if total_up == 5:
            gestures.append(DetectedGesture("open_palm", GestureType.HAND, 0.9))

        # Fist — no fingers extended
        elif total_up == 0:
            gestures.append(DetectedGesture("fist", GestureType.HAND, 0.9))

        # Thumbs Up — only thumb extended
        elif fingers_up[0] and total_up == 1:
            # Check thumb is pointing up
            if lm[4].y < lm[3].y:
                gestures.append(DetectedGesture("thumbs_up", GestureType.HAND, 0.95))
            elif lm[4].y > lm[3].y:
                gestures.append(DetectedGesture("thumbs_down", GestureType.HAND, 0.95))

        # Thumbs Down — only thumb extended, pointing down
        # Peace / Victory — index + middle extended
        elif fingers_up[1] and fingers_up[2] and total_up == 2:
            gestures.append(DetectedGesture("peace", GestureType.HAND, 0.9))

        # Point Up — only index extended
        elif fingers_up[1] and total_up == 1:
            dx = lm[8].x - lm[6].x
            dy = lm[8].y - lm[6].y
            if abs(dy) >= abs(dx) and dy < 0:
                gestures.append(DetectedGesture("point_up", GestureType.HAND, 0.85))
            elif abs(dy) >= abs(dx) and dy > 0:
                gestures.append(DetectedGesture("point_down", GestureType.HAND, 0.85))
            elif dx > 0:
                gestures.append(DetectedGesture("point_right", GestureType.HAND, 0.85))
            else:
                gestures.append(DetectedGesture("point_left", GestureType.HAND, 0.85))

        # Point Down — only index extended, pointing down
        # Point Right — only index extended, pointing right
        # Point Left — only index extended, pointing left
        # OK Sign — thumb and index form circle, others extended
        elif fingers_up[0] and fingers_up[1]:
            ok_dist = _distance(lm[4], lm[8])
            if ok_dist < 0.06:
                gestures.append(DetectedGesture("ok_sign", GestureType.HAND, 0.85))

        # Pinch — thumb and index close together
        pinch_dist = _distance(lm[4], lm[8])
        if pinch_dist < 0.04:
            gestures.append(DetectedGesture("pinch", GestureType.HAND, 0.8, data=state))

        # Rock — index + pinky extended (metal horns)
        if fingers_up[1] and fingers_up[4] and total_up == 2:
            gestures.append(DetectedGesture("rock", GestureType.HAND, 0.85))

        # Grab — all fingers curling (check if tips are close to palm center)
        palm_center = lm[9]
        tip_avg_dist = sum(_distance(lm[t], palm_center) for t in tips) / 5
        if tip_avg_dist < 0.08 and total_up <= 2:
            gestures.append(DetectedGesture("grab", GestureType.HAND, 0.75))

        # Swipe detection (requires previous frame)
        if self._prev_landmarks and (now - self._prev_time) < 0.3:
            prev_lm = self._prev_landmarks.landmark
            dx = lm[8].x - prev_lm[8].x
            if abs(dx) > 0.15:
                if dx > 0:
                    gestures.append(DetectedGesture("swipe_right", GestureType.HAND, 0.8))
                else:
                    gestures.append(DetectedGesture("swipe_left", GestureType.HAND, 0.8))

        self._wave_history.append((now, lm[9].x))
        self._wave_history = [(t, x) for t, x in self._wave_history if now - t <= 0.8]
        if total_up >= 4 and len(self._wave_history) >= 5:
            xs = [x for _, x in self._wave_history]
            direction_changes = 0
            prev_sign = 0
            for a, b in zip(xs, xs[1:]):
                diff = b - a
                sign = 1 if diff > 0.025 else (-1 if diff < -0.025 else 0)
                if sign and prev_sign and sign != prev_sign:
                    direction_changes += 1
                if sign:
                    prev_sign = sign
            if direction_changes >= 2 and (max(xs) - min(xs)) > 0.12:
                gestures.append(DetectedGesture("wave", GestureType.HAND, 0.82, data=state))

        self._prev_landmarks = landmarks
        self._prev_time = now

        return gestures


# ── Face Expression Recognition ────────────────────────────

class FaceExpressionRecognizer:
    """Recognizes facial expressions from MediaPipe face mesh landmarks."""

    EXPRESSION_NAMES = [
        "smile", "frown", "open_mouth", "wink_left", "wink_right",
        "blink_both", "blink_left", "blink_right", "raise_eyebrows",
        "head_nod", "head_shake", "head_turn_left", "head_turn_right",
    ]

    def __init__(self):
        self._prev_landmarks = None
        self._prev_time = 0
        self._blink_history = []

    def recognize(self, face_landmarks, pose_landmarks=None) -> list[DetectedGesture]:
        """Recognize face expressions from face mesh landmarks."""
        gestures = []
        if not face_landmarks:
            return gestures

        lm = face_landmarks.landmark
        now = time.time()

        # ── Smile Detection ──
        # Compare mouth corner distance to nose width
        mouth_left = lm[61]
        mouth_right = lm[291]
        mouth_width = _distance(mouth_left, mouth_right)

        upper_lip = lm[13]
        lower_lip = lm[14]
        mouth_open_dist = _distance(upper_lip, lower_lip)

        nose_width = _distance(lm[33], lm[263])

        # Smile: mouth wide + lips curved up
        left_curve = lm[61].y - lm[33].y  # left mouth corner relative to nose
        right_curve = lm[291].y - lm[33].y  # right mouth corner relative to nose
        avg_curve = (left_curve + right_curve) / 2

        if mouth_width > nose_width * 1.1 and avg_curve > 0:
            gestures.append(DetectedGesture("smile", GestureType.FACE, 0.8))

        # ── Open Mouth ──
        if mouth_open_dist > 0.03:
            gestures.append(DetectedGesture("open_mouth", GestureType.FACE, 0.75))

        # ── Blink Detection ──
        # Left eye: upper eyelid (159) to lower eyelid (145)
        left_upper = lm[159]
        left_lower = lm[145]
        left_eye_dist = _distance(left_upper, left_lower)

        # Right eye: upper eyelid (386) to lower eyelid (374)
        right_upper = lm[386]
        right_lower = lm[374]
        right_eye_dist = _distance(right_upper, right_lower)

        # Left iris center for wink detection
        left_iris = lm[468]  # left iris center
        right_iris = lm[473]  # right iris center

        eye_threshold = 0.015

        left_closed = left_eye_dist < eye_threshold
        right_closed = right_eye_dist < eye_threshold

        if left_closed and right_closed:
            gestures.append(DetectedGesture("blink_both", GestureType.FACE, 0.85))
        elif left_closed and not right_closed:
            gestures.append(DetectedGesture("wink_left", GestureType.FACE, 0.8))
        elif right_closed and not left_closed:
            gestures.append(DetectedGesture("wink_right", GestureType.FACE, 0.8))

        # Also detect individual eye blinks
        if left_closed:
            gestures.append(DetectedGesture("blink_left", GestureType.FACE, 0.8))
        if right_closed:
            gestures.append(DetectedGesture("blink_right", GestureType.FACE, 0.8))

        # ── Eyebrow Raise ──
        left_brow = lm[70]
        left_eye_top = lm[159]
        brow_eye_dist = left_brow.y - left_eye_top.y

        if brow_eye_dist > 0.04:
            gestures.append(DetectedGesture("raise_eyebrows", GestureType.FACE, 0.7))

        # ── Frown ──
        inner_brow_left = lm[107]
        inner_brow_right = lm[336]
        brow_center_y = (inner_brow_left.y + inner_brow_right.y) / 2
        nose_bridge_y = lm[6].y

        if brow_center_y < nose_bridge_y - 0.02:
            # Brows are pulled together and down
            gestures.append(DetectedGesture("frown", GestureType.FACE, 0.7))

        # ── Head Pose (using Face Mesh landmarks for high precision) ──
        # Landmark 4: nose tip, 234: user right (left in image), 454: user left (right in image)
        # Landmark 10: top forehead, 152: chin
        face_right = lm[234]
        face_left = lm[454]
        nose_tip = lm[4]
        
        mid_face_x = (face_right.x + face_left.x) / 2
        face_width = abs(face_right.x - face_left.x)
        if face_width > 0.01:
            dev_x = (nose_tip.x - mid_face_x) / face_width
            # If dev_x > 0.16 -> nose is shifted left in face (user turned head left)
            # If dev_x < -0.16 -> nose is shifted right in face (user turned head right)
            if dev_x > 0.16:
                gestures.append(DetectedGesture("head_turn_left", GestureType.FACE, 0.75))
            elif dev_x < -0.16:
                gestures.append(DetectedGesture("head_turn_right", GestureType.FACE, 0.75))

            face_height = abs(lm[10].y - lm[152].y)
            mid_face_y = (lm[10].y + lm[152].y) / 2
            if face_height > 0.01:
                dev_y = (nose_tip.y - mid_face_y) / face_height
                # If dev_y > 0.12 -> nose is shifted down (user nod down)
                # If dev_y < -0.12 -> nose is shifted up (user nod up)
                if dev_y > 0.12:
                    gestures.append(DetectedGesture("head_nod", GestureType.FACE, 0.75))
                elif dev_y < -0.12:
                    gestures.append(DetectedGesture("head_shake", GestureType.FACE, 0.5))

        self._prev_landmarks = face_landmarks
        self._prev_time = now

        return gestures


# ── Gesture Engine (Main) ──────────────────────────────────

class GestureEngine:
    """Continuous gesture recognition engine running in background thread."""

    def __init__(self, on_gesture: Callable[[DetectedGesture], None] | None = None):
        self.on_gesture = on_gesture
        self.on_state: Callable[[dict], None] | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._camera_index = 0
        self._hand_recognizer = HandGestureRecognizer()
        self._face_recognizer = FaceExpressionRecognizer()
        self._gesture_callbacks: dict[str, list[Callable]] = {}
        self._last_gesture_time: dict[str, float] = {}
        self._cooldown = 1.0  # seconds between same gesture
        self._fps = 15
        self._lock = threading.Lock()

        # Consecutive frame thresholds for gestures to prevent false positives (noise filtering)
        self._gesture_thresholds = {
            "fist": 3,
            "pinch": 2,
            "open_palm": 3,
            "grab": 3,
            "thumbs_up": 8,
            "thumbs_down": 8,
            "peace": 8,
            "point_right": 8,
            "point_left": 8,
            "point_up": 8,
            "point_down": 8,
            "ok_sign": 8,
            "wave": 6,
            "swipe_left": 4,
            "swipe_right": 4,
            "rock": 8
        }
        self._gesture_consecutive_frames = {}

        # MediaPipe components (lazy init)
        self._mp_hands = None
        self._mp_face = None
        self._mp_pose = None
        self._mp_drawing = None
        self._hands_model = None
        self._face_model = None
        self._pose_model = None

        # Current state
        self.current_hands = []
        self.current_faces = []
        self.current_gestures = []
        self.current_state = {}
        self._last_frame_jpeg = ""
        self._last_frame_time = 0.0
        self.is_active = False

        # Load gesture config
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load gesture configuration."""
        defaults = {
            "enabled": True,
            "clap_activate": True,
            "face_expressions": True,
            "hand_gestures": True,
            "pose": False,  # heavy + barely used; off by default to save CPU for FX
            "cooldown": 1.0,
            "fps": 30,  # bumped from 15 for smoother cursor control
            "skeleton": True,  # draw neon skeleton on the camera preview
            "mappings": {
                # fist / pinch / open_palm are handled LIVE by gesture_control.py
                # (engage + click + scroll), so leave their discrete action as none.
                "fist": {"action": "none", "description": "Hold to engage control (controller)"},
                "pinch": {"action": "none", "description": "Click while engaged (controller)"},
                "open_palm": {"action": "none", "description": "Scroll mode while engaged (controller)"},
                "grab": {"action": "none", "description": "Drag while engaged (controller)"},
                # Discrete gestures -> real single-shot actions
                "thumbs_up": {"action": "volume_up", "description": "Volume up"},
                "thumbs_down": {"action": "volume_down", "description": "Volume down"},
                "peace": {"action": "media_play_pause", "description": "Play / pause media"},
                "point_right": {"action": "media_next", "description": "Next track"},
                "point_left": {"action": "media_prev", "description": "Previous track"},
                "point_up": {"action": "none", "description": "Reserved (controller uses palm to scroll up)"},
                "point_down": {"action": "none", "description": "Reserved (controller uses palm to scroll down)"},
                "ok_sign": {"action": "take_screenshot", "description": "Take a screenshot"},
                "wave": {"action": "toggle_voice", "description": "Toggle voice mode"},
                "swipe_left": {"action": "press_key_alt_back", "description": "Browser back"},
                "swipe_right": {"action": "press_key_alt_fwd", "description": "Browser forward"},
                "rock": {"action": "trigger_headpat", "description": "IRA headpat reaction"},
                # Face expressions stay as mirror (handled by hud_overlay _on_face)
                "smile": {"action": "none", "description": "Mirror onto avatar"},
                "wink_left": {"action": "none", "description": "Mirror onto avatar"},
                "wink_right": {"action": "none", "description": "Mirror onto avatar"},
                "blink_both": {"action": "none", "description": "Mirror onto avatar"},
                "open_mouth": {"action": "none", "description": "Mirror onto avatar"},
            }
        }

        if os.path.exists(GESTURE_CONFIG):
            try:
                with open(GESTURE_CONFIG, "r") as f:
                    saved = json.load(f)
                # Merge with defaults
                for k, v in defaults.items():
                    if k not in saved:
                        saved[k] = v
                    elif k == "mappings":
                        for mk, mv in defaults["mappings"].items():
                            if mk not in saved["mappings"]:
                                saved["mappings"][mk] = mv
                return saved
            except Exception:
                pass

        # Save defaults
        self._save_config(defaults)
        return defaults

    def _save_config(self, config: dict = None):
        """Save gesture configuration to disk."""
        if config is None:
            config = self._config
        try:
            with open(GESTURE_CONFIG, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"[Gesture] Failed to save config: {e}")

    def _init_mediapipe(self):
        """Lazy-initialize MediaPipe models."""
        import mediapipe as mp

        if self._mp_hands is None:
            self._mp_hands = mp.solutions.hands
            self._hands_model = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )

        if self._mp_face is None:
            self._mp_face = mp.solutions.face_mesh
            self._face_model = self._mp_face.FaceMesh(
                static_image_mode=False,
                max_num_faces=2,
                refine_landmarks=True,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )

        if self._mp_pose is None:
            self._mp_pose = mp.solutions.pose
            # Pose is heavy; only build the model when explicitly enabled.
            if self._config.get("pose", False):
                self._pose_model = self._mp_pose.Pose(
                    static_image_mode=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )

        if self._mp_drawing is None:
            self._mp_drawing = mp.solutions.drawing_utils

    def start(self, camera_index: int = 0):
        """Start the gesture recognition engine."""
        if self._running:
            return

        self._camera_index = camera_index
        self._running = True
        self.is_active = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gesture-engine")
        self._thread.start()
        print("[Gesture] Engine started")

    def stop(self):
        """Stop the gesture recognition engine."""
        self._running = False
        self.is_active = False
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[Gesture] Engine stopped")

    def _gesture_monitor_frame_due(self) -> bool:
        return (time.time() - self._last_frame_time) >= 0.12

    def get_latest_frame_base64(self) -> str:
        """Return the latest JPEG frame from the active camera loop."""
        with self._lock:
            return self._last_frame_jpeg

    def _draw_skeleton(self, frame, hands: list):
        """Draw a neon hand skeleton onto the frame (BGR) for the camera preview.

        Uses direct cv2 polylines/circles for a glowing look — independent of
        MediaPipe drawing_utils color quirks. Connections follow the standard
        MediaPipe Hands topology.
        """
        if frame is None or not hands:
            return frame
        h, w, _ = frame.shape

        # MediaPipe Hands connections (index pairs into the 21 landmarks)
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
            (0, 5), (5, 6), (6, 7), (7, 8),          # index
            (5, 9), (9, 10), (10, 11), (11, 12),     # middle
            (9, 13), (13, 14), (14, 15), (15, 16),   # ring
            (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
            (0, 17),                                  # palm base
        ]
        cyan = (255, 255, 0)      # BGR #00FFFF
        magenta = (245, 95, 213)  # BGR ~#9B59F5 -> warm magenta joint
        out = frame.copy()

        for hand in hands:
            lm = hand.get("landmarks")
            if lm is None or not hasattr(lm, "landmark"):
                continue
            pts = [(int(lm[i].x * w), int(lm[i].y * h)) for i in range(21)]

            # Glow pass: thick translucent cyan underlay
            for a, b in connections:
                cv2.line(out, pts[a], pts[b], cyan, 6, lineType=cv2.LINE_AA)
            # Crisp core line
            for a, b in connections:
                cv2.line(out, pts[a], pts[b], (180, 255, 255), 2, lineType=cv2.LINE_AA)
            # Joints
            for i, p in enumerate(pts):
                col = magenta if i in (4, 8, 12, 16, 20) else cyan  # tips in magenta
                cv2.circle(out, p, 5, col, -1, lineType=cv2.LINE_AA)
                cv2.circle(out, p, 5, (255, 255, 255), 1, lineType=cv2.LINE_AA)
        return out


    def _loop(self):
        """Main detection loop."""
        import cv2

        self._init_mediapipe()

        cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self._camera_index)
        if not cap.isOpened():
            print("[Gesture] Could not open camera")
            self._running = False
            self.is_active = False
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self._config.get("camera_width", 640)))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self._config.get("camera_height", 480)))
        cap.set(cv2.CAP_PROP_FPS, int(self._config.get("fps", 20)))

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.1)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, _ = frame.shape

                detected = []
                frame_hands = []
                frame_faces = []
                primary_state = None

                if not self._config.get("enabled", True):
                    time.sleep(1.0 / self._config.get("fps", 15))
                    continue

                # Hand detection
                if self._config.get("hand_gestures", True):
                    hand_results = self._hands_model.process(rgb)
                    if hand_results.multi_hand_landmarks:
                        for hand_lm, handedness in zip(
                            hand_results.multi_hand_landmarks,
                            hand_results.multi_handedness,
                        ):
                            label = handedness.classification[0].label
                            hand_state = self._hand_recognizer.get_hand_state(hand_lm, label)
                            hand_state["frame_width"] = w
                            hand_state["frame_height"] = h
                            if primary_state is None:
                                primary_state = hand_state
                            gestures = self._hand_recognizer.recognize(hand_lm, label)
                            detected.extend(gestures)
                            frame_hands.append({"landmarks": hand_lm, "handedness": label, "state": hand_state})
                    else:
                        self.current_hands = []

                # Face expression detection
                if self._config.get("face_expressions", True):
                    face_results = self._face_model.process(rgb)
                    pose_results = self._pose_model.process(rgb) if self._pose_model else None

                    if face_results.multi_face_landmarks:
                        for face_lm in face_results.multi_face_landmarks:
                            pose_lm = pose_results.pose_landmarks.landmark if pose_results and pose_results.pose_landmarks else None
                            gestures = self._face_recognizer.recognize(face_lm, pose_results.pose_landmarks if pose_results else None)
                            detected.extend(gestures)
                            frame_faces.append(face_lm)
                    else:
                        self.current_faces = []

                with self._lock:
                    self.current_hands = frame_hands
                    self.current_faces = frame_faces
                    self.current_state = {
                        "timestamp": time.time(),
                        "hands_detected": len(frame_hands),
                        "faces_detected": len(frame_faces),
                        "primary_hand": primary_state,
                    }
                    if self._gesture_monitor_frame_due():
                        # Draw neon skeleton onto a copy for the preview frame
                        preview = frame
                        if self._config.get("skeleton", True):
                            try:
                                preview = self._draw_skeleton(frame, frame_hands)
                            except Exception as e:
                                print(f"[Gesture] skeleton draw failed: {e}")
                        ok, buf = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 68])
                        if ok:
                            self._last_frame_jpeg = base64.b64encode(buf).decode("ascii")
                            self._last_frame_time = time.time()

                if self.on_state and primary_state:
                    try:
                        self.on_state(self.current_state.copy())
                    except Exception as e:
                        print(f"[Gesture] State callback error: {e}")

                # Update consecutive frame counts for detected gestures
                detected_names = {g.name for g in detected}
                for g_name in detected_names:
                    self._gesture_consecutive_frames[g_name] = self._gesture_consecutive_frames.get(g_name, 0) + 1
                for g_name in list(self._gesture_consecutive_frames.keys()):
                    if g_name not in detected_names:
                        self._gesture_consecutive_frames[g_name] = 0

                # Filter out gestures that haven't met consecutive frame thresholds (to filter noise)
                filtered_detected = []
                for g in detected:
                    req_frames = self._gesture_thresholds.get(g.name, 5)  # default 5 frames
                    if self._gesture_consecutive_frames.get(g.name, 0) >= req_frames:
                        filtered_detected.append(g)

                # Filter by cooldown (responsive for controller gestures, strict/longer for discrete actions)
                now = time.time()
                filtered = []
                for g in filtered_detected:
                    last = self._last_gesture_time.get(g.name, 0)
                    if g.name in ("pinch", "fist", "open_palm", "grab"):
                        g_cooldown = self._config.get("cooldown", 0.3)
                    else:
                        g_cooldown = max(1.5, self._config.get("cooldown", 1.0))
                    
                    if (now - last) >= g_cooldown:
                        self._last_gesture_time[g.name] = now
                        # For single-shot gestures, reset consecutive count to require a release/re-engage
                        if g.name not in ("fist", "open_palm", "grab"):
                            self._gesture_consecutive_frames[g.name] = 0
                        filtered.append(g)

                self.current_gestures = filtered

                # Dispatch gestures
                for g in filtered:
                    if self.on_gesture:
                        self.on_gesture(g)
                    # Check registered callbacks
                    for cb in self._gesture_callbacks.get(g.name, []):
                        try:
                            cb(g)
                        except Exception as e:
                            print(f"[Gesture] Callback error for {g.name}: {e}")

                # Throttle
                time.sleep(1.0 / self._config.get("fps", 15))

        finally:
            cap.release()

    def on(self, gesture_name: str, callback: Callable[[DetectedGesture], None]):
        """Register a callback for a specific gesture."""
        if gesture_name not in self._gesture_callbacks:
            self._gesture_callbacks[gesture_name] = []
        self._gesture_callbacks[gesture_name].append(callback)

    def off(self, gesture_name: str, callback: Callable = None):
        """Remove callback(s) for a gesture."""
        if callback:
            self._gesture_callbacks[gesture_name] = [
                cb for cb in self._gesture_callbacks.get(gesture_name, []) if cb != callback
            ]
        else:
            self._gesture_callbacks.pop(gesture_name, None)

    def set_mapping(self, gesture_name: str, action: str, description: str = ""):
        """Set a gesture-to-action mapping."""
        self._config["mappings"][gesture_name] = {
            "action": action,
            "description": description,
        }
        self._save_config()

    def remove_mapping(self, gesture_name: str) -> bool:
        """Remove a gesture mapping."""
        if gesture_name in self._config["mappings"]:
            del self._config["mappings"][gesture_name]
            self._save_config()
            return True
        return False

    def get_mappings(self) -> dict:
        """Get all gesture mappings."""
        return self._config.get("mappings", {})

    def get_config(self) -> dict:
        """Get full gesture config."""
        return self._config.copy()

    def update_config(self, updates: dict):
        """Update gesture config."""
        self._config.update(updates)
        self._save_config()

    def get_status(self) -> dict:
        """Get current engine status."""
        return {
            "running": self._running,
            "camera_index": self._camera_index,
            "current_gestures": [g.name for g in self.current_gestures],
            "hands_detected": len(self.current_hands),
            "faces_detected": len(self.current_faces),
            "mappings_count": len(self._config.get("mappings", {})),
        }


# ── Singleton ──────────────────────────────────────────────

_engine: GestureEngine | None = None


def get_engine() -> GestureEngine:
    """Get or create the global gesture engine."""
    global _engine
    if _engine is None:
        _engine = GestureEngine()
    return _engine
