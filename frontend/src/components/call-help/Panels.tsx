"use client";
import { useEffect, useRef, useState } from "react";
import { Activity, ArrowRight, Bell, Check, ChevronRight, CircleCheck, Clock3, Expand, LoaderCircle, MapPin, ScanLine, Send, ShieldCheck, Siren, Sparkles, TriangleAlert, Video, X } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { askCoach } from "@/lib/call-help/api";
import { imageUrl, resolveCameraHealth, resolveCameraStream } from "@/lib/call-help/cameras";
import { eventLabel, type CoachAnswer, type Incident, type Zone } from "@/lib/call-help/types";

const formatTime = (timestamp: string) => new Date(timestamp).toLocaleString();
export function StatusBadge({ status, children }: { status: string; children?: React.ReactNode }) { return <span className={`status-badge ${status}`}><i/>{children || status}</span>; }
export function TopNav({ connection, onNotifications }: { connection: string; onNotifications: () => void }) {
  return <header className="top-nav"><div className="brand"><div className="brand-icon"><Activity size={24}/></div><div><div className="brand-name">HAZARD<span> LENS</span></div><div className="brand-tagline">Industrial Transit Safety</div></div></div><div className="nav-right"><span className="small-label">{connection}</span><button className="icon-button" aria-label="View notifications" onClick={onNotifications}><Bell size={19}/></button></div></header>;
}
export function LiveCameraPanel({ zone, cameraId, incident }: { zone: Zone; cameraId: string | null; incident?: Incident }) {
  const [expanded, setExpanded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [cvStatus, setCvStatus] = useState<"checking" | "connected" | "offline">("checking");
  const [cvPeople, setCvPeople] = useState<number | null>(null);
  const stream = resolveCameraStream(cameraId, process.env.NEXT_PUBLIC_CAMERA_STREAM_URL);
  const healthUrl = resolveCameraHealth(stream);
  const snapshot = incident?.camera_id === cameraId ? imageUrl(incident.metadata.snapshot_url) : undefined;
  const [streamFailed, setStreamFailed] = useState(false);
  const source = (!streamFailed && stream) || snapshot;
  const showingSnapshot = !!source && (streamFailed || !stream);
  useEffect(() => {
    if (!expanded) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    document.addEventListener("keydown", key); return () => document.removeEventListener("keydown", key);
  }, [expanded]);
  useEffect(() => {
    let disposed = false;
    const check = async () => {
      try {
        const response = await fetch(healthUrl, { cache: "no-store", signal: AbortSignal.timeout(2500) });
        if (!response.ok) throw new Error("CV engine health failed");
        const data = await response.json() as { people_detected?: number };
        if (!disposed) {
          setCvStatus("connected");
          setCvPeople(typeof data.people_detected === "number" ? data.people_detected : null);
        }
      } catch {
        if (!disposed) {
          setCvStatus("offline");
          setCvPeople(null);
        }
      }
    };
    void check();
    const timer = setInterval(() => void check(), 3000);
    return () => { disposed = true; clearInterval(timer); };
  }, [healthUrl]);
  return <section className={`panel camera-panel ${expanded ? "camera-expanded" : ""}`} id="live-camera">
    <div className="panel-heading"><div><h2><Video size={15}/> CAMERA MONITORING</h2><p><MapPin size={12}/>{zone.name}{cameraId ? ` · ${cameraId}` : ""}</p></div><button className="icon-button" aria-label={expanded ? "Exit expanded camera" : "Expand camera"} onClick={() => setExpanded(!expanded)}>{expanded ? <X size={17}/> : <Expand size={16}/>}</button></div>
    <div className="camera-view">
      {source && !failed ? <>
        {/* MJPEG is a continuous response and must use a native image element. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img key={`${cameraId || "camera"}-${source}-${attempt}`} src={source} alt={`${showingSnapshot ? "Incident snapshot" : "Annotated CV feed"} for ${cameraId || zone.name}`} className="live-stream" onLoad={() => setLoaded(true)} onError={() => { if (!showingSnapshot && snapshot) setStreamFailed(true); else setFailed(true); setLoaded(false); }}/>
        <span className="scene-label">{loaded ? (showingSnapshot ? "Incident snapshot · not live" : "Live CV camera stream") : "Connecting to camera…"}</span>
      </> : <div className="camera-placeholder"><Video size={36}/><p>{failed ? "Camera feed unavailable" : "No camera feed configured for this incident"}</p>{failed && <button className="button secondary" onClick={() => { setStreamFailed(false); setFailed(false); setLoaded(false); setAttempt(n => n + 1); }}>Reconnect camera</button>}</div>}
    </div><div className="camera-controls"><div className="vision-status"><ScanLine size={15}/><span>{showingSnapshot ? "Showing the saved incident frame" : cvStatus === "connected" ? `CV engine connected${cvPeople !== null ? ` · ${cvPeople} people detected` : ""}` : cvStatus === "offline" ? "CV engine offline — start cv_engine.run" : "Checking CV engine…"}</span>{streamFailed && snapshot && <button className="button secondary" onClick={() => { setStreamFailed(false); setFailed(false); setLoaded(false); setAttempt(n => n + 1); }}>Retry live camera</button>}</div></div>
  </section>;
}
export function ActiveIncidentCard({ incident, pending, onAcknowledge, onCamera }: { incident?: Incident; pending: boolean; onAcknowledge: () => void; onCamera: () => void }) {
  return <section className={`panel active-panel ${incident ? "active-critical" : ""}`}><div className="panel-heading"><h2><Siren size={15}/> INCIDENT RESPONSE</h2></div>{!incident ? <div className="all-clear"><ShieldCheck size={39}/><h3>No unresolved incident loaded</h3><p>Connection status is shown above.</p></div> : <div className="incident-content"><div className="incident-title"><div><StatusBadge status={incident.severity === "high" ? "critical" : "warning"}>{incident.status.toUpperCase()}</StatusBadge><h3>{eventLabel(incident.event_type)}</h3></div><TriangleAlert size={30}/></div><div className="incident-meta"><div><span>Location</span><b>{incident.zone_id}</b></div><div><span>Detected</span><b>{formatTime(incident.detected_at)}</b></div><div><span>Model confidence</span><b>{Math.round(incident.pose_confidence * 100)}%</b></div><div><span>Severity</span><b>{incident.severity}</b></div><div><span>Alert status</span><b>{incident.alert_status.replaceAll("_", " ")}</b></div></div><p className="drawer-note">Alert status reports the configured provider submission result.</p><div className="incident-actions"><button className="button secondary" onClick={onAcknowledge} disabled={pending || incident.status !== "active"}><Check size={14}/> {pending ? "Saving…" : "Acknowledge"}</button></div><button className="view-camera" onClick={onCamera}><Video size={14}/> View Camera <ArrowRight size={13}/></button></div>}</section>;
}
export function ZoneStatusPanel({ zones, selected, onSelect }: { zones: Zone[]; selected: string; onSelect: (zone: Zone) => void }) {
  return <section className="panel zones-panel"><div className="panel-heading"><h2><MapPin size={15}/> TRANSIT ZONES</h2></div><div className="zone-list">{zones.map(zone => <button className={`zone-row ${selected === zone.id ? "selected" : ""} ${zone.status}`} key={zone.id} onClick={() => onSelect(zone)}><span className="zone-icon"><ScanLine size={17}/></span><span className="zone-info"><b>{zone.name}</b><span>{zone.status === "critical" ? "Unresolved incidents" : "No unresolved incidents"}<em>·</em>{zone.incidentsToday} today</span></span><ChevronRight size={15}/></button>)}</div><div className="panel-footnote">Counts use recorded incidents; camera availability is separate.</div></section>;
}
export function SafetyStats({ incidents }: { incidents: Incident[] }) {
  const data = Array.from({ length: 24 }, (_, hour) => ({ hour: `${hour}:00`, incidents: incidents.filter(row => new Date(row.detected_at).getHours() === hour).length }));
  return <section className="panel stats-panel"><div className="panel-heading"><h2><Activity size={15}/> TODAY’S RECORDED INCIDENTS</h2></div><div className="stats-grid">{[
    ["Incidents", incidents.length], ["Possible falls", incidents.filter(row => row.event_type === "fall").length], ["Unresolved", incidents.filter(row => row.status !== "resolved").length], ["Resolved", incidents.filter(row => row.status === "resolved").length],
  ].map(([label, value]) => <div className="stat" key={label}><span className="stat-value">{value}</span><span className="stat-label">{label}</span></div>)}</div><div className="chart-title">Incidents by hour · local time</div><div className="hour-chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}><AreaChart data={data}><CartesianGrid vertical={false} stroke="#263032"/><XAxis dataKey="hour" minTickGap={30} tick={{ fill: "#a1b1b4", fontSize: 10 }}/><YAxis allowDecimals={false} width={25}/><Tooltip contentStyle={{ background: "#192225", color: "#edf1ef" }}/><Area dataKey="incidents" stroke="#9bbeb2" fill="#3c5546" isAnimationActive={false}/></AreaChart></ResponsiveContainer></div></section>;
}
export function IncidentTimeline({ incidents, onSelect }: { incidents: Incident[]; onSelect: (incident: Incident) => void }) {
  return <section className="panel timeline-panel"><div className="panel-heading"><h2><Clock3 size={15}/> RECENT INCIDENTS</h2><span className="small-label">{incidents.length} RECORDS</span></div><div className="timeline-list">{!incidents.length && <p className="panel-footnote">No incident records loaded.</p>}{incidents.map(incident => <button key={incident.incident_id} className="timeline-row" onClick={() => onSelect(incident)}><span className={`timeline-node ${incident.severity === "high" ? "critical" : "warning"}`}><i/></span><span className="timeline-body"><span className="timeline-top"><b>{eventLabel(incident.event_type)}</b><time>{formatTime(incident.detected_at)}</time></span><span className="timeline-location">{incident.zone_id}</span><span className="timeline-status">{incident.status} · Alert: {incident.alert_status.replaceAll("_", " ")}</span></span><ChevronRight size={13}/></button>)}</div></section>;
}
export function AISafetyInsights({ zone }: { zone: string }) {
  const [question, setQuestion] = useState("Summarize risk trends and suggest inspections based on recorded incidents.");
  const [allZones, setAllZones] = useState(false);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<(CoachAnswer & { scope: string; question: string }) | null>(null);
  const [error, setError] = useState("");
  async function analyze(e: React.FormEvent) {
    e.preventDefault(); if (loading || !question.trim()) return;
    setLoading(true); setError("");
    try { const result = await askCoach(question.trim(), allZones ? undefined : zone); setAnalysis({ ...result, scope: allZones ? "All zones" : zone, question }); }
    catch (e) { setError(e instanceof Error ? e.message : "Coach unavailable"); }
    finally { setLoading(false); }
  }
  return <section className="panel ai-panel"><div className="ai-header"><div className="ai-heading"><span className="ai-icon"><Sparkles size={21}/></span><div><h2>AI SAFETY COACH</h2><p>Ask about recorded incidents. Each question retrieves fresh context.</p></div></div></div>
    <form className="coach-form" onSubmit={analyze}><label htmlFor="coach-question">Question</label><textarea id="coach-question" value={question} onChange={e => setQuestion(e.target.value)} maxLength={2000} required rows={3}/><div><label><input type="checkbox" checked={allZones} onChange={e => setAllZones(e.target.checked)}/> All zones</label><span>Scope: {allZones ? "All zones" : zone}</span><button className="button analyze-button" disabled={loading || !question.trim()}>{loading ? <LoaderCircle size={15} className="spin"/> : <Send size={15}/>} {loading ? "Retrieving incidents…" : "Ask Safety Coach"}</button></div></form>
    <div aria-live="polite">{error && <p role="alert" className="integration-error">{error}</p>}{analysis && <div className="coach-answer"><span className="analysis-eyebrow">{"Ollama · Local AI"} · {analysis.scope} · {analysis.context_count} records{analysis.truncated ? " · limited to 50 most recent" : ""}</span><h3>{analysis.question}</h3><p>{analysis.answer}</p>{analysis.incident_ids.length > 0 && <details><summary>Source incident IDs</summary><ul>{analysis.incident_ids.map(id => <li key={id}>{id}</li>)}</ul></details>}</div>}</div><div className="ai-disclaimer"><ShieldCheck size={12}/> Observations come from recorded events. Suggested inspections do not establish a cause.</div></section>;
}
export function IncidentDrawer({ incident, pending, onDismiss, onResolve }: { incident: Incident | null; pending: boolean; onDismiss: () => void; onResolve: (id: string) => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const incidentId = incident?.incident_id;
  useEffect(() => {
    if (!incidentId) return;
    const previous = document.activeElement as HTMLElement; closeRef.current?.focus();
    const old = document.body.style.overflow; document.body.style.overflow = "hidden";
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
      if (e.key === "Tab") {
        const items = document.querySelectorAll<HTMLButtonElement>(".incident-drawer button:not(:disabled)");
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", key);
    return () => { document.body.style.overflow = old; document.removeEventListener("keydown", key); previous?.focus(); };
  }, [incidentId, onDismiss]);
  if (!incident) return null;
  return <div className="drawer-layer"><button aria-label="Dismiss incident details" className="drawer-backdrop" onClick={onDismiss}/><aside className="incident-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><div className="drawer-header"><h2 id="drawer-title">Incident details</h2><button ref={closeRef} className="icon-button" aria-label="Close drawer" onClick={onDismiss}><X size={20}/></button></div><h3>{eventLabel(incident.event_type)}</h3><div className="drawer-details">{[["Incident ID", incident.incident_id], ["Camera", incident.camera_id], ["Zone", incident.zone_id], ["Detected", formatTime(incident.detected_at)], ["Confidence", `${Math.round(incident.pose_confidence * 100)}%`], ["Status", incident.status], ["Alert", incident.alert_status]].map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}</div><h4>Recorded detection metadata</h4><div className="drawer-details">{Object.entries(incident.metadata).map(([key, value]) => <div key={key}><span>{key}</span><b>{String(value)}</b></div>)}</div><p className="drawer-note">{incident.description}</p><button className="button resolve-button" disabled={pending || incident.status === "resolved"} onClick={() => onResolve(incident.incident_id)}><CircleCheck size={16}/>{pending ? "Saving…" : incident.status === "resolved" ? "Incident closed" : "Close incident"}</button></aside></div>;
}
export function AlertToast({ toast, onDismiss }: { toast: { title: string; message: string; critical?: boolean } | null; onDismiss: () => void }) {
  return toast && <div role="alert" className={`alert-toast ${toast.critical ? "critical" : ""}`}><span className="toast-icon">{toast.critical ? <TriangleAlert size={21}/> : <CircleCheck size={21}/>}</span><div><b>{toast.title}</b><p>{toast.message}</p></div><button className="icon-button" aria-label="Dismiss notification" onClick={onDismiss}><X size={16}/></button></div>;
}
