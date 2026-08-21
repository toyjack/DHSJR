-- MANUAL EMERGENCY RECOVERY ONLY.
-- Review the backup row count and representative records before running this file.
-- Every statement is one transaction; any validation failure restores the current
-- production table automatically.

begin;

lock table public.dhsjr_backup in share mode;
lock table public.dhsjr in access exclusive mode;

do $$
declare
  backup_count bigint;
begin
  select count(*) into backup_count from public.dhsjr_backup;
  if backup_count <= 0 then
    raise exception 'Refusing to restore an empty dhsjr_backup';
  end if;
end;
$$;

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
from public.dhsjr_backup;

do $$
declare
  backup_count bigint;
  production_count bigint;
begin
  select count(*) into backup_count from public.dhsjr_backup;
  select count(*) into production_count from public.dhsjr;
  if production_count <> backup_count then
    raise exception 'Restore validation failed: production %, backup %',
      production_count, backup_count;
  end if;
end;
$$;

commit;
