"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, CircleAlert, LoaderCircle, ShieldCheck, TestTube2, TriangleAlert } from "lucide-react";
import { detectFrame, getCvHealth, simulateFall, type CvHealth, type DetectionResult } from "@/lib/call-help/camera";
import type { Zone } from "@/lib/call-help/types";
import "./live-camera.css";

type CameraState = "off" | "starting" | "monitoring" | "person" | "possible" | "fall" | "error";

const labels: Record<CameraState, string> = {
  off: "Camera Off",
  starting: "Camera Starting",
  monitoring: "Monitoring — No hazard detected",
  person: "Person Detected",
  possible: "Possible Fall",
  fall: "FALL DETECTED",
  error: "Camera / detection error",
};

export function LiveCameraPanel({ zone }: { zone: Zone }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const [state, setState] = useState<CameraState>("off");
  const [health, setHealth] = useState<CvHealth | null>(null);
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [message, setMessage] = useState("Start the camera to begin local safety monitoring.");

  const detectionFps = Math.max(1, Math.min(5, Number(process.env.NEXT_PUBLIC_CV_DETECTION_FPS || "3")));
  const externalStream = process.env.NEXT_PUBLIC_CAMERA_STREAM_URL;
  const cameraMode = process.env.NEXT_PUBLIC_CAMERA_MODE || "browser";

  useEffect(() => {
    const controller = new AbortController();
    getCvHealth(controller.signal)
      .then(setHealth)
      .catch(error => setMessage(error instanceof Error ? error.message : "CV backend unavailable"));
    return () => {
      controller.abort();
      stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyResult(next: DetectionResult) {
    setResult(next);
    if (next.fall_detected) {
      setState("fall");
      setMessage(next.simulated ? "Safe test alert — no emergency contact was triggered." : "Confirmed fall detected by the pose model.");
    } else if (next.status === "possible_fall") {
      setState("possible");
      setMessage("Fall-like motion is being confirmed across time.");
    } else if (next.person_detected) {
      setState("person");
      setMessage("Person detected. Monitoring posture and movement.");
    } else {
      setState("monitoring");
      setMessage("No person or safety hazard detected.");
    }
  }

  async function sampleFrame() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2 || inFlightRef.current || state === "off") return;

    const sourceWidth = video.videoWidth || 640;
    const sourceHeight = video.videoHeight || 480;
    const width = Math.min(640, sourceWidth);
    const height = Math.round(width * sourceHeight / sourceWidth);
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d")?.drawImage(video, 0, 0, width, height);

    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.72));
    if (!blob) return;

    inFlightRef.current = true;
    abortRef.current = new AbortController();
    try {
      applyResult(await detectFrame(blob, zone.id, abortRef.current.signal));
    } catch (error) {
      if (abortRef.current.signal.aborted) return;
      setState("error");
      setMessage(error instanceof Error ? error.message : "Detection request failed");
    } finally {
      inFlightRef.current = false;
    }
  }

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setState("error");
      setMessage("This browser does not provide webcam access.");
      return;
    }
    setState("starting");
    setMessage("Requesting camera permission…");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setState("monitoring");
      setMessage("Camera active. Sampling frames for fall detection.");
      timerRef.current = setInterval(() => void sampleFrame(), Math.round(1000 / detectionFps));
    } catch (error) {
      setState("error");
      const name = error instanceof DOMException ? error.name : "";
      setMessage(name === "NotAllowedError"
        ? "Camera permission was denied. Allow camera access in your browser and try again."
        : "Camera could not be started. Check that a webcam is connected and not in use.");
    }
  }

  function stopCamera() {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    abortRef.current?.abort();
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    inFlightRef.current = false;
    setResult(null);
    setState("off");
    setMessage("Camera stopped.");
  }

  async function runSafeFallTest() {
    try {
      applyResult(await simulateFall(zone.id));
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Safe fall simulation failed");
    }
  }

  const stateClass = state === "fall" ? "danger" : state === "possible" ? "warning" : state === "error" ? "error" : "normal";

  return <section className={`panel live-safety-camera ${stateClass}`} id="live-camera">
    <div className="camera-header">
      <div><h2><Camera size={16}/> LIVE SAFETY CAMERA</h2><p>{zone.name}</p></div>
      <span className={`camera-state-pill ${stateClass}`}>{state === "starting" && <LoaderCircle size={12} className="spin"/>}{labels[state]}</span>
    </div>

    <div className="browser-camera-view">
      {cameraMode === "stream" && externalStream ? <>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={externalStream} alt="Hazard Lens CV stream" className="browser-camera-video"/>
      </> : <>
        <video ref={videoRef} muted playsInline className="browser-camera-video"/>
        <canvas ref={canvasRef} hidden/>
      </>}

      {state === "off" && cameraMode !== "stream" && <div className="camera-empty"><CameraOff size={42}/><span>Camera is off</span></div>}

      {result?.people.map(person => {
        const [x1, y1, x2, y2] = person.bbox;
        const width = result.frame.width || 1;
        const height = result.frame.height || 1;
        return <div key={person.track_id} className={`person-box ${person.state}`} style={{
          left: `${x1 / width * 100}%`, top: `${y1 / height * 100}%`,
          width: `${(x2 - x1) / width * 100}%`, height: `${(y2 - y1) / height * 100}%`,
        }}><span>{person.state.toUpperCase()} · {Math.round(person.confidence * 100)}%</span></div>;
      })}

      {state === "fall" && <div className="fall-banner"><TriangleAlert size={22}/><strong>FALL DETECTED</strong></div>}
      {state === "possible" && <div className="possible-banner"><CircleAlert size={18}/> Possible fall detected — confirming…</div>}
    </div>

    <div className="camera-status-row">
      <div><span className={`status-dot ${stateClass}`}/><b>{labels[state]}</b><small>{message}</small></div>
      <div className="camera-metrics">
        <span>{result ? `${Math.round(result.confidence * 100)}% confidence` : "No inference yet"}</span>
        <span>{result ? `${result.inference_ms} ms` : `${detectionFps} FPS target`}</span>
        <span>{health?.device ? health.device.toUpperCase() : "CV offline"}</span>
      </div>
    </div>

    <div className="camera-actions">
      {cameraMode === "browser" && state === "off" && <button className="button" onClick={() => void startCamera()}><Camera size={14}/> Start Camera</button>}
      {cameraMode === "browser" && state !== "off" && state !== "starting" && <button className="button secondary" onClick={stopCamera}><CameraOff size={14}/> Stop Camera</button>}
      {health?.test_mode && <button className="button secondary" onClick={() => void runSafeFallTest()}><TestTube2 size={14}/> Test Fall Alert</button>}
      <span className={`mode-badge ${health?.emergency_mode ? "live" : "test"}`}><ShieldCheck size={12}/>{health?.emergency_mode ? "LIVE ALERT MODE" : "TEST MODE — NO EMERGENCY CONTACT"}</span>
    </div>
  </section>;
}
