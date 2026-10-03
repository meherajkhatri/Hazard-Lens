import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const api = 'http://127.0.0.1:18080';
const ui = 'http://127.0.0.1:13000';
const key = 'integration-test-only';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

test('CV telemetry → live dashboard → persisted actions → scoped Coach', { timeout: 90000 }, async () => {
  const temp = await mkdtemp(resolve(tmpdir(), 'call-help-integration-'));
  const children = [];
  let logs = '';
  const launch = (command, args, cwd, env) => {
    const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe'] });
    children.push(child);
    child.stdout.on('data', data => { logs += data; });
    child.stderr.on('data', data => { logs += data; });
    return child;
  };
  async function waitFor(url) {
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(url)).ok) return; } catch {}
      await sleep(200);
    }
    throw new Error(`Server did not start: ${url}\n${logs}`);
  }
  const backendEnv = {
    API_KEY: key, STORAGE_BACKEND: 'sqlite', SQLITE_PATH: resolve(temp, 'test.sqlite3'),
    SMS_MODE: 'dry_run', SMS_RECIPIENTS: '+15555550123', GEMINI_API_KEY: '',
    GEMINI_MODEL: '', ALERT_COOLDOWN_SECONDS: '0',
  };
  let reader;
  const abort = new AbortController();
  try {
    launch(process.env.CALL_HELP_TEST_PYTHON || resolve(root, '.venv/bin/python'),
      ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18080'], resolve(root, 'backend'), backendEnv);
    launch(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '13000'],
      resolve(root, 'frontend'), { BACKEND_URL: api, API_KEY: key });
    await Promise.all([waitFor(`${api}/health`), waitFor(`${ui}/api/backend/health`)]);
    const backendRequest = (path, body, headers = {}) => fetch(`${api}${path}`, {
      method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', 'X-API-Key': key, ...headers }, body: body ? JSON.stringify(body) : undefined,
    });
    const browserRequest = (path, method = 'GET', body) => fetch(`${ui}/api/backend/${path}`, {
      method, headers: { 'Content-Type': 'application/json', Origin: ui }, body: body ? JSON.stringify(body) : undefined,
    });
    assert.equal((await backendRequest('/api/v1/incidents', undefined, { 'X-API-Key': 'wrong' })).status, 401);
    assert.deepEqual(await (await browserRequest('incidents')).json(), []);
    assert.equal((await browserRequest('telemetry', 'POST', {})).status, 404);
    assert.equal((await fetch(`${ui}/api/backend/coach/chat`, { method: 'POST', headers: { Origin: 'https://untrusted.example' } })).status, 403);
    assert.equal((await fetch(`${ui}/api/events`, { headers: { Origin: 'https://untrusted.example' } })).status, 403);
    const stream = await fetch(`${ui}/api/events`, { signal: abort.signal });
    assert.match(stream.headers.get('content-type'), /text\/event-stream/);
    reader = stream.body.getReader();
    let buffer = '';
    async function nextEvent() {
      const deadline = setTimeout(() => abort.abort(), 10000);
      try {
        for (;;) {
          const boundary = buffer.indexOf('\n\n');
          if (boundary >= 0) {
            const message = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
            if (message.startsWith('data: ')) return JSON.parse(message.slice(6));
          } else {
            const { value, done } = await reader.read();
            assert.equal(done, false, 'Event stream closed unexpectedly');
            buffer += new TextDecoder().decode(value);
          }
        }
      } finally { clearTimeout(deadline); }
    }
    assert.equal((await nextEvent()).type, 'connected');
    const payload = {
      event_id: crypto.randomUUID(), camera_id: 'zone-1-cam-1', zone_id: 'Zone 1',
      timestamp: new Date().toISOString(), event_type: 'fall', pose_confidence: 0.94,
      metadata: { trigger: 'manual', track_id: 1, torso_angle_deg: 82, bbox_aspect: 1.8 },
    };
    const ingested = await (await backendRequest('/api/v1/telemetry', payload)).json();
    assert.equal(ingested.status, 'received');
    assert.equal(ingested.incident.sms_status, 'dry_run');
    const created = await nextEvent();
    assert.equal(created.type, 'incident.created');
    assert.equal(created.incident.incident_id, payload.event_id);
    assert.equal((await nextEvent()).incident.sms_status, 'dry_run');
    assert.equal((await (await backendRequest('/api/v1/telemetry', payload)).json()).status, 'duplicate');
    const rows = await (await browserRequest('incidents')).json();
    assert.equal(rows.length, 1);
    assert.equal(rows[0].pose_confidence, 0.94);
    const acknowledged = await browserRequest(`incidents/${payload.event_id}`, 'PATCH', { status: 'acknowledged' });
    assert.equal(acknowledged.status, 200);
    assert.equal((await nextEvent()).incident.status, 'acknowledged');
    assert.equal((await (await browserRequest('incidents')).json())[0].status, 'acknowledged');
    const answer = await (await browserRequest('coach/chat', 'POST', { question: 'Summarize recorded falls', zone_id: 'Zone 1' })).json();
    assert.equal(answer.mode, 'local_summary');
    assert.equal(answer.context_count, 1);
    assert.deepEqual(answer.incident_ids, [payload.event_id]);
    const empty = await (await browserRequest('coach/chat', 'POST', { question: 'Summarize', zone_id: 'Zone 2' })).json();
    assert.equal(empty.context_count, 0);
    await browserRequest(`incidents/${payload.event_id}`, 'PATCH', { status: 'resolved' });
    assert.equal((await nextEvent()).incident.status, 'resolved');
    assert.equal((await browserRequest(`incidents/${payload.event_id}`, 'PATCH', { status: 'acknowledged' })).status, 409);
    assert.equal((await (await browserRequest('incidents')).json())[0].status, 'resolved');
    // Closing and reopening the bridge supports the browser reconnect path.
    await reader.cancel();
    const reconnect = await fetch(`${ui}/api/events`, { signal: abort.signal });
    reader = reconnect.body.getReader(); buffer = '';
    assert.equal((await nextEvent()).type, 'connected');
    assert.equal((await (await browserRequest('incidents')).json()).length, 1);
    assert.equal((await fetch(ui)).status, 200);
  } catch (error) {
    error.message += `\nServer logs:\n${logs}`;
    throw error;
  } finally {
    abort.abort();
    await reader?.cancel().catch(() => {});
    for (const child of children) child.kill('SIGTERM');
    await Promise.all(children.map(child => new Promise(resolve => {
      if (child.exitCode !== null) return resolve();
      child.once('exit', resolve);
      setTimeout(() => { child.kill('SIGKILL'); resolve(); }, 3000).unref();
    })));
    await rm(temp, { recursive: true, force: true });
  }
});
