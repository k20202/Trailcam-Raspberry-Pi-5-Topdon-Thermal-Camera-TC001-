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

Clone the repository:

``` bash
git clone https://github.com/k20202/Trailcam-Raspberry-Pi-5-Topdon-Thermal-Camera-TC001.git
cd Trailcam-Raspberry-Pi-5-Topdon-Thermal-Camera-TC001
```

Create a virtual environment (optional):

``` bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

------------------------------------------------------------------------

## Running Manually

Start the recorder:

``` bash
python3 main.py
```

Start the web interface:

``` bash
python3 webapp.py
```

------------------------------------------------------------------------

## Running at Boot (systemd)

Install services:

``` bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trailcam-recorder.service
sudo systemctl enable trailcam-web.service
sudo systemctl start trailcam-recorder.service
sudo systemctl start trailcam-web.service
```

------------------------------------------------------------------------

## Wi‑Fi Access Point Mode

AP mode allows direct phone connection to the Pi:

-   SSID example: `Topdon TrailCam`
-   AP IP: `192.168.4.1`
-   Web UI:
    -   `http://192.168.4.1:8000/`
    -   `http://trailcam.local:8000/`

Requires: - `hostapd` - `dnsmasq` - `avahi-daemon`

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
