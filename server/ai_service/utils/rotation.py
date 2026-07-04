"""Video rotation detection and correction utilities.

Detects display rotation from ffprobe tags / side data.
Used by all AI services that read video frames via OpenCV.
"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Optional


def get_video_rotation(video_path: str | Path) -> int:
    """Detect the intended display rotation of a video file.

    Checks (in order):
      1. Stream tags.rotate (most common, used by phones/tablets)
      2. Side data display_matrix (rare, alternative encoding)

    Returns:
        0, 90, 180, or 270 degrees
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") != "video":
                continue
            tags = stream.get("tags", {})
            rotate_tag = tags.get("rotate")
            if rotate_tag is not None:
                return int(rotate_tag) % 360
            side_data_list = stream.get("side_data_list", [])
            for sd in side_data_list:
                if sd.get("side_data_type") == "Display Matrix":
                    r = sd.get("rotation")
                    if r is not None:
                        return int(r) % 360
        return 0
    except Exception:
        return 0


def apply_rotation(frame, rotation: int):
    """Rotate an OpenCV frame according to display rotation.

    Args:
        frame: OpenCV BGR frame from cv2.VideoCapture.read()
        rotation: 0, 90, 180, or 270 degrees

    Returns:
        Rotated frame (or original if rotation == 0)
    """
    import cv2

    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame
