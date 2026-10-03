"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, ChevronDown, CircleHelp, MapPin, ShieldCheck } from "lucide-react";
import { MotionConfig } from "framer-motion";
import { acknowledgeIncident, dispatchResponse, fetchIncidents, handleIncomingIncident, triggerAlertSound } from "@/lib/call-help/demo-api";
import { initialZones, type Incident, type Zone } from "@/lib/call-help/mock-data";
import { ActiveIncidentCard, AISafetyInsights, AlertToast, IncidentDrawer, IncidentTimeline, LiveCameraPanel, SafetyStats, TopNav, ZoneStatusPanel } from "./Panels";
import "./dashboard.css";

type Toast = { title: string; message: string; critical?: boolean };
export default function Dashboard() {
  const [incidents, setIncidents] = useState<Incident[]>(fetchIncidents);
  const [zones, setZones] = useState<Zone[]>(() => initialZones.map(zone => ({ ...zone })));
  const [selectedZone, setSelectedZone] = useState("02");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [addedFalls, setAddedFalls] = useState(0);
  const [resetVersion, setResetVersion] = useState(0);
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [cameraTime, setCameraTime] = useState("");
  const sequence = useRef(43);
  const alertTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeIncident = incidents.find(incident => incident.id === activeId && incident.status !== "resolved");
  const incidentActive = Boolean(activeIncident);
  const zone = zones.find(zone => zone.id === selectedZone)!;
  const cameraIncidentActive = incidentActive && zone.name === activeIncident?.zone;
  useEffect(() => { const update = () => setCameraTime(new Date().toLocaleString("sv-SE")); update(); const timer = setInterval(update, 1000); return () => { clearInterval(timer); if (alertTimer.current) clearTimeout(alertTimer.current); }; }, []);
  function notify(value: Toast) { if (alertTimer.current) clearTimeout(alertTimer.current); setToast(value); alertTimer.current = setTimeout(() => setToast(null), 6500); }
  function simulateFall() {
    if (incidentActive) return;
    const incident = handleIncomingIncident({ id: `INC-${String(sequence.current++).padStart(3, "0")}`, timestamp: new Date().toISOString(), zone: "Forklift Corridor 1", eventType: "Worker Down", confidence: 94, severity: "critical", status: "unacknowledged" });
    setIncidents(previous => [incident, ...previous]); setActiveId(incident.id); setSelectedZone("02"); setAddedFalls(previous => previous + 1);
    setZones(previous => previous.map(zone => zone.id === "02" ? { ...zone, status: "critical", incidentsToday: zone.incidentsToday + 1 } : zone));
    triggerAlertSound(); notify({ title: "CRITICAL INCIDENT DETECTED", message: "Worker down in Forklift Corridor 1", critical: true });
  }
  function acknowledge() { if (!activeIncident || activeIncident.status !== "unacknowledged") return; setIncidents(previous => previous.map(incident => incident.id === activeId ? acknowledgeIncident(incident) : incident)); notify({ title: "Incident acknowledged", message: "Response coordination is ready." }); }
  function dispatch() { if (!activeIncident || activeIncident.status === "dispatched") return; setIncidents(previous => previous.map(incident => incident.id === activeId ? dispatchResponse(incident) : incident)); notify({ title: "RESPONSE DISPATCHED", message: "Emergency response team notified." }); }
  function reset() { setResetVersion(previous => previous + 1); setIncidents(fetchIncidents()); setZones(initialZones.map(zone => ({ ...zone }))); setSelectedZone("02"); setActiveId(null); setAddedFalls(0); setDrawerId(null); setToast(null); if (alertTimer.current) clearTimeout(alertTimer.current); }
  const dismissDrawer = useCallback(() => setDrawerId(null), []);
  function resolve(id: string) { setIncidents(previous => previous.map(incident => incident.id === id ? { ...incident, status: "resolved" } : incident)); if (id === activeId) { setActiveId(null); setZones(previous => previous.map(zone => zone.id === "02" ? { ...zone, status: "normal" } : zone)); } notify({ title: "Incident closed", message: "The incident has been marked as resolved." }); }
  return <MotionConfig reducedMotion="user"><div className="call-help min-h-screen relative isolate"><TopNav active={incidentActive} onNotifications={() => notify(incidentActive ? { title: "Active safety alert", message: "Worker down in Forklift Corridor 1", critical: true } : { title: "You’re all caught up", message: "No active incidents. All monitored zones are operating normally." })}/><main className="dashboard"><div className="dashboard-intro"><div><div className="eyebrow"><span/> LIVE OPERATIONS</div><h1>Safety command center<span>.</span></h1><p>Real-time awareness. Faster response. Safer people.</p></div><div className="facility-label"><span className="facility-icon"><MapPin size={19}/></span><div><small>MONITORING FACILITY</small><b>North facility <span>·</span> Detroit, MI</b></div><ChevronDown size={14}/></div></div><div className="operation-strip"><div><ShieldCheck size={15}/><b>{incidentActive ? "Incident response in progress" : "All systems operational"}</b><span className="strip-separator"/><span>4 transit zones monitored</span></div><span><Activity size={14}/> Computer vision connected</span></div><div className="primary-grid"><LiveCameraPanel zone={zone} incidentActive={cameraIncidentActive} simulationDisabled={incidentActive} time={cameraTime} onSimulate={simulateFall} onReset={reset}/><ActiveIncidentCard incident={activeIncident} onAcknowledge={acknowledge} onDispatch={dispatch} onCamera={() => { setSelectedZone("02"); document.getElementById("live-camera")?.scrollIntoView({ behavior: "smooth", block: "center" }); }}/></div><div className="secondary-grid"><ZoneStatusPanel zones={zones} selected={selectedZone} onSelect={zone => setSelectedZone(zone.id)}/><SafetyStats addedFalls={addedFalls}/><IncidentTimeline incidents={incidents} onSelect={incident => setDrawerId(incident.id)}/></div><AISafetyInsights key={resetVersion}/><footer className="dashboard-footer"><span><span className="footer-logo"><Activity size={12}/></span> CALL-HELP <i/> Built for the people on the floor.</span><span><CircleHelp size={12}/> Local demonstration <i/> No external services connected</span></footer></main><IncidentDrawer incident={incidents.find(incident => incident.id === drawerId) || null} onDismiss={dismissDrawer} onResolve={resolve}/><AlertToast toast={toast} onDismiss={() => setToast(null)}/></div></MotionConfig>;
}
