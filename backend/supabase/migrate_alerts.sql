-- Run once for an existing Supabase incidents table.
alter table public.incidents rename column sms_status to alert_status;
alter table public.incidents rename column sms_results to alert_results;
update public.incidents
set alert_status = 'not_configured'
where alert_status is null;
update public.incidents
set alert_results = '[]'::jsonb
where alert_results is null;
alter table public.incidents alter column alert_status set default 'not_configured';
alter table public.incidents alter column alert_results set default '[]'::jsonb;
alter table public.incidents alter column alert_status set not null;
alter table public.incidents alter column alert_results set not null;
