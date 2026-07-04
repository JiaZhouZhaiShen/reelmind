import numpy as np
from transnetv2_pytorch import TransNetV2

VIDEO_PATH = "/nas-media/PR视频/2026/乐山私董会成片/乐山私董会成片.mp4"

model = TransNetV2()
model = model.to("cpu")
model.eval()

video_frames, one_hot_preds, many_hot_preds = model.predict_video(VIDEO_PATH, quiet=True)

print(f"Video duration (frames): {len(video_frames)} seconds")
print(f"one_hot shape: {one_hot_preds.shape}")
print(f"many_hot shape: {many_hot_preds.shape}")

# one-hot: class 0 = no cut, class 1 = cut
oh_cut = one_hot_preds[:, 1].numpy().flatten()
print(f"\none_hot class 1 (cut probability):")
print(f"  max: {oh_cut.max():.4f}, min: {oh_cut.min():.4f}, mean: {oh_cut.mean():.4f}")
print(f"  > 0.5: {(oh_cut > 0.5).sum()}, > 0.3: {(oh_cut > 0.3).sum()}, > 0.1: {(oh_cut > 0.1).sum()}")

# many-hot: single channel boundary probability (what the code uses)
mh = many_hot_preds.numpy().flatten()
print(f"\nmany_hot (what detect_scenes currently uses):")
print(f"  max: {mh.max():.4f}, min: {mh.min():.4f}, mean: {mh.mean():.4f}")
print(f"  > 0.5: {(mh > 0.5).sum()}, > 0.3: {(mh > 0.3).sum()}, > 0.1: {(mh > 0.1).sum()}")

print(f"\none_hot top 10 scores: {[round(x,4) for x in sorted(oh_cut, reverse=True)[:10]]}")
print(f"many_hot top 10 scores: {[round(x,4) for x in sorted(mh, reverse=True)[:10]]}")

# one_hot[:, 0] = no-cut probability (inverse of class 1)
oh_no_cut = one_hot_preds[:, 0].numpy().flatten()
print(f"\none_hot class 0 (no-cut probability - typically HIGH for no cut):")
print(f"  max: {oh_no_cut.max():.4f}, min: {oh_no_cut.min():.4f}, mean: {oh_no_cut.mean():.4f}")
print(f"  < 0.5: {(oh_no_cut < 0.5).sum()}")
