# Trailcam-Raspberry-Pi-5-Topdon-Thermal-Camera-TC001-

Trailcam is a Raspberry Pi–based trail camera / thermal recorder project.

It consists of:

- `main.py` – the recorder / motion logic that:
  - grabs frames from the camera,
  - runs detection / background subtraction,
  - saves photos/videos into a media directory,
  - writes `status.json` for the web UI.
- `webapp.py` – a lightweight Flask web interface that:
  - shows a live MJPEG view using `live.jpg`,
  - lets you browse/download/delete photos and videos,
  - offers a "Download all media as ZIP" button,
  - exposes a "Reset background" button for the recorder.

Networking is set up so the Pi can run as a **Wi-Fi access point** (AP mode), with:
- SSID like `Topdon TrailCam` (configured via `hostapd.conf`)
- Static AP IP `192.168.4.1`
- Web interface at `http://trailcam.local:8000/` or `http://192.168.4.1:8000/` when connected to the AP

Ethernet works as a backup path: if both your PC and Pi are on the same wired LAN, you can still reach:
- `ssh kasper@trailcam.local`
- `http://trailcam.local:8000/`

> **NOTE:** This repo contains configuration *templates* for hostapd/dnsmasq and systemd services. You may need to adjust usernames, paths, and SSIDs for your own Pi.

---

## Features

- MJPEG live view from `live.jpg`
- File browser for:
  - raw videos (`/home/<user>/media/videos`)
  - processed / tracked videos (`/home/<user>/media/videos_tracked`)
  - photos (`/home/<user>/media/photos`)
- Per–file download + delete
- "Delete all" buttons (with warning) for each category and all media
- "Download ALL media as ZIP" button
- Background reset hook via a simple flag file
- Optional: Wi-Fi AP with static IP & DHCP via hostapd + dnsmasq
- systemd units to run the recorder and web server at boot

---

## Directory structure (runtime on the Pi)

By default, the recorder and webapp expect:

```text
/home/<user>/media/
├── photos/
├── videos/
├── videos_tracked/
├── live.jpg         # latest frame for live MJPEG view
└── status.json      # small JSON with {"recording": bool, "events": int}
