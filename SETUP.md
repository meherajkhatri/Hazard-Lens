# Hazard-Lens --- Complete Setup & Run Guide

Hazard-Lens is an industrial safety monitoring system that combines a
camera/computer-vision pipeline, a FastAPI backend, and a Next.js
frontend dashboard.

This guide explains how to set up and run the complete project on
**macOS** and **Windows**.

## Project Architecture

``` text
Camera
  |
  v
CV Engine (YOLOv8 Pose)
  |
  | telemetry
  v
FastAPI Backend
  |
  | REST API / WebSocket
  v
Next.js Frontend Dashboard
```

The repository contains these main components:

``` text
Hazard-Lens/
├── backend/       # FastAPI backend
├── cv_engine/     # Camera + YOLO computer vision engine
├── cv_api/        # Computer vision API components
├── frontend/      # Next.js frontend
├── docs/
└── README.md
```

## Prerequisites

Install the following before starting:

-   Git
-   Python 3
-   Node.js and npm
-   VS Code
-   A working webcam/camera

Verify the installations:

``` bash
git --version
python3 --version
node --version
npm --version
```

On Windows, Python may use `python` instead of `python3`:

``` powershell
python --version
```

## 1. Clone the Repository

If the repository has not already been cloned:

``` bash
git clone https://github.com/meherajkhatri/Hazard-Lens.git
cd Hazard-Lens
```

If it is already cloned, open the project folder in VS Code.

Make sure you are working on `main`:

``` bash
git switch main
git pull origin main
git status
```

The following sections use **three terminals**:

1.  Terminal 1 --- Backend
2.  Terminal 2 --- CV Engine / Camera
3.  Terminal 3 --- Frontend

Keep all three running while using the complete application.

------------------------------------------------------------------------

# macOS Setup

## 2. Terminal 1 --- Start the Backend

From the repository root:

``` bash
cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --reload
```

A successful startup should include:

``` text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

Keep this terminal running.

Backend:

``` text
http://127.0.0.1:8000
```

## 3. Terminal 2 --- Set Up the CV Engine

Open another VS Code terminal.

From the repository root:

``` bash
cd cv_engine

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Return to the repository root:

``` bash
cd ..
```

### Run the Preflight Test

Run the preflight check **from the repository root**:

``` bash
python -m cv_engine.preflight
```

Do not run:

``` bash
python cv_engine/preflight.py
```

or:

``` bash
cd cv_engine
python preflight.py
```

The CV engine uses package imports such as `cv_engine.config`, so
running it as a module from the repository root avoids
`ModuleNotFoundError`.

Expected output:

``` text
Backend: http://localhost:8000
READY: backend reachable, API key accepted, telemetry format matches.
```

### Start the Camera / CV Engine

Still from the repository root:

``` bash
python -m cv_engine.run
```

On the first run, YOLO may download the pose model:

``` text
yolov8n-pose.pt
```

You may also see Matplotlib font-cache messages. These are normally
harmless.

Successful startup should eventually show messages similar to:

``` text
loading yolov8n-pose.pt on cpu
camera camera index 0 connected
to stop: click the video window and press q, or close it
```

Keep Terminal 2 running.

### macOS Camera Permission

If you see:

``` text
OpenCV: not authorized to capture video
```

open:

**System Settings → Privacy & Security → Camera**

Enable camera access for **Visual Studio Code** and/or the terminal
application being used.

Then:

1.  Stop the CV engine with `Ctrl+C`.
2.  Completely quit VS Code.
3.  Reopen VS Code.
4.  Restart the backend.
5.  Restart the CV engine.

Also close applications that may already be using the camera, including
FaceTime, Zoom, Teams, Photo Booth, or browser tabs with camera access.

------------------------------------------------------------------------

## 4. Terminal 3 --- Start the Frontend on macOS

Open a third VS Code terminal.

From the repository root:

``` bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The frontend should display a local address, typically:

``` text
http://localhost:3000
```

Open it in a browser.

------------------------------------------------------------------------

# Windows Setup

The recommended shell is **PowerShell** inside VS Code.

## 5. Terminal 1 --- Start the Backend

From the repository root:

``` powershell
cd backend

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
Copy-Item .env.example .env

uvicorn app.main:app --reload
```

A successful startup should include:

``` text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

Keep Terminal 1 running.

### PowerShell Execution Policy Error

If PowerShell prevents virtual-environment activation, you may see an
error stating that scripts cannot be loaded.

For the current PowerShell session, run:

``` powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate again:

``` powershell
.venv\Scripts\Activate.ps1
```

This changes the execution policy only for the current PowerShell
process.

------------------------------------------------------------------------

## 6. Terminal 2 --- Set Up the CV Engine on Windows

Open another PowerShell terminal.

From the repository root:

``` powershell
cd cv_engine

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
Copy-Item .env.example .env

cd ..
```

### Run the Preflight Test

From the repository root:

``` powershell
python -m cv_engine.preflight
```

Expected output:

``` text
Backend: http://localhost:8000
READY: backend reachable, API key accepted, telemetry format matches.
```

### Start the Camera / CV Engine

``` powershell
python -m cv_engine.run
```

The first run may download `yolov8n-pose.pt`.

Successful startup should eventually show that the camera is connected.

### Windows Camera Permission

If the camera cannot be opened:

1.  Open **Settings**.
2.  Go to **Privacy & security → Camera**.
3.  Enable **Camera access**.
4.  Enable **Let desktop apps access your camera**.
5.  Close programs such as Zoom, Teams, OBS, or browser tabs that may be
    using the camera.
6.  Restart VS Code if necessary.
7.  Run the CV engine again.

------------------------------------------------------------------------

## 7. Terminal 3 --- Start the Frontend on Windows

Open a third PowerShell terminal.

From the repository root:

``` powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the displayed local URL, normally:

``` text
http://localhost:3000
```

------------------------------------------------------------------------

# Normal Startup After Initial Installation

You do **not** need to recreate virtual environments or reinstall
dependencies every time.

## macOS

### Terminal 1 --- Backend

``` bash
cd Hazard-Lens/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Terminal 2 --- Camera / CV Engine

From the `Hazard-Lens` repository root:

``` bash
source cv_engine/.venv/bin/activate
python -m cv_engine.preflight
python -m cv_engine.run
```

### Terminal 3 --- Frontend

``` bash
cd Hazard-Lens/frontend
npm run dev
```

## Windows PowerShell

### Terminal 1 --- Backend

``` powershell
cd Hazard-Lens\backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

### Terminal 2 --- Camera / CV Engine

From the `Hazard-Lens` repository root:

``` powershell
cv_engine\.venv\Scripts\Activate.ps1
python -m cv_engine.preflight
python -m cv_engine.run
```

### Terminal 3 --- Frontend

``` powershell
cd Hazard-Lens\frontend
npm run dev
```

------------------------------------------------------------------------

# Correct Startup Order

Always start the services in this order:

``` text
1. Backend
      ↓
2. CV Engine / Camera
      ↓
3. Frontend
```

The backend should be running before the CV engine performs its
preflight check.

The final running system should look like:

``` text
Terminal 1
FastAPI Backend
http://127.0.0.1:8000
        ↑
        │ telemetry
        │
Terminal 2
Camera → YOLOv8 Pose → CV Engine
        │
        ↓
Terminal 3
Next.js Frontend
http://localhost:3000
```

------------------------------------------------------------------------

# Troubleshooting

## `ModuleNotFoundError: No module named 'cv_engine'`

Incorrect:

``` bash
cd cv_engine
python preflight.py
```

Correct:

``` bash
cd Hazard-Lens
python -m cv_engine.preflight
```

The command must be run from the repository root.

## Backend Is Not Reachable

Make sure Terminal 1 is running:

``` bash
uvicorn app.main:app --reload
```

Then retry:

``` bash
python -m cv_engine.preflight
```

A successful result should contain:

``` text
READY: backend reachable
```

## Camera Connects and Then Disconnects

If you see:

``` text
camera camera index 0 lost; reconnecting every 2s
```

check:

-   Camera permissions are enabled.
-   Another application is not using the camera.
-   The correct camera is connected.
-   VS Code was restarted after changing camera permissions.
-   Camera index `0` corresponds to the intended camera.

## YOLO Model Download

On the first CV-engine run, Ultralytics may download:

``` text
yolov8n-pose.pt
```

Allow the download to complete. Future runs should normally reuse the
downloaded model.

## Matplotlib Font Warnings on macOS

Messages about Apple fonts, `Apple Color Emoji.ttc`, `PingFangUI.ttc`,
or Matplotlib building its font cache generally do not indicate a
Hazard-Lens failure.

If the camera and model continue loading afterward, these messages can
normally be ignored.

## Port Already in Use

Typical ports are:

``` text
Backend:  8000
Frontend: 3000
CV stream/configuration: may use another configured port
```

If a previous instance is still running, stop it with:

``` text
Ctrl+C
```

Then restart the service.

## Frontend Cannot Reach Backend

Confirm that the backend is still running at:

``` text
http://127.0.0.1:8000
```

Check the frontend `.env` configuration and ensure its backend/API URL
matches the backend configuration.

## CV Stream Address

The CV engine may print a stream address such as:

``` text
http://<host>:8001/stream
```

The exact host depends on the project environment and `.env`
configuration. If the frontend is running on another machine or the
camera stream is being shared over a network, ensure the configured host
is reachable from that machine.

Do not automatically replace a network IP with `localhost` when the
frontend and CV engine are intended to run on different devices.

------------------------------------------------------------------------

# Stopping Hazard-Lens

Stop each running service with:

``` text
Ctrl+C
```

If the CV video window is active, the application may also support
clicking the video window and pressing:

``` text
q
```

After stopping a Python service, deactivate its virtual environment if
desired:

``` bash
deactivate
```

------------------------------------------------------------------------

# Environment Files

The project uses `.env` files for local configuration.

macOS:

``` bash
cp .env.example .env
```

Windows PowerShell:

``` powershell
Copy-Item .env.example .env
```

Do not commit secrets, API keys, or private credentials to Git.

External integrations such as Supabase, Twilio, or Gemini may require
additional credentials depending on which project features are enabled.

------------------------------------------------------------------------

# Quick Verification Checklist

Before testing the complete dashboard, confirm:

-   Backend says `Application startup complete`.
-   `python -m cv_engine.preflight` reports `READY`.
-   YOLO successfully loads `yolov8n-pose.pt`.
-   The camera reports that it is connected.
-   The frontend development server starts successfully.
-   The frontend opens in the browser.
-   Backend telemetry/events are reaching the dashboard.
-   The camera/CV stream appears where expected.

Once all checks pass, the frontend, backend, and camera/CV pipeline are
running together.
