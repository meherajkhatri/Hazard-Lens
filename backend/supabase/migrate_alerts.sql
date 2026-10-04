-- Run once for an existing Supabase incidents table. Safe to re-run.
do $$
begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'incidents' and column_name = 'sms_status')
     and not exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'incidents' and column_name = 'alert_status') then
    alter table public.incidents rename column sms_status to alert_status;
  end if;
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'incidents' and column_name = 'sms_results')
     and not exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'incidents' and column_name = 'alert_results') then
    alter table public.incidents rename column sms_results to alert_results;
  end if;
end $$;
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
