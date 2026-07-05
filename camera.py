"""IRA Camera Module — webcam capture for visual awareness."""

from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from pathlib import Path

import cv2
from PIL import Image

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRATCH_DIR = os.path.join(ROOT_DIR, "scratch")


def _get_camera(index: int = 0) -> cv2.VideoCapture:
    """Open webcam by device index."""
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    return cap


def capture_photo(camera_index: int = 0) -> str:
    """Capture a single photo from the webcam. Returns base64 PNG + saves to scratch."""
    cap = _get_camera(camera_index)
    if not cap.isOpened():
        return "Error: Could not open webcam. Make sure a camera is connected."

    try:
        # Warm up camera
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        if not ret or frame is None:
            return "Error: Could not capture frame from webcam."

        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        # Resize if too large (max 1280px wide)
        w, h = img.size
        if w > 1280:
            ratio = 1280 / w
            img = img.resize((1280, int(h * ratio)), Image.LANCZOS)

        # Save to scratch
        os.makedirs(SCRATCH_DIR, exist_ok=True)
        save_path = os.path.join(SCRATCH_DIR, "camera_capture.png")
        img.save(save_path, "PNG")

        # Read raw bytes from the saved file to avoid double compression
        with open(save_path, "rb") as f:
            png_bytes = f.read()
        b64 = base64.b64encode(png_bytes).decode()

        return f"Camera photo captured successfully. Size: {img.size[0]}x{img.size[1]}. Saved to: {save_path}"

    finally:
        cap.release()


def get_frame(camera_index: int = 0):
    """Capture a single frame as numpy array. Used by gesture engine."""
    cap = _get_camera(camera_index)
    try:
        for _ in range(3):
            cap.read()
        ret, frame = cap.read()
        if ret and frame is not None:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return None
    finally:
        cap.release()


def get_frame_base64(camera_index: int = 0) -> str:
    """Capture a frame and return as base64 PNG string."""
    cap = _get_camera(camera_index)
    try:
        for _ in range(3):
            cap.read()
        ret, frame = cap.read()
        if not ret or frame is None:
            return ""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()
    finally:
        cap.release()


def list_cameras() -> list[dict]:
    """Detect available cameras."""
    cameras = []
    for i in range(4):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cameras.append({"index": i, "width": w, "height": h})
            cap.release()
    return cameras
