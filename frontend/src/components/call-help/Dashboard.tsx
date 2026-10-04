"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, MapPin, ShieldCheck } from "lucide-react";
import { MotionConfig } from "framer-motion";
import { fetchIncidents, request, updateIncident } from "@/lib/call-help/api";
import { configuredCameras } from "@/lib/call-help/cameras";
import { mergeIncident, type Incident, type Zone } from "@/lib/call-help/types";
import { ActiveIncidentCard, AISafetyInsights, AlertToast, IncidentDrawer, IncidentTimeline, LiveCameraPanel, SafetyStats, TopNav, ZoneStatusPanel } from "./Panels";
import "./dashboard.css";

const cameras = configuredCameras();
type Selection = { zoneId: string; cameraId: string | null; incidentId?: string };
type Toast = { title: string; message: string; critical?: boolean };
export default function Dashboard() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [showAllCameras, setShowAllCameras] = useState(false);
  const [disabledCameras, setDisabledCameras] = useState<Set<string>>(new Set());
  const selectedZone = selection?.zoneId || cameras[0]?.zone || process.env.NEXT_PUBLIC_CAMERA_ZONE || "Zone 1";
  const selectedCameraId = showAllCameras ? null : selection ? selection.cameraId : cameras[0]?.id || null;
  const focusIncident = (row: Incident) => setSelection({ zoneId: row.zone_id, cameraId: row.camera_id, incidentId: row.incident_id });
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [connection, setConnection] = useState("Connecting to backend…");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [mode, setMode] = useState("Checking services…");
  const [now, setNow] = useState<Date | null>(null);
  const [sound, setSound] = useState(false);
  const audio = useRef<AudioContext | null>(null);
  const seen = useRef(new Set<string>());
  const revision = useRef(0);
  const today = incidents.filter(row => now && new Date(row.detected_at).toDateString() === now.toDateString());
  const zones: Zone[] = [...new Set([selectedZone, ...cameras.map(camera => camera.zone), ...incidents.map(row => row.zone_id)])].map(id => ({
    id, name: id, incidentsToday: today.filter(row => row.zone_id === id).length,
    status: incidents.some(row => row.zone_id === id && row.status !== "resolved") ? "critical" : "normal",
  }));
  const activeIncident = incidents.find(row => row.incident_id === selection?.incidentId)
    || incidents.find(row => (showAllCameras || row.zone_id === selectedZone) &&
      (!selectedCameraId || row.camera_id === selectedCameraId) && row.status !== "resolved");
  const zone = zones.find(row => row.id === selectedZone) || zones[0];
  useEffect(() => {
    const tick = () => setNow(new Date());
    tick(); const timer = setInterval(tick, 1000);
    return () => { clearInterval(timer); void audio.current?.close(); };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6500);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    let disposed = false;
    let refreshSequence = 0;
    const controller = new AbortController();
    async function refresh() {
      const sequence = ++refreshSequence;
      const startRevision = revision.current;
      try {
        const rows = await fetchIncidents(controller.signal);
        if (disposed || sequence !== refreshSequence) return;
        // A WebSocket update may have arrived while REST was in flight. Retry
        // rather than replacing a newer state with an older snapshot.
        if (startRevision !== revision.current) { void refresh(); return; }
        rows.forEach(row => seen.current.add(row.incident_id));
        setIncidents(rows); setError("");
        const latest = rows.find(row => row.status !== "resolved");
        if (latest) setSelection(current => current || { zoneId: latest.zone_id, cameraId: latest.camera_id, incidentId: latest.incident_id });
      } catch (e) { if (!disposed) setError(e instanceof Error ? e.message : "Unable to load incidents"); }
    }
    async function health() {
      try {
        const data = await request<{ alert_provider: string; coach_mode: string; storage: string }>("health", { signal: controller.signal });
        if (!disposed) setMode(`Storage: ${data.storage} · Alerts: ${data.alert_provider} · Coach: ${data.coach_mode}`);
      } catch { if (!disposed) setMode("Backend unavailable"); }
    }
    void refresh(); void health();
    const events = new EventSource("/api/events");
    events.onmessage = message => {
      const event = JSON.parse(message.data) as { type: string; incident?: Incident };
      if (event.type === "connected") {
        setConnection("Live incident updates connected"); void refresh(); void health(); return;
      }
      const row = event.incident;
      if (!row) return;
      revision.current++;
      setIncidents(previous => mergeIncident(previous, row));
      if (event.type === "incident.created" && !seen.current.has(row.incident_id)) {
        seen.current.add(row.incident_id);
        focusIncident(row);
        setToast({ title: "New incident detected", message: `${row.description} · ${row.zone_id}`, critical: row.severity === "high" });
        const context = audio.current;
        if (context?.state === "running") {
          const oscillator = context.createOscillator(), gain = context.createGain();
          oscillator.connect(gain); gain.connect(context.destination);
          oscillator.frequency.value = 880; gain.gain.value = 0.08;
          oscillator.start(); oscillator.stop(context.currentTime + 0.25);
        }
      }
    };
    events.onerror = () => setConnection("Live updates disconnected · reconnecting; refreshing every 15s");
    const timer = setInterval(() => { void refresh(); void health(); }, 15000);
    return () => { disposed = true; controller.abort(); events.close(); clearInterval(timer); };
  }, []);
  async function changeStatus(id: string, status: "acknowledged" | "resolved") {
    if (pendingRef.current) return;
    pendingRef.current = true; setPending(true);
    try {
      const row = await updateIncident(id, status);
      revision.current++;
      // Live updates and periodic snapshots also reconcile this record.
      setIncidents(previous => mergeIncident(previous, row));
      setToast({ title: `Incident ${status}`, message: "Saved to the incident database." });
    } catch (e) { setToast({ title: "Update failed", message: e instanceof Error ? e.message : "Please retry", critical: true }); }
    finally { pendingRef.current = false; setPending(false); }
  }
  async function toggleSound() {
    if (sound) { await audio.current?.suspend(); setSound(false); return; }
    try { audio.current ??= new AudioContext(); await audio.current.resume(); setSound(true); }
    catch { setToast({ title: "Sound unavailable", message: "This browser could not enable audio alerts." }); }
  }
  const dismissDrawer = useCallback(() => setDrawerId(null), []);
  return <MotionConfig reducedMotion="user"><div className="call-help min-h-screen relative isolate">
    <TopNav connection={connection} onNotifications={() => setToast({ title: "Incident summary", message: `${incidents.filter(row => row.status !== "resolved").length} unresolved incidents in the database.` })}/>
    <main className="dashboard">
      <div className="dashboard-intro"><div><div className="eyebrow"><span/> LIVE OPERATIONS</div><h1>Safety command center<span>.</span></h1><p>Real-time awareness. Faster response. Safer people.</p></div><div className="facility-label"><MapPin size={19}/><b>{zone.name}</b></div></div>
      <div className="operation-strip"><div><ShieldCheck size={15}/><b>{connection}</b></div><button className="button secondary" onClick={toggleSound}>{sound ? "Mute alerts" : "Enable alert sound"}</button></div>
      {cameras.length > 0 && <label className="camera-selector">Camera <select aria-label="Select camera" value={showAllCameras ? "__all__" : selectedCameraId || ""} onChange={event => {
        if (event.target.value === "__all__") {
          setShowAllCameras(true);
          setSelection(null);
          return;
        }
        setShowAllCameras(false);
        const camera = cameras.find(row => row.id === event.target.value);
        if (camera) setSelection({ zoneId: camera.zone, cameraId: camera.id });
      }}>
        <option value="__all__">All cameras ({cameras.length})</option>
        {!cameras.some(camera => camera.id === selectedCameraId) && <option value={selectedCameraId || ""}>{selectedCameraId || "No mapped camera"}</option>}
        {cameras.map(camera => <option key={camera.id} value={camera.id}>{camera.id} · {camera.zone}</option>)}
      </select></label>}
      {error && <p role="alert" className="integration-error">{error} · Displayed records may be stale.</p>}
      <div className={`primary-grid ${showAllCameras ? "all-cameras-mode" : ""}`}>
        <div className="camera-wall" aria-label={showAllCameras ? "All camera feeds" : "Selected camera feed"}>
          {showAllCameras
            ? cameras.map(camera => <LiveCameraPanel key={camera.id} zone={{ id: camera.zone, name: camera.zone, status: "normal", incidentsToday: 0 }} cameraId={camera.id} enabled={!disabledCameras.has(camera.id)} onToggle={() => setDisabledCameras(current => { const next = new Set(current); if (next.has(camera.id)) next.delete(camera.id); else next.add(camera.id); return next; })} incident={incidents.find(row => row.camera_id === camera.id && row.status !== "resolved")} />)
            : <LiveCameraPanel key={selectedCameraId || "no-camera"} zone={zone} cameraId={selectedCameraId} incident={activeIncident} enabled={!selectedCameraId || !disabledCameras.has(selectedCameraId)} onToggle={selectedCameraId ? () => setDisabledCameras(current => { const next = new Set(current); if (next.has(selectedCameraId)) next.delete(selectedCameraId); else next.add(selectedCameraId); return next; }) : undefined}/>}
        </div>
        <ActiveIncidentCard incident={activeIncident} pending={pending} onAcknowledge={() => activeIncident && void changeStatus(activeIncident.incident_id, "acknowledged")} onCamera={() => { if (activeIncident) { setShowAllCameras(false); focusIncident(activeIncident); } document.getElementById("live-camera")?.scrollIntoView({ behavior: "smooth" }); }}/>
      </div>
      <div className="secondary-grid"><ZoneStatusPanel zones={zones} selected={selectedZone} onSelect={row => { const incident = incidents.find(item => item.zone_id === row.id && item.status !== "resolved"); if (incident) focusIncident(incident); else setSelection({ zoneId: row.id, cameraId: cameras.find(camera => camera.zone === row.id)?.id || null }); }}/><SafetyStats incidents={today}/><IncidentTimeline incidents={incidents} onSelect={row => { setDrawerId(row.incident_id); focusIncident(row); }}/></div>
      <AISafetyInsights zone={selectedZone}/>
      <footer className="dashboard-footer"><span><Activity size={12}/> HAZARD LENS</span><span>{mode}</span></footer>
    </main>
    <IncidentDrawer incident={incidents.find(row => row.incident_id === drawerId) || null} pending={pending} onDismiss={dismissDrawer} onResolve={id => void changeStatus(id, "resolved")}/>
    <AlertToast toast={toast} onDismiss={() => setToast(null)}/>
  </div></MotionConfig>;
}
