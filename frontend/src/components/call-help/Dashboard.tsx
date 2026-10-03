"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, ChevronDown, CircleHelp, MapPin, ShieldCheck } from "lucide-react";
import { MotionConfig } from "framer-motion";
import { connectIncidentSocket, getHealth, getIncidents, sendDemoFall, setIncidentStatus } from "@/lib/call-help/api";
import type { Incident, Zone } from "@/lib/call-help/types";
import { ActiveIncidentCard, AISafetyInsights, AlertToast, IncidentDrawer, IncidentTimeline, LiveCameraPanel, SafetyStats, TopNav, ZoneStatusPanel } from "./Panels";
import "./dashboard.css";

type Toast = { title: string; message: string; critical?: boolean };

export default function Dashboard() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedZone, setSelectedZone] = useState("");
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [cameraTime, setCameraTime] = useState("");
  const [backendOnline, setBackendOnline] = useState(false);
  const [realtimeOnline, setRealtimeOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const alertTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const upsertIncident = useCallback((incoming: Incident) => {
    setIncidents(previous => {
      const next = previous.filter(item => item.id !== incoming.id);
      return [incoming, ...next].sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp));
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const updateClock = () => setCameraTime(new Date().toLocaleString("sv-SE"));
    updateClock();
    const clock = setInterval(updateClock, 1000);

    Promise.all([getHealth(), getIncidents()])
      .then(([health, rows]) => {
        if (cancelled) return;
        setBackendOnline(health.status === "ok");
        setIncidents(rows.sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp)));
        setSelectedZone(rows[0]?.zone || "");
      })
      .catch(() => {
        if (!cancelled) setBackendOnline(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    const disconnect = connectIncidentSocket(
      incident => {
        upsertIncident(incident);
        setBackendOnline(true);
        setSelectedZone(current => current || incident.zone);
        if (incident.status !== "resolved") {
          notify({ title: "LIVE INCIDENT UPDATE", message: `${incident.eventType} · ${incident.zone}`, critical: incident.severity === "critical" });
        }
      },
      setRealtimeOnline,
    );

    return () => {
      cancelled = true;
      clearInterval(clock);
      disconnect();
      if (alertTimer.current) clearTimeout(alertTimer.current);
    };
  }, [upsertIncident]);

  function notify(value: Toast) {
    if (alertTimer.current) clearTimeout(alertTimer.current);
    setToast(value);
    alertTimer.current = setTimeout(() => setToast(null), 6500);
  }

  const activeIncident = useMemo(
    () => incidents.find(incident => incident.status !== "resolved"),
    [incidents],
  );

  const zones = useMemo<Zone[]>(() => {
    const today = new Date().toDateString();
    const names = Array.from(new Set(incidents.map(item => item.zone)));
    return names.map((name, index) => {
      const rows = incidents.filter(item => item.zone === name);
      const unresolved = rows.find(item => item.status !== "resolved");
      return {
        id: name,
        name,
        status: unresolved ? (unresolved.severity === "critical" ? "critical" : "warning") : "normal",
        incidentsToday: rows.filter(item => new Date(item.timestamp).toDateString() === today).length,
      };
    }).sort((a, b) => a.name.localeCompare(b.name));
  }, [incidents]);

  const selected = zones.find(zone => zone.id === selectedZone) || zones[0] || {
    id: "none",
    name: "No recorded zone",
    status: "normal" as const,
    incidentsToday: 0,
  };

  async function simulateFall() {
    if (!backendOnline || actionBusy) return;
    setActionBusy(true);
    try {
      await sendDemoFall(selected.id === "none" ? "Forklift Corridor 1" : selected.name);
      notify({ title: "DEMO TELEMETRY SENT", message: "Fall telemetry was sent through the real backend.", critical: true });
    } catch (error) {
      notify({ title: "Telemetry failed", message: error instanceof Error ? error.message : "Backend request failed." });
    } finally {
      setActionBusy(false);
    }
  }

  async function acknowledge() {
    if (!activeIncident || actionBusy) return;
    setActionBusy(true);
    try {
      upsertIncident(await setIncidentStatus(activeIncident.id, "acknowledged"));
      notify({ title: "Incident acknowledged", message: "Backend status updated successfully." });
    } catch (error) {
      notify({ title: "Acknowledge failed", message: error instanceof Error ? error.message : "Backend request failed." });
    } finally {
      setActionBusy(false);
    }
  }

  async function resolve(id: string) {
    if (actionBusy) return;
    setActionBusy(true);
    try {
      upsertIncident(await setIncidentStatus(id, "resolved"));
      notify({ title: "Incident resolved", message: "Backend status updated successfully." });
    } catch (error) {
      notify({ title: "Resolve failed", message: error instanceof Error ? error.message : "Backend request failed." });
    } finally {
      setActionBusy(false);
    }
  }

  const dismissDrawer = useCallback(() => setDrawerId(null), []);

  return <MotionConfig reducedMotion="user">
    <div className="call-help min-h-screen relative isolate">
      <TopNav active={Boolean(activeIncident)} backendOnline={backendOnline} realtimeOnline={realtimeOnline} onNotifications={() => notify(activeIncident ? { title: "Active safety alert", message: `${activeIncident.eventType} · ${activeIncident.zone}`, critical: true } : { title: "No active incident", message: "The backend currently reports no unresolved incidents." })}/>
      <main className="dashboard">
        <div className="dashboard-intro">
          <div><div className="eyebrow"><span/> LIVE OPERATIONS</div><h1>Safety command center<span>.</span></h1><p>Backend-connected incident monitoring and response.</p></div>
          <div className="facility-label"><span className="facility-icon"><MapPin size={19}/></span><div><small>SELECTED ZONE</small><b>{selected.name} <span>·</span> Live data</b></div><ChevronDown size={14}/></div>
        </div>
        <div className="operation-strip"><div><ShieldCheck size={15}/><b>{loading ? "Connecting to safety backend…" : activeIncident ? "Incident response in progress" : "No unresolved incidents"}</b><span className="strip-separator"/><span>{zones.length} recorded zones</span></div><span><Activity size={14}/> {realtimeOnline ? "Realtime incident channel connected" : "Realtime channel disconnected"}</span></div>
        <div className="primary-grid">
          <LiveCameraPanel zone={selected} incidentActive={Boolean(activeIncident && activeIncident.zone === selected.name)} simulationDisabled={!backendOnline || actionBusy} time={cameraTime} onSimulate={simulateFall} backendOnline={backendOnline} realtimeOnline={realtimeOnline}/>
          <ActiveIncidentCard incident={activeIncident} busy={actionBusy} onAcknowledge={acknowledge} onCamera={() => document.getElementById("live-camera")?.scrollIntoView({ behavior: "smooth", block: "center" })}/>
        </div>
        <div className="secondary-grid">
          <ZoneStatusPanel zones={zones} selected={selected.id} onSelect={zone => setSelectedZone(zone.id)}/>
          <SafetyStats incidents={incidents}/>
          <IncidentTimeline incidents={incidents} onSelect={incident => setDrawerId(incident.id)}/>
        </div>
        <AISafetyInsights zoneId={selected.id === "none" ? undefined : selected.name}/>
        <footer className="dashboard-footer"><span><span className="footer-logo"><Activity size={12}/></span> CALL-HELP <i/> Built for the people on the floor.</span><span><CircleHelp size={12}/> REST + WebSocket integration <i/> {backendOnline ? "Backend online" : "Backend offline"}</span></footer>
      </main>
      <IncidentDrawer incident={incidents.find(incident => incident.id === drawerId) || null} onDismiss={dismissDrawer} onResolve={resolve}/>
      <AlertToast toast={toast} onDismiss={() => setToast(null)}/>
    </div>
  </MotionConfig>;
}
