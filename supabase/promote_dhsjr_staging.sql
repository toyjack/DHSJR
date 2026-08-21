-- Install this function once in the Supabase SQL editor.
--
-- The function promotes the already validated staging table inside one database
-- transaction. PostgreSQL rolls back the backup replacement, TRUNCATE, and INSERT
-- together if any statement or validation fails.

create or replace function public.promote_dhsjr_staging(
  expected_count bigint,
  confirmation text
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
set statement_timeout = '60s'
as $$
declare
  staging_count bigint;
  production_count_before bigint;
  backup_count bigint;
  inserted_count bigint;
  production_count_after bigint;
begin
  if confirmation is distinct from 'IMPORT_PRODUCTION' then
    raise exception 'Production confirmation is invalid';
  end if;

  if expected_count is null or expected_count <= 0 then
    raise exception 'Expected row count must be positive';
  end if;

  -- Serialize promotions and prevent either table from changing during the copy.
  perform pg_advisory_xact_lock(pg_catalog.hashtextextended('dhsjr-promotion', 0));
  lock table public.dhsjr_staging in share mode;
  lock table public.dhsjr in access exclusive mode;

  select count(*) into staging_count from public.dhsjr_staging;
  if staging_count <> expected_count then
    raise exception 'Staging row count % does not match expected %',
      staging_count, expected_count;
  end if;

  select count(*) into production_count_before from public.dhsjr;

  -- Keep the immediately previous production contents for manual recovery.
  -- Transactional DDL means an older backup remains intact if this call fails.
  -- The recovery snapshot intentionally has no indexes: rebuilding production
  -- indexes for the backup would consume most of the API transaction timeout.
  drop table if exists public.dhsjr_backup;
  create table public.dhsjr_backup
    (like public.dhsjr including defaults including generated including identity);
  alter table public.dhsjr_backup enable row level security;
  revoke all on table public.dhsjr_backup from anon, authenticated;

  insert into public.dhsjr_backup (
    "ID", "資料番号", "資料名", "資料内漢字番号", "資料内漢語番号",
    "単字_見出し", "単字_出現形", "漢語_見出し", "漢語_出現形",
    "漢語_alphabet", "語種", "漢語内位置", "単字長", "声点", "声点型",
    "仮名注", "仮名型", "反切", "類音", "節博士", "その他", "出現位置", "備考"
  )
  select
    "ID", "資料番号", "資料名", "資料内漢字番号", "資料内漢語番号",
    "単字_見出し", "単字_出現形", "漢語_見出し", "漢語_出現形",
    "漢語_alphabet", "語種", "漢語内位置", "単字長", "声点", "声点型",
    "仮名注", "仮名型", "反切", "類音", "節博士", "その他", "出現位置", "備考"
  from public.dhsjr;
  get diagnostics backup_count = row_count;

  if backup_count <> production_count_before then
    raise exception 'Backup row count % does not match production %',
      backup_count, production_count_before;
  end if;

  truncate table public.dhsjr;

  insert into public.dhsjr (
    "ID", "資料番号", "資料名", "資料内漢字番号", "資料内漢語番号",
    "単字_見出し", "単字_出現形", "漢語_見出し", "漢語_出現形",
    "漢語_alphabet", "語種", "漢語内位置", "単字長", "声点", "声点型",
    "仮名注", "仮名型", "反切", "類音", "節博士", "その他", "出現位置", "備考"
  )
  select
    "ID", "資料番号", "資料名", "資料内漢字番号", "資料内漢語番号",
    "単字_見出し", "単字_出現形", "漢語_見出し", "漢語_出現形",
    "漢語_alphabet", "語種", "漢語内位置", "単字長", "声点", "声点型",
    "仮名注", "仮名型", "反切", "類音", "節博士", "その他", "出現位置", "備考"
  from public.dhsjr_staging;
  get diagnostics inserted_count = row_count;

  select count(*) into production_count_after from public.dhsjr;
  if inserted_count <> expected_count
     or production_count_after <> expected_count then
    raise exception 'Production row count validation failed: inserted %, actual %, expected %',
      inserted_count, production_count_after, expected_count;
  end if;

  return jsonb_build_object(
    'staging_count', staging_count,
    'production_count_before', production_count_before,
    'backup_count', backup_count,
    'production_count_after', production_count_after
  );
end;
$$;

revoke all on function public.promote_dhsjr_staging(bigint, text) from public;
grant execute on function public.promote_dhsjr_staging(bigint, text) to service_role;

comment on function public.promote_dhsjr_staging(bigint, text) is
  'Atomically backs up dhsjr and replaces it with validated dhsjr_staging contents.';
