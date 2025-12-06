#!/usr/bin/env python3
import os
import time
import json
import zipfile
import tempfile

from flask import (
    Flask, Response, send_from_directory,
    render_template_string, abort, redirect, url_for,
    send_file, after_this_request, request
)

# Paths must match main.py
MEDIA_ROOT = "/home/kasper/media"
PHOTO_DIR = os.path.join(MEDIA_ROOT, "photos")
VIDEO_DIR = os.path.join(MEDIA_ROOT, "videos")
VIDEO_TRACKED_DIR = os.path.join(MEDIA_ROOT, "videos_tracked")
LIVE_JPEG_PATH = os.path.join(MEDIA_ROOT, "live.jpg")

# Background reset flag watched by main.py
RESET_FLAG_PATH = "/tmp/trailcam_reset_bg"

# Status file written by main.py
STATUS_PATH = os.path.join(MEDIA_ROOT, "status.json")

# Network state + desired-mode files used by trailcam_netmgr.py
NET_STATE_PATH = "/run/trailcam_net_state.json"
DESIRED_MODE_PATH = "/run/trailcam_desired_mode.json"

app = Flask(__name__)

HTML_INDEX = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Trailcam Live</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { margin:0; background:#000; color:#fff; font-family:sans-serif; }
    .wrap { display:flex; flex-direction:column; min-height:100vh; }
    .top { flex:1; display:flex; align-items:center; justify-content:center; background:#000; }
    .top img { width:100%; height:100%; object-fit:contain; }
    .bot { padding:10px; background:#111; }
    a, a:visited { color:#6cf; text-decoration:none; }
    a:hover { text-decoration:underline; }
    .btn-row { margin-bottom:10px; }
    .btn { display:inline-block; padding:8px 12px; margin-right:8px; background:#222; border-radius:6px; border:0; color:#6cf; cursor:pointer; }
    form { display:inline; }
    .status { margin-top:8px; font-size:0.85rem; color:#aaa; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <img src="{{ url_for('stream') }}" alt="Live">
    </div>
    <div class="bot">
      <div class="btn-row">
        <a class="btn" href="{{ url_for('files') }}">Browse files</a>
        <form method="post" action="{{ url_for('reset_background') }}">
          <button class="btn" type="submit">Reset background</button>
        </form>
        <form method="post" action="{{ url_for('set_mode_wifi') }}">
          <button class="btn" type="submit">Use Wi-Fi mode</button>
        </form>
        <form method="post" action="{{ url_for('set_mode_ap') }}">
          <button class="btn" type="submit">Use AP mode</button>
        </form>
      </div>
      <div>
        <small>Live view comes from the latest frame saved by the recorder.</small>
      </div>
      <div class="status">
        Events this run: {{ events }} &nbsp;|&nbsp;
        Recording: {{ "ON" if recording else "OFF" }}<br>
        Network:
        {% if net_mode == "wifi" %}
          Wi-Fi client
          {% if net_signal is not none %}(signal {{ net_signal }} dBm){% endif %}
        {% elif net_mode == "ap" %}
          Access Point (hotspot)
        {% else %}
          Unknown
        {% endif %}
      </div>
    </div>
  </div>
</body>
</html>
"""

HTML_FILES = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Trailcam Files</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { background:#000; color:#fff; font-family:sans-serif; padding:10px; }
    h2 { margin-top:20px; }
    a, a:visited { color:#6cf; text-decoration:none; }
    a:hover { text-decoration:underline; }
    ul { list-style:none; padding-left:0; }
    li { margin:4px 0; }
    .delbtn { margin-left:8px; padding:2px 6px; border-radius:4px; border:0; background:#700; color:#fff; cursor:pointer; font-size:0.8rem; }
    .dlbtn { margin-left:8px; padding:2px 6px; border-radius:4px; border:0; background:#246; color:#fff; cursor:pointer; font-size:0.8rem; text-decoration:none; }
    form { display:inline; }
    .footer { margin-top:20px; font-size:0.85rem; color:#aaa; }
    .warn { font-size:0.85rem; color:#faa; margin-top:4px; }
    .big-del { margin:10px 0; padding:6px 10px; border-radius:6px; border:0; background:#900; color:#fff; cursor:pointer; }
    .status { font-size:0.85rem; color:#aaa; margin-bottom:10px; }
  </style>
</head>
<body>
  <h1>Trailcam Files</h1>

  <p class="status">
    Network:
    {% if net_mode == "wifi" %}
      Wi-Fi client
      {% if net_signal is not none %}(signal {{ net_signal }} dBm){% endif %}
    {% elif net_mode == "ap" %}
      Access Point (hotspot)
    {% else %}
      Unknown
    {% endif %}
  </p>

  <div class="status">
    <form method="post" action="{{ url_for('set_mode_wifi') }}">
      <button class="btn" type="submit">Use Wi-Fi mode</button>
    </form>
    <form method="post" action="{{ url_for('set_mode_ap') }}">
      <button class="btn" type="submit">Use AP mode</button>
    </form>
  </div>

  <form method="post" action="{{ url_for('delete_all', target='all') }}">
    <button class="big-del" type="submit">
      Delete ALL media (videos, tracked videos, photos)
    </button>
  </form>
  <div class="warn">
    Note: Deleting media is irreversible. Once deleted, files cannot be recovered.
  </div>

  <p>
    <form method="get" action="{{ url_for('download_all_media') }}">
      <button class="dlbtn" type="submit">Download ALL media as ZIP</button>
    </form>
  </p>

  <h2>Videos</h2>
  <form method="post" action="{{ url_for('delete_all', target='videos') }}">
    <button class="delbtn" type="submit">Delete all videos</button>
  </form>
  <ul>
    {% for f in videos %}
    <li>
      <a href="{{ url_for('view_file', folder='videos', fname=f) }}">{{ f }}</a>
      <a class="dlbtn" href="{{ url_for('download', folder='videos', fname=f) }}">Download</a>
      <form method="post" action="{{ url_for('delete_file', folder='videos', fname=f) }}">
        <button class="delbtn" type="submit">Delete</button>
      </form>
    </li>
    {% endfor %}
    {% if not videos %}
    <li><em>No videos yet.</em></li>
    {% endif %}
  </ul>

  <h2>Tracked Videos</h2>
  <form method="post" action="{{ url_for('delete_all', target='videos_tracked') }}">
    <button class="delbtn" type="submit">Delete all tracked videos</button>
  </form>
  <ul>
    {% for f in videos_trk %}
    <li>
      <a href="{{ url_for('view_file', folder='videos_tracked', fname=f) }}">{{ f }}</a>
      <a class="dlbtn" href="{{ url_for('download', folder='videos_tracked', fname=f) }}">Download</a>
      <form method="post" action="{{ url_for('delete_file', folder='videos_tracked', fname=f) }}">
        <button class="delbtn" type="submit">Delete</button>
      </form>
    </li>
    {% endfor %}
    {% if not videos_trk %}
    <li><em>No tracked videos yet.</em></li>
    {% endif %}
  </ul>

  <h2>Photos</h2>
  <form method="post" action="{{ url_for('delete_all', target='photos') }}">
    <button class="delbtn" type="submit">Delete all photos</button>
  </form>
  <ul>
    {% for f in photos %}
    <li>
      <a href="{{ url_for('view_file', folder='photos', fname=f) }}">{{ f }}</a>
      <a class="dlbtn" href="{{ url_for('download', folder='photos', fname=f) }}">Download</a>
      <form method="post" action="{{ url_for('delete_file', folder='photos', fname=f) }}">
        <button class="delbtn" type="submit">Delete</button>
      </form>
    </li>
    {% endfor %}
    {% if not photos %}
    <li><em>No photos yet.</em></li>
    {% endif %}
  </ul>

  <p><a href="{{ url_for('index') }}">⬅ Back to live view</a></p>

  <div class="footer">
    Events this run: {{ events }} &nbsp;|&nbsp;
    Recording: {{ "ON" if recording else "OFF" }}
  </div>
</body>
</html>
"""

def get_status():
    """Read status.json written by main.py."""
    try:
        with open(STATUS_PATH, "r") as f:
            data = json.load(f)
        recording = bool(data.get("recording", False))
        events = int(data.get("events", 0))
    except Exception:
        recording = False
        events = 0
    return recording, events

def get_net_state():
    """Read mode info written by trailcam_netmgr.py."""
    try:
        with open(NET_STATE_PATH, "r") as f:
            data = json.load(f)
        mode = data.get("mode", "unknown")
        signal = data.get("signal_dbm")
    except Exception:
        mode = "unknown"
        signal = None
    return mode, signal

def set_desired_mode(mode):
    """Write desired mode for trailcam_netmgr.py to pick up."""
    data = {"desired": mode, "timestamp": time.time()}
    try:
        with open(DESIRED_MODE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def mjpeg_generator():
    """Stream the latest JPEG as MJPEG."""
    while True:
        if os.path.exists(LIVE_JPEG_PATH):
            try:
                with open(LIVE_JPEG_PATH, "rb") as f:
                    frame = f.read()
                if frame:
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n\r\n" +
                           frame + b"\r\n")
            except Exception:
                pass
        time.sleep(0.1)  # ~10 fps

@app.route("/")
def index():
    recording, events = get_status()
    net_mode, net_signal = get_net_state()
    return render_template_string(
        HTML_INDEX,
        recording=recording,
        events=events,
        net_mode=net_mode,
        net_signal=net_signal,
    )

@app.route("/stream")
def stream():
    if not os.path.exists(LIVE_JPEG_PATH):
        def blank():
            while True:
                time.sleep(0.5)
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n\r\n")
        return Response(blank(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/files")
def files():
    def safe_list(path):
        if not os.path.isdir(path):
            return []
        return sorted(os.listdir(path), reverse=True)

    videos = safe_list(VIDEO_DIR)
    videos_trk = safe_list(VIDEO_TRACKED_DIR)
    photos = safe_list(PHOTO_DIR)

    recording, events = get_status()
    net_mode, net_signal = get_net_state()

    return render_template_string(
        HTML_FILES,
        photos=photos,
        videos=videos,
        videos_trk=videos_trk,
        recording=recording,
        events=events,
        net_mode=net_mode,
        net_signal=net_signal,
    )

@app.route("/view/<folder>/<path:fname>")
def view_file(folder, fname):
    """Inline preview: clicking the filename opens the media for viewing."""
    folder_map = {
        "photos": PHOTO_DIR,
        "videos": VIDEO_DIR,
        "videos_tracked": VIDEO_TRACKED_DIR,
    }
    base = folder_map.get(folder)
    if base is None:
        abort(404)
    # as_attachment=False so browser tries to play / show it
    return send_from_directory(base, fname, as_attachment=False)

@app.route("/download/<folder>/<path:fname>")
def download(folder, fname):
    """Download: Download button always triggers a save dialog."""
    folder_map = {
        "photos": PHOTO_DIR,
        "videos": VIDEO_DIR,
        "videos_tracked": VIDEO_TRACKED_DIR,
    }
    base = folder_map.get(folder)
    if base is None:
        abort(404)
    return send_from_directory(base, fname, as_attachment=True)

@app.route("/download_all_media")
def download_all_media():
    """
    Create a ZIP containing all media (photos, videos, tracked videos)
    and return it as a download.
    """
    # Temporary ZIP file
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()

    dir_specs = [
        (PHOTO_DIR, "photos"),
        (VIDEO_DIR, "videos"),
        (VIDEO_TRACKED_DIR, "videos_tracked"),
    ]

    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder_path, arc_prefix in dir_specs:
            if not os.path.isdir(folder_path):
                continue
            for name in os.listdir(folder_path):
                full = os.path.join(folder_path, name)
                if os.path.isfile(full):
                    arcname = os.path.join(arc_prefix, name)
                    try:
                        zf.write(full, arcname=arcname)
                    except Exception:
                        # skip problematic file, continue
                        pass

    @after_this_request
    def remove_file(response):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return response

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name="trailcam_all_media.zip",
        mimetype="application/zip",
    )

@app.route("/delete/<folder>/<path:fname>", methods=["POST"])
def delete_file(folder, fname):
    folder_map = {
        "photos": PHOTO_DIR,
        "videos": VIDEO_DIR,
        "videos_tracked": VIDEO_TRACKED_DIR,
    }
    base = folder_map.get(folder)
    if base is None:
        abort(404)

    full_path = os.path.join(base, fname)
    if not os.path.isfile(full_path):
        abort(404)

    try:
        os.remove(full_path)
    except Exception:
        abort(500)
    return redirect(url_for("files"))

@app.route("/delete_all/<target>", methods=["POST"])
def delete_all(target):
    """
    Delete all files in the requested category:
      target = photos | videos | videos_tracked | all
    This is irreversible.
    """
    target_map = {
        "photos": [PHOTO_DIR],
        "videos": [VIDEO_DIR],
        "videos_tracked": [VIDEO_TRACKED_DIR],
        "all": [PHOTO_DIR, VIDEO_DIR, VIDEO_TRACKED_DIR],
    }
    dirs = target_map.get(target)
    if dirs is None:
        abort(404)

    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            full = os.path.join(d, name)
            if os.path.isfile(full):
                try:
                    os.remove(full)
                except Exception:
                    # Ignore individual file errors, keep going
                    pass

    return redirect(url_for("files"))

@app.route("/reset_background", methods=["POST"])
def reset_background():
    # Touch the flag file; main.py will see it and reset background
    try:
        with open(RESET_FLAG_PATH, "w") as f:
            f.write("reset\n")
    except Exception:
        pass
    return redirect(url_for("index"))

@app.route("/set_mode_wifi", methods=["POST"])
def set_mode_wifi():
    set_desired_mode("wifi")
    ref = request.referrer
    if ref:
        return redirect(ref)
    return redirect(url_for("index"))

@app.route("/set_mode_ap", methods=["POST"])
def set_mode_ap():
    set_desired_mode("ap")
    ref = request.referrer
    if ref:
        return redirect(ref)
    return redirect(url_for("index"))

if __name__ == "__main__":
    # Listen on all interfaces, port 8000
    app.run(host="0.0.0.0", port=8000, threaded=True)
