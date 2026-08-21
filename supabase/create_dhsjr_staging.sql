-- Run this once in the Supabase SQL editor before using the staging
-- operation in .github/workflows/import-tsv.yml.
-- This statement does not copy production data.

create table if not exists public.dhsjr_staging
  (like public.dhsjr including all);

alter table public.dhsjr_staging enable row level security;

comment on table public.dhsjr_staging is
  'Disposable staging target for validating DHSJR TSV imports before production.';
