-- =========================================================
--  НА СПОТЕ — миграция v3
--  Добавляет: срок жизни метки (авто-исчезновение по таймеру),
--  хранилище для аватаров/обложек профиля (личный кабинет).
--
--  Выполните в Supabase Dashboard → SQL Editor ПОСЛЕ
--  supabase_schema.sql и supabase_migration_v2.sql.
-- =========================================================

-- ---------- spots: срок жизни метки ----------
alter table public.spots
  add column if not exists expires_at timestamptz;

create index if not exists idx_spots_expires_at on public.spots(expires_at);

-- ---------- storage: аватары и обложки профиля ----------
insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', true)
on conflict (id) do nothing;

create policy "Публичный просмотр аватаров"
  on storage.objects for select
  using (bucket_id = 'avatars');

create policy "Загрузка аватаров авторизованными"
  on storage.objects for insert
  with check (bucket_id = 'avatars' and auth.role() = 'authenticated');

create policy "Замена своего аватара"
  on storage.objects for update
  using (bucket_id = 'avatars' and auth.role() = 'authenticated');
