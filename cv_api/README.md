# Hazard Lens Browser Camera API

Small Flask bridge for the dashboard's browser webcam. It **reuses** the existing
`cv_engine` YOLOv8-pose / PyTorch pose estimator and fall state machine.

## Run

Use Python 3.10–3.12 from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r cv_api/requirements.txt
cp cv_api/.env.example cv_api/.env
python -m cv_api.app
```

The API starts on `http://127.0.0.1:5000`.

- `GET /api/health` — model/device/test-mode status
- `POST /api/detect` — multipart JPEG field `frame`, optional `zone_id`
- `POST /api/test/fall` — safe UI alert test, available only when `TEST_MODE=true`

The model is `yolov8n-pose.pt` through Ultralytics, which runs on PyTorch.
`DEVICE=auto` chooses CUDA first, then Apple MPS, then CPU.

Fall confirmation is not a one-frame classifier. The existing Hazard Lens state
machine tracks each person through UPRIGHT → FALLING → DOWN and requires the down
pose to persist for `FALL_CONFIRMATION_SECONDS` before emitting a fall.

With `EMERGENCY_MODE=false` (default), confirmed falls are written to the
ignored `backend/data/cv_api_falls.jsonl` file and are **not** forwarded to the
alert backend. Set it true only when the team intentionally wants the existing
FastAPI/Twilio incident flow to receive live events.
