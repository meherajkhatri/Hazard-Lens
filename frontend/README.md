# Call-Help

An offline-capable industrial transit safety frontend. The standalone public dashboard runs at `/`.

## Run

```sh
npm install
npm run dev
```

Open http://localhost:3000. No database, authentication, API keys, or external connection is needed for Call-Help.

## Judging demo

1. Click **Simulate Fall**. Camera detection, active incident, corridor status, timeline, statistics, and notification update together.
2. Click **Acknowledge** to record acknowledgment, or dispatch directly.
3. Click **Dispatch Response** to record a mock dispatch and show a confirmation.
4. Click **Analyze Safety Pattern**. Local sample analysis appears after one second.
5. Click any timeline entry for incident details. **Close Incident** resolves the record and clears the active zone alert when appropriate.
6. Click **Reset Demo** to restore all initial data and clear AI results. Simulation can be repeated.

Zone rows select their simulated camera feed. The camera supports expansion. Notifications and all incident actions are local mock interactions; no actual messages or audio are sent.

## Integration points

- `src/lib/call-help/mock-data.ts`: reusable Incident/Zone types and all mock datasets.
- `src/lib/call-help/demo-api.ts`: placeholder Supabase reads/mutations, computer-vision WebSocket ingestion, server-side Gemini analysis, Twilio dispatch, and `triggerAlertSound()`.
- `src/components/call-help/Dashboard.tsx`: coordinated frontend demo state.
- `src/components/call-help/Panels.tsx`: reusable dashboard panels, toast, and accessible incident drawer.
- `src/components/call-help/WarehouseScene.tsx`: local SVG camera illustration with normal/fallen poses.
- `src/components/call-help/dashboard.css`: scoped responsive theme and reduced-motion support.

Production validation: `npm run build`. Webpack is an alternative if this environment blocks Turbopack worker ports. Run `npm run lint` to check the complete project.
