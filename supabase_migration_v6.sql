-- =========================================================
--  НА СПОТЕ — миграция v6 (безопасная, можно выполнять повторно)
--  Добавляет: место обитания, комментарии к меткам, личные сообщения
--
--  Выполните в Supabase Dashboard → SQL Editor ПОСЛЕ
--  supabase_schema.sql, supabase_migration_v2.sql, v3.sql, v4.sql, v5.sql.
-- =========================================================

-- 1. Место обитания в профиле
alter table public.profiles add column if not exists location text;

-- 2. Таблица комментариев к меткам
create table if not exists public.spot_comments (
  id bigint generated always as identity primary key,
  spot_id bigint references public.spots(id) on delete cascade not null,
  user_id uuid references public.profiles(id) on delete cascade not null,
  text text not null,
  created_at timestamptz default now()
);
alter table public.spot_comments enable row level security;

-- Удаляем старые политики (если были) и создаём заново
drop policy if exists "Комментарии видны всем авторизованным" on public.spot_comments;
drop policy if exists "Комментарии видны всем авторизова" on public.spot_comments;
drop policy if exists "Пользователь создаёт комментарии" on public.spot_comments;
drop policy if exists "Пользователь удаляет свои комментарии" on public.spot_comments;

create policy "Комментарии видны всем авторизованным"
  on public.spot_comments for select
  using (auth.role() = 'authenticated');

create policy "Пользователь создаёт комментарии"
  on public.spot_comments for insert
  with check (auth.uid() = user_id);

create policy "Пользователь удаляет свои комментарии"
  on public.spot_comments for delete
  using (auth.uid() = user_id);

-- 3. Таблица личных сообщений
create table if not exists public.messages (
  id bigint generated always as identity primary key,
  sender_id uuid references public.profiles(id) on delete cascade not null,
  receiver_id uuid references public.profiles(id) on delete cascade not null,
  text text not null,
  is_read boolean default false,
  created_at timestamptz default now()
);
alter table public.messages enable row level security;

-- Удаляем старые политики (если были) и создаём заново
drop policy if exists "Пользователь видит свои сообщения" on public.messages;
drop policy if exists "Пользователь отправляет сообщения" on public.messages;
drop policy if exists "Пользователь помечает сообщения прочитанными" on public.messages;

create policy "Пользователь видит свои сообщения"
  on public.messages for select
  using (auth.uid() = sender_id or auth.uid() = receiver_id);

create policy "Пользователь отправляет сообщения"
  on public.messages for insert
  with check (auth.uid() = sender_id);

create policy "Пользователь помечает сообщения прочитанными"
  on public.messages for update
  using (auth.uid() = receiver_id);

-- 4. Индексы для ускорения запросов
create index if not exists idx_spot_comments_spot_id on public.spot_comments(spot_id);
create index if not exists idx_messages_conversation
  on public.messages(sender_id, receiver_id, created_at);
