-- Run once in your Supabase SQL editor. Server-only Data API access.
create table if not exists public.incidents (
  incident_id uuid primary key,
  camera_id text not null,
  zone_id text not null,
  event_type text not null check (event_type in ('fall', 'ppe_violation', 'collision_risk')),
  pose_confidence double precision not null check (pose_confidence between 0 and 1),
  severity text not null check (severity in ('high', 'medium')),
  description text not null,
  location text not null,
  detected_at timestamptz not null,
  received_at timestamptz not null,
  status text not null default 'active' check (status in ('active', 'acknowledged', 'resolved')),
  sms_status text not null default 'not_required',
  sms_results jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb
);
create index if not exists incidents_zone_time on public.incidents(zone_id, detected_at desc);
create index if not exists incidents_status_time on public.incidents(status, detected_at desc);
alter table public.incidents enable row level security;
revoke all on public.incidents from anon, authenticated;
grant select, insert, update on public.incidents to service_role;
