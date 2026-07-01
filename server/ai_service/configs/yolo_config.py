"""YOLOv8 object detection configuration."""
from __future__ import annotations
from configs.base import ModuleConfig


class YoloConfig(ModuleConfig):
    """Configuration for YOLOv8n object detection."""

    enabled: bool = True
    # YOLO model variant (yolov8n.pt, yolov8s.pt, etc.)
    model_name: str = "yolov8n.pt"
    # Confidence threshold for detections (0.0 to 1.0)
    confidence_threshold: float = 0.35
    # IOU threshold for NMS
    iou_threshold: float = 0.45
    # Max detections per image
    max_detections: int = 150
    # Device to run inference on
    device: str = "cuda"