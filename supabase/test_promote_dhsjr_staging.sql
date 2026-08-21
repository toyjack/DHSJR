-- Run only against a disposable local PostgreSQL database:
--   psql -v ON_ERROR_STOP=1 -f supabase/test_promote_dhsjr_staging.sql

create role anon;
create role authenticated;
create role service_role;

create table public.dhsjr (
  "ID" text primary key,
  "資料番号" text,
  "資料名" text,
  "資料内漢字番号" integer not null,
  "資料内漢語番号" text,
  "単字_見出し" text,
  "単字_出現形" text,
  "漢語_見出し" text,
  "漢語_出現形" text,
  "漢語_alphabet" text,
  "語種" text,
  "漢語内位置" text,
  "単字長" text,
  "声点" text,
  "声点型" text,
  "仮名注" text,
  "仮名型" text,
  "反切" text,
  "類音" text,
  "節博士" text,
  "その他" text,
  "出現位置" text,
  "備考" text
);

create table public.dhsjr_staging
  (like public.dhsjr including all);

\ir promote_dhsjr_staging.sql

insert into public.dhsjr ("ID", "資料内漢字番号", "資料名")
values ('production-before', 1, 'old');
insert into public.dhsjr_staging ("ID", "資料内漢字番号", "資料名")
values ('staging-first', 2, 'new');

select public.promote_dhsjr_staging(1, 'IMPORT_PRODUCTION');

do $$
begin
  if not exists (select 1 from public.dhsjr where "ID" = 'staging-first')
     or not exists (select 1 from public.dhsjr_backup where "ID" = 'production-before') then
    raise exception 'Successful promotion validation failed';
  end if;
end;
$$;

truncate public.dhsjr_staging;
insert into public.dhsjr_staging ("ID", "資料内漢字番号", "資料名")
values ('force-failure', 3, 'must roll back');

create function public.reject_test_row()
returns trigger
language plpgsql
as $$
begin
  if new."ID" = 'force-failure' then
    raise check_violation using message = 'intentional test failure';
  end if;
  return new;
end;
$$;

create trigger reject_test_row
before insert on public.dhsjr
for each row execute function public.reject_test_row();

do $$
begin
  begin
    perform public.promote_dhsjr_staging(1, 'IMPORT_PRODUCTION');
    raise exception 'Promotion unexpectedly succeeded';
  exception
    when check_violation then
      null;
  end;

  if not exists (select 1 from public.dhsjr where "ID" = 'staging-first')
     or exists (select 1 from public.dhsjr where "ID" = 'force-failure') then
    raise exception 'Production was not rolled back after failure';
  end if;

  if not exists (select 1 from public.dhsjr_backup where "ID" = 'production-before')
     or exists (select 1 from public.dhsjr_backup where "ID" = 'staging-first') then
    raise exception 'Previous backup was not preserved after failure';
  end if;
end;
$$;

select 'promotion_success_and_rollback_checks=ok' as result;
