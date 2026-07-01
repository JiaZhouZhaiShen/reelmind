"""Scene detection worker — runs in a subprocess for crash isolation.

Called by pipeline.py via subprocess. Each invocation:
  1. Loads TransNetV2 model from scratch
  2. Processes ONE video
  3. Outputs JSON results to stdout
  4. Exits (freeing GPU memory completely)
"""

from __future__ import annotations
import json, sys, os

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing video_path argument"}), file=sys.stderr)
        sys.exit(1)

    video_path = sys.argv[1]

    # Import inside worker so the parent process doesn't load torch
    from services.scene_service import detect_scenes

    try:
        scenes = detect_scenes(video_path)
        print(json.dumps(scenes))
        sys.exit(0)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(json.dumps({"error": str(e), "traceback": tb}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
