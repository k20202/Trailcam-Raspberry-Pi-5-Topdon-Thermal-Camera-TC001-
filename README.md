# Trailcam -- Raspberry Pi 5 + Topdon TC001 Thermal Camera

This project is a **Raspberry Pi 5--based thermal trail camera system**
built around the **Topdon TC001** USB thermal camera. It provides:

-   Real‑time MJPEG **live streaming**
-   **Automatic thermal motion detection**
-   **Tracked and raw video recording**
-   **Snapshot photos**
-   **Full web‑based control panel**
-   **ARMED / DISARMED recording toggle**
-   **Background auto‑reset when idle**
-   **Phone‑based time synchronisation**
-   **ZIP export + file browser**
-   **Optional Wi‑Fi access‑point mode**
-   **DS3231 RTC hardware support**

------------------------------------------------------------------------

## Core Programs

-   **`main.py`**
    -   Handles:
        -   Thermal + visual decoding
        -   Hot‑object detection
        -   Motion tracking
        -   Video + tracked‑video recording
        -   Periodic photo capture
        -   Background subtraction
        -   Status file generation
        -   **ARMED / DISARMED logic**
        -   **Auto background reset every 60s while idle**
-   **`webapp.py`**
    -   Lightweight Flask server providing:
        -   Live MJPEG stream from `live.jpg`
        -   Media browser + download
        -   Bulk ZIP export
        -   Per‑file delete + delete all
        -   Manual background reset
        -   **ARMED / DISARMED toggle button**
        -   **One‑tap phone time synchronisation**
        -   Recorder status display

------------------------------------------------------------------------

## Major New Features (2025 Update)

✅ **ARMED / DISARMED Recording Toggle** - Recording only occurs while
ARMED. - DISARMED state disables **all video + photo saving**. - Live
stream continues even when disarmed. - Toggle controlled from the web
UI. - Green button = ARMED\
- Red button = DISARMED

✅ **Automatic Background Reset While Idle** - If **no objects are
detected for 60 seconds**, the thermal background is automatically
refreshed. - Prevents: - Cloud movement false positives - Gradual
thermal drift accumulation - Reset only happens when **nothing is being
tracked**.

✅ **Phone‑Based Time Synchronisation** - When connected to the Pi -
Press **"Sync Time From This Device"** - Pi system clock is instantly
updated from your phone - DS3231 RTC can then be written automatically

✅ **DS3231 RTC Hardware Support** - Allows correct time even without
internet - Recommended for permanent deployment

------------------------------------------------------------------------

## Web Interface Preview

### Live View
![Live View](images/webui_live.png)

### File Browser
![File Browser](images/webui_files.png)

------------------------------------------------------------------------

## Runtime Directory Structure

    /home/kasper/media/
    ├── photos/
    ├── videos/
    ├── videos_tracked/
    ├── live.jpg
    └── status.json

-   `live.jpg` = latest MJPEG frame
-   `status.json` = `{ recording: bool, events: int }`

------------------------------------------------------------------------

## Web Interface

The web interface is hosted at:

    http://trailcam.local:8000/
    http://192.168.4.1:8000/

Features: - Live MJPEG view - Browse and delete all media - Download
individual files - Download everything as ZIP - Manual background
reset - **ARMED / DISARMED toggle** - **Phone time synchronisation
button**

------------------------------------------------------------------------

## Installation

Clone the repository to your Pi:

```bash
cd ~
git clone https://github.com/<your-username>/trailcam.git
cd trailcam
```

Create and activate a virtual environment (optional but recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Make sure your camera and other dependencies are correctly set up  
(Topdon TS004 / thermal camera, OpenCV, etc.) as required by `main.py`.


------------------------------------------------------------------------

## Running manually

### Web UI

```bash
cd ~/trailcam
python3 webapp.py
```

The app listens on **0.0.0.0:8000**, so you can visit:

- http://trailcam.local:8000/ (if mDNS is set up and your client supports `.local`)
- http://192.168.4.1:8000/ when connected to the Pi’s AP
* `http://<ethernet-ip>:8000/` if using Ethernet


### Recorder

In another terminal:

```bash
cd ~/trailcam
python3 main.py
```

------------------------------------------------------------------------

## Running with systemd (recommended)

This repo includes example systemd service files in `systemd/`:

- **wlan0-ap-ip.service** – sets `192.168.4.1/24` on wlan0 at boot  
- **trailcam-recorder.service** – runs `main.py` at boot  
- **trailcam-web.service** – runs `webapp.py` at boot  

To install them:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

sudo systemctl enable wlan0-ap-ip.service
sudo systemctl enable trailcam-recorder.service
sudo systemctl enable trailcam-web.service

sudo systemctl start wlan0-ap-ip.service
sudo systemctl start trailcam-recorder.service
sudo systemctl start trailcam-web.service
```

**Make sure you edit the `ExecStart=` paths inside each service**  
to match where you cloned the repo and the user you run as.

------------------------------------------------------------------------

## Wi-Fi AP configuration

Example configuration templates are in `config/`:

- `hostapd.conf.example`  
- `dnsmasq-trailcam.conf.example`

---

### On the Pi

#### Install required packages:

```bash
sudo apt update
sudo apt install hostapd dnsmasq avahi-daemon -y
```

#### Copy and edit configs:

```bash
sudo cp config/hostapd.conf.example /etc/hostapd/hostapd.conf
sudo cp config/dnsmasq-trailcam.conf.example /etc/dnsmasq.d/trailcam.conf

sudo nano /etc/hostapd/hostapd.conf
sudo nano /etc/dnsmasq.d/trailcam.conf
```

#### Enable hostapd and dnsmasq:

```bash
sudo systemctl enable hostapd dnsmasq
sudo systemctl restart hostapd dnsmasq
```

#### Enable mDNS (for `trailcam.local`):

```bash
sudo systemctl enable --now avahi-daemon
```

------------------------------------------------------------------------

## 3D Printed Parts

The 3D parts used for the camera mount are available here:

- [STL file](3d_models/Trailcam_3D.stl)
- [STEP file](3d_models/Trailcam_3D.step)
- [Fusion 360 file (F3D)](3d_models/Trailcam_3D.f3d)

------------------------------------------------------------------------

## Hardware Used

-   Raspberry Pi 5
-   Topdon TC001 USB Thermal Camera
-   DS3231 RTC Module
-   3D printed enclosure and camera mount

------------------------------------------------------------------------

## Safety & Legal Notes

-   Always respect local wildlife and privacy laws
-   Do not surveil private property without consent
-   Thermal cameras can detect humans through foliage
-   Use responsibly

------------------------------------------------------------------------

## Author

Kasper Starzec\
Biomedical Engineering & Embedded Vision Systems\
Topdon Master Contributor
