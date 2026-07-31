-- =========================================================
--  НА СПОТЕ — миграция v4
--  Добавляет: категорию у самой метки (не только у организации)
--  и персональные настройки видимости меток по категориям.
--
--  Выполните в Supabase Dashboard → SQL Editor ПОСЛЕ
--  supabase_schema.sql, supabase_migration_v2.sql, supabase_migration_v3.sql.
-- =========================================================

-- ---------- spots: категория метки ----------
alter table public.spots
  add column if not exists category text;

create index if not exists idx_spots_category on public.spots(category);

-- ---------- profiles: какие категории пользователь хочет видеть на карте ----------
-- NULL = показывать всё (значение по умолчанию, ничего не отфильтровано)
alter table public.profiles
  add column if not exists visible_categories text[];
