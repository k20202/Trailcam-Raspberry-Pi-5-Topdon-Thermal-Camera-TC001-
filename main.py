#!/usr/bin/env python3
import cv2
import numpy as np
import time
import datetime
import os
import sys
from collections import deque

# Force headless behaviour; Pi screen no longer used
HAS_DISPLAY = False

WIDTH = 256
HEIGHT = 192
DISPLAY_SCALE = 3
CAMERA_FPS = 25

# ------------------------------------------------------------
# CONFIGURABLE PARAMETERS
# ------------------------------------------------------------

DELTA_TEMP_C = 1.5
THERMAL_DELTA_RAW = int(DELTA_TEMP_C * 64)

BG_UPDATE_ALPHA = 0.01
MIN_HOT_AREA = 30
SPLIT_DISTANCE_PX = 20

PRE_ROLL_SEC = 10
POST_ROLL_SEC = 10
PHOTO_INTERVAL_SEC = 20

TRACK_FORGET_SEC = POST_ROLL_SEC
TRACK_MAX_DIST = 40 * 40

# Record videos at the same scale as live display for crispness
VIDEO_SCALE = DISPLAY_SCALE
VIDEO_SIZE = (WIDTH * VIDEO_SCALE, HEIGHT * VIDEO_SCALE)

# Background reset flag (touched by web UI)
RESET_FLAG_PATH = "/tmp/trailcam_reset_bg"

# Optional flicker smoothing for the visual channel
ENABLE_VISUAL_SMOOTHING = False
VISUAL_SMOOTH_ALPHA = 0.4  # 0–1, higher = more smoothing (and more lag)

# ------------------------------------------------------------
# STORAGE STRUCTURE (LOCAL, PERSISTENT ON SD CARD)
# ------------------------------------------------------------

# With overlay filesystem disabled, this lives directly on /dev/mmcblk0p2
BASE_MEDIA_DIR = os.path.join("/home/kasper", "media")
PHOTO_DIR = os.path.join(BASE_MEDIA_DIR, "photos")
VIDEO_DIR = os.path.join(BASE_MEDIA_DIR, "videos")
VIDEO_TRACKED_DIR = os.path.join(BASE_MEDIA_DIR, "videos_tracked")
LIVE_JPEG_PATH = os.path.join(BASE_MEDIA_DIR, "live.jpg")
STATUS_PATH = os.path.join(BASE_MEDIA_DIR, "status.json")

for d in (BASE_MEDIA_DIR, PHOTO_DIR, VIDEO_DIR, VIDEO_TRACKED_DIR):
    os.makedirs(d, exist_ok=True)

# ------------------------------------------------------------
# COLOUR LOGGING (ANSI with fallback)
# ------------------------------------------------------------
def _supports_color():
    return sys.stdout.isatty()

if _supports_color():
    COL_INFO = "\033[92m"
    COL_TRACK = "\033[94m"
    COL_RECORD = "\033[95m"
    COL_WARN = "\033[91m"
    COL_RESET = "\033[0m"
else:
    COL_INFO = COL_TRACK = COL_RECORD = COL_WARN = COL_RESET = ""

def log_info(msg):   print(f"{COL_INFO}[INFO]{COL_RESET} {msg}")
def log_track(msg):  print(f"{COL_TRACK}[TRACK]{COL_RESET} {msg}")
def log_record(msg): print(f"{COL_RECORD}[RECORD]{COL_RESET} {msg}")
def log_warn(msg):   print(f"{COL_WARN}[WARN]{COL_RESET} {msg}")

# ------------------------------------------------------------
# CAMERA OPEN / AUTODETECT (Pi/Linux friendly)
# ------------------------------------------------------------

def open_tc001_capture():
    """
    TC001 on Linux often appears as /dev/video1 or /dev/video2 etc.
    It outputs a 256x384 YUYV stream where:
      top half = visual (grayscale luma)
      bottom half = thermal raw (2 bytes per pixel)
    We try indices 0..4 and pick the one that looks like 256x384.
    """
    for idx in range(0, 5):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            continue

        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        time.sleep(0.3)

        ret, frame = cap.read()
        if not ret or frame is None:
            cap.release()
            continue

        h, w = frame.shape[:2]
        # stacked layout: 256x384 (h=384,w=256) or very close
        if (w == WIDTH and h >= HEIGHT * 2) or (h == HEIGHT and w >= WIDTH * 2):
            log_info(f"Using camera index {idx} with frame {w}x{h}")
            return cap

        cap.release()

    return None

# ------------------------------------------------------------
# TC001 DECODE (dual-layout)
# ------------------------------------------------------------

def decode_visual(frame):
    """
    Returns 8-bit visual grayscale (HEIGHT x WIDTH).
    Handles:
      A) Pi stacked 256x384 YUYV (take top half luma)
      B) Windows-style packed row (split row into halves)
    """
    h, w = frame.shape[:2]

    # Layout A: stacked 256x384 (or similar)
    if h >= HEIGHT * 2 and w == WIDTH:
        top = frame[:HEIGHT, :, :]
        if top.ndim == 3 and top.shape[2] >= 1:
            return top[:, :, 0].copy()
        return top.copy()

    # Layout B: packed single row carrying visual + thermal
    row = frame[0]
    im_row, _ = np.array_split(row, 2)
    imdata = np.frombuffer(im_row, dtype=np.uint8).reshape(HEIGHT, WIDTH, 2)
    return imdata[:, :, 0]

def decode_thermal_raw(frame):
    """
    Returns 16-bit thermal raw (HEIGHT x WIDTH).
    Layout A: stacked 256x384 YUYV, thermal in bottom half (2 bytes per pixel).
    Layout B: packed row split.
    """
    h, w = frame.shape[:2]

    # Layout A: stacked
    if h >= HEIGHT * 2 and w == WIDTH:
        bottom = frame[HEIGHT:HEIGHT * 2, :, :]
        if bottom.ndim == 3 and bottom.shape[2] >= 2:
            low = bottom[:, :, 0].astype(np.uint16)
            high = bottom[:, :, 1].astype(np.uint16)
            return low + (high << 8)
        buf = bottom.tobytes()
        th = np.frombuffer(buf, dtype=np.uint16, count=WIDTH * HEIGHT)
        return th.reshape(HEIGHT, WIDTH)

    # Layout B: packed
    row = frame[0]
    _, th_row = np.array_split(row, 2)
    thdata = np.frombuffer(th_row, dtype=np.uint8).reshape(HEIGHT, WIDTH, 2)
    low = thdata[:, :, 0].astype(np.uint16)
    high = thdata[:, :, 1].astype(np.uint16)
    return low + (high << 8)

# ------------------------------------------------------------
# HOT OBJECT SEGMENTATION
# ------------------------------------------------------------

def detect_hot_objects(thermal_raw, background):
    delta = thermal_raw.astype(np.int32) - background.astype(np.int32)
    hot_mask = delta > THERMAL_DELTA_RAW

    new_bg = background.copy()
    cold = ~hot_mask
    new_bg[cold] = (1.0 - BG_UPDATE_ALPHA) * new_bg[cold] + BG_UPDATE_ALPHA * thermal_raw[cold]

    mask_u8 = (hot_mask.astype(np.uint8) * 255)
    kernel = np.ones((3, 3), np.uint8)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_u8 = cv2.dilate(mask_u8, kernel, iterations=2)
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detections = []
    for c in contours:
        if cv2.contourArea(c) < MIN_HOT_AREA:
            continue
        x, y, w, h = cv2.boundingRect(c)
        detections.append({"bbox": (x, y, w, h), "cx": x + w / 2, "cy": y + h / 2})

    return detections, new_bg

# ------------------------------------------------------------
# MERGE CLOSE / OVERLAPPING BLOBS
# ------------------------------------------------------------

def _rects_intersect(b1, b2, pad=0):
    x1, y1, w1, h1 = b1
    x2, y2, w2, h2 = b2
    a1x1, a1y1, a1x2, a1y2 = x1 - pad, y1 - pad, x1 + w1 + pad, y1 + h1 + pad
    a2x1, a2y1, a2x2, a2y2 = x2 - pad, y2 - pad, x2 + w2 + pad, y2 + h2 + pad
    return not (a1x2 < a2x1 or a2x2 < a1x1 or a1y2 < a2y1 or a2y2 < a1y1)

def _union_bbox(b1, b2):
    x1, y1, w1, h1 = b1
    x2, y2, w2, h2 = b2
    xa1, ya1, xa2, ya2 = x1, y1, x1 + w1, y1 + h1
    xb1, yb1, xb2, yb2 = x2, y2, x2 + w2, y2 + h2
    x = min(xa1, xb1)
    y = min(ya1, yb1)
    xe = max(xa2, xb2)
    ye = max(ya2, yb2)
    return (x, y, xe - x, ye - y)

def merge_detections(detections):
    dets = [d.copy() for d in detections]

    changed = True
    while changed:
        changed = False
        out = []
        used = [False] * len(dets)

        for i in range(len(dets)):
            if used[i]:
                continue
            b1 = dets[i]["bbox"]

            merged_bbox = b1
            used[i] = True

            for j in range(i + 1, len(dets)):
                if used[j]:
                    continue
                b2 = dets[j]["bbox"]
                overlap = _rects_intersect(merged_bbox, b2, pad=0)
                cx1 = merged_bbox[0] + merged_bbox[2] / 2
                cy1 = merged_bbox[1] + merged_bbox[3] / 2
                cx2 = b2[0] + b2[2] / 2
                cy2 = b2[1] + b2[3] / 2
                dx = cx1 - cx2
                dy = cy1 - cy2
                close = (dx * dx + dy * dy) ** 0.5 < SPLIT_DISTANCE_PX

                if close or overlap:
                    merged_bbox = _union_bbox(merged_bbox, b2)
                    used[j] = True
                    changed = True

            x, y, w, h = merged_bbox
            out.append(
                {
                    "bbox": merged_bbox,
                    "cx": x + w / 2,
                    "cy": y + h / 2,
                }
            )

        dets = out

    return dets

# ------------------------------------------------------------
# TRACKING
# ------------------------------------------------------------

def generate_color(tid):
    rng = np.random.RandomState(tid * 9973 + 12345)
    return tuple(int(x) for x in rng.randint(50, 255, 3))

def update_tracks(detections, tracks, now):
    used = set()
    visible = []

    for tid, t in list(tracks.items()):
        best = -1
        best_d2 = TRACK_MAX_DIST
        for i, d in enumerate(detections):
            if i in used:
                continue
            dx = d["cx"] - t["cx"]
            dy = d["cy"] - t["cy"]
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best = i

        if best >= 0:
            d = detections[best]
            t["cx"], t["cy"], t["bbox"] = d["cx"], d["cy"], d["bbox"]
            t["last"] = now
            used.add(best)
            visible.append((tid, t))

    next_id = max([0] + list(tracks.keys())) + 1
    for i, d in enumerate(detections):
        if i in used:
            continue
        tid = next_id
        next_id += 1
        tracks[tid] = {
            "cx": d["cx"],
            "cy": d["cy"],
            "bbox": d["bbox"],
            "last": now,
            "color": generate_color(tid),
        }
        visible.append((tid, tracks[tid]))
        log_track(f"New ID {tid} at ({d['cx']:.1f},{d['cy']:.1f})")

    for tid in list(tracks.keys()):
        if now - tracks[tid]["last"] > TRACK_FORGET_SEC:
            del tracks[tid]

    return tracks, visible

# ------------------------------------------------------------
# VIDEO WRITER + HELPERS
# ------------------------------------------------------------

def make_writer(path_base, fps, size):
    is_windows = sys.platform.startswith("win")

    if is_windows:
        codecs_to_try = ("mp4v", "XVID", "MJPG")
    else:
        codecs_to_try = ("avc1", "H264", "mp4v", "MJPG")

    for fourcc_str in codecs_to_try:
        ext = "mp4" if fourcc_str in ("mp4v", "avc1", "H264") else "avi"
        path = f"{path_base}.{ext}"

        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        w = cv2.VideoWriter(path, fourcc, fps, size)

        if w.isOpened():
            return w, fourcc_str, ext

        try:
            w.release()
        except Exception:
            pass

    return None, None, None

def upscale_gray_to_bgr(gray):
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return cv2.resize(bgr, VIDEO_SIZE, interpolation=cv2.INTER_NEAREST)

def format_hhmmss(sec):
    sec = int(max(0, sec))
    hh = sec // 3600
    mm = (sec % 3600) // 60
    ss = sec % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"

def write_status(recording, events):
    """Write lightweight JSON status for the web UI."""
    import json
    tmp_path = STATUS_PATH + ".tmp"
    data = {
        "recording": bool(recording),
        "events": int(events),
        "ts": time.time(),
    }
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, STATUS_PATH)
    except Exception:
        pass

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    cap = open_tc001_capture()
    if cap is None:
        log_warn("Camera init failed. Check v4l2 devices.")
        return

    # warm up until we get a valid full frame
    for _ in range(20):
        ret, frame = cap.read()
        if ret and frame is not None:
            h, w = frame.shape[:2]
            if (w == WIDTH and h >= HEIGHT * 2) or (h == HEIGHT and w >= WIDTH * 2):
                break
        time.sleep(0.05)
    else:
        log_warn("Camera stream not producing expected frames.")
        return

    try:
        visual = decode_visual(frame)
        thermal = decode_thermal_raw(frame)
    except Exception as e:
        log_warn(f"Initial decode failed: {e}")
        return

    background = thermal.astype(np.float32)

    # optional smoothing state
    vis_smooth = visual.astype(np.float32)

    prebuffer = deque(maxlen=PRE_ROLL_SEC * CAMERA_FPS)
    tracks = {}
    recording = False
    raw_out = trk_out = None

    last_seen = 0
    last_photo_time = 0

    recording_start_time = None
    recording_label = None
    raw_path = trk_path = None

    last_objects_present = False
    last_ids = []
    last_recording_state = False

    # count how many recording events have started since this process started
    events_count = 0
    # initial status for web UI
    write_status(False, events_count)

    log_info("TC001 Thermal Tracker running...")
    log_info(f"Media root: {BASE_MEDIA_DIR}")

    while True:
        now = time.time()

        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        # decode safely; skip weird frames
        try:
            visual = decode_visual(frame)
            thermal = decode_thermal_raw(frame)
            if visual.shape != (HEIGHT, WIDTH):
                continue
        except Exception:
            continue

        # background reset trigger (from web UI)
        if os.path.exists(RESET_FLAG_PATH):
            background = thermal.astype(np.float32)
            try:
                os.remove(RESET_FLAG_PATH)
            except OSError:
                pass

        # update smoothing
        if ENABLE_VISUAL_SMOOTHING:
            vis_smooth[:] = (1.0 - VISUAL_SMOOTH_ALPHA) * vis_smooth + VISUAL_SMOOTH_ALPHA * visual.astype(np.float32)
            visual_out = vis_smooth.astype(np.uint8)
        else:
            visual_out = visual

        prebuffer.append(visual_out.copy())

        # object detection/tracking uses thermal only
        detections, background = detect_hot_objects(thermal, background)
        merged = merge_detections(detections)
        tracks, visible = update_tracks(merged, tracks, now)

        # write latest frame for web live-view (smoothed visual)
        try:
            cv2.imwrite(LIVE_JPEG_PATH, visual_out)
        except Exception:
            pass

        ids_now = sorted([tid for tid, _ in visible])
        objects_present = len(ids_now) > 0
        in_frame = len(visible)

        # ---------------- START RECORDING ----------------
        if objects_present and not recording:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            recording_label = ts

            raw_base = os.path.join(VIDEO_DIR, ts)
            trk_base = os.path.join(VIDEO_TRACKED_DIR, ts)

            raw_out, raw_cc, raw_ext = make_writer(raw_base, CAMERA_FPS, VIDEO_SIZE)
            trk_out, trk_cc, trk_ext = make_writer(trk_base, CAMERA_FPS, VIDEO_SIZE)
            if raw_out is None or trk_out is None:
                log_warn("VideoWriter init failed (no working codec).")
                recording = False
                if raw_out:
                    raw_out.release()
                if trk_out:
                    trk_out.release()
                raw_out = trk_out = None
                raw_path = trk_path = None
            else:
                raw_path = f"{raw_base}.{raw_ext}"
                trk_path = f"{trk_base}.{trk_ext}"

                for f in prebuffer:
                    pre_scaled = upscale_gray_to_bgr(f)
                    raw_out.write(pre_scaled)
                    trk_out.write(pre_scaled)

                recording = True
                last_seen = now
                last_photo_time = 0
                recording_start_time = now

                events_count += 1
                write_status(recording, events_count)

            # snapshot at start (silent) using smoothed visual
            photo_path = os.path.join(PHOTO_DIR, f"{ts}.jpg")
            cv2.imwrite(photo_path, visual_out)

        # ---------------- DURING RECORDING ----------------
        if recording:
            if objects_present:
                last_seen = now

            # periodic photos (silent)
            if objects_present and (now - last_photo_time >= PHOTO_INTERVAL_SEC):
                ts_p = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                photo_path = os.path.join(PHOTO_DIR, f"{ts_p}.jpg")
                cv2.imwrite(photo_path, visual_out)
                last_photo_time = now

            raw_scaled = upscale_gray_to_bgr(visual_out)
            raw_out.write(raw_scaled)

            trk_scaled = upscale_gray_to_bgr(visual_out)
            for tid, t in visible:
                x, y, w, h = t["bbox"]
                color = t["color"]

                xs = int(x * VIDEO_SCALE)
                ys = int(y * VIDEO_SCALE)
                ws = int(w * VIDEO_SCALE)
                hs = int(h * VIDEO_SCALE)

                cv2.rectangle(
                    trk_scaled,
                    (xs, ys),
                    (xs + ws, ys + hs),
                    color,
                    2,
                    lineType=cv2.LINE_8,
                )

                label = f"ID{tid}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                lx = xs + ws - tw - 6
                ly = ys + hs - 6

                cv2.putText(
                    trk_scaled,
                    label,
                    (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    color,
                    2,
                    lineType=cv2.LINE_AA,
                )

            trk_out.write(trk_scaled)

            if (not objects_present) and (now - last_seen > POST_ROLL_SEC):
                recording = False
                raw_out.release()
                trk_out.release()
                raw_out = trk_out = None
                prebuffer.clear()

                rec_len = format_hhmmss(now - recording_start_time)
                recording_start_time = None

                write_status(recording, events_count)

                print(f"{COL_RECORD}[RECORD]{COL_RESET} STOP {recording_label} | LENGTH:{rec_len}")

        # ---------------- OPTIONAL LIVE DISPLAY (currently disabled) ----------------
        if HAS_DISPLAY:
            display = cv2.resize(
                cv2.cvtColor(visual_out, cv2.COLOR_GRAY2BGR),
                (WIDTH * DISPLAY_SCALE, HEIGHT * DISPLAY_SCALE),
                interpolation=cv2.INTER_NEAREST,
            )

            for tid, t in visible:
                x, y, w, h = t["bbox"]
                color = t["color"]

                cv2.rectangle(
                    display,
                    (x * DISPLAY_SCALE, y * DISPLAY_SCALE),
                    ((x + w) * DISPLAY_SCALE, (y + h) * DISPLAY_SCALE),
                    color,
                    2,
                    lineType=cv2.LINE_8,
                )

                label = f"ID{tid}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                lx = (x + w) * DISPLAY_SCALE - tw - 6
                ly = (y + h) * DISPLAY_SCALE - 6

                cv2.putText(
                    display,
                    label,
                    (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                    lineType=cv2.LINE_AA,
                )

            cv2.imshow("TC001 Thermal Tracker", display)

        # ---------------- EVENT-BASED CONSOLE ----------------
        ids_changed = ids_now != last_ids
        objects_changed = objects_present != last_objects_present

        if objects_changed or ids_changed:
            if recording and not last_recording_state:
                print(
                    f"{COL_INFO}[STATUS]{COL_RESET} "
                    f"OBJ:{in_frame} | IDs:{','.join(map(str, ids_now)) if ids_now else 'none'} | "
                    f"REC:ON@{recording_label}"
                )
            else:
                rec_text = f"ON@{recording_label}" if recording else "OFF"
                print(
                    f"{COL_INFO}[STATUS]{COL_RESET} "
                    f"OBJ:{in_frame} | IDs:{','.join(map(str, ids_now)) if ids_now else 'none'} | "
                    f"REC:{rec_text}"
                )

            last_ids = ids_now
            last_objects_present = objects_present
            last_recording_state = recording

        if HAS_DISPLAY:
            if cv2.waitKey(1) & 0xFF == ord("q"):
                log_info("Exit requested.")
                break
        else:
            time.sleep(0.001)

    cap.release()
    if HAS_DISPLAY:
        cv2.destroyAllWindows()
    log_info("Shut down cleanly.")

if __name__ == "__main__":
    main()
