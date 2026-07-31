-- =========================================================
--  НА СПОТЕ — схема базы данных для Supabase
--  Выполните этот файл целиком в Supabase Dashboard → SQL Editor
-- =========================================================

-- расширение для геометрии/геоиндексов не обязательно (используем просто lat/lng float)

-- ---------- ПРОФИЛИ ----------
create table if not exists public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  username text unique not null,
  display_name text not null,
  avatar_url text,
  bio text,
  age int,
  created_at timestamptz default now()
);

alter table public.profiles enable row level security;

create policy "Профили видны всем авторизованным"
  on public.profiles for select
  using (auth.role() = 'authenticated');

create policy "Пользователь редактирует только свой профиль"
  on public.profiles for update
  using (auth.uid() = id);

create policy "Пользователь создаёт только свой профиль"
  on public.profiles for insert
  with check (auth.uid() = id);


-- ---------- ДРУЖБА ----------
create table if not exists public.friendships (
  id bigint generated always as identity primary key,
  requester_id uuid references public.profiles(id) on delete cascade not null,
  addressee_id uuid references public.profiles(id) on delete cascade not null,
  status text not null default 'pending' check (status in ('pending','accepted','declined')),
  created_at timestamptz default now(),
  unique (requester_id, addressee_id)
);

alter table public.friendships enable row level security;

create policy "Участники видят свои дружбы"
  on public.friendships for select
  using (auth.uid() = requester_id or auth.uid() = addressee_id);

create policy "Можно отправить заявку в друзья"
  on public.friendships for insert
  with check (auth.uid() = requester_id);

create policy "Можно обновлять свои заявки (принять/отклонить/удалить)"
  on public.friendships for update
  using (auth.uid() = requester_id or auth.uid() = addressee_id);

create policy "Можно удалить дружбу"
  on public.friendships for delete
  using (auth.uid() = requester_id or auth.uid() = addressee_id);


-- ---------- МЕТКИ (СПОТЫ) ----------
create table if not exists public.spots (
  id bigint generated always as identity primary key,
  owner_id uuid references public.profiles(id) on delete cascade not null,
  title text not null,
  description text,
  lat double precision not null,
  lng double precision not null,
  photo_url text,
  visibility text not null default 'public' check (visibility in ('public','friends')),
  is_live boolean default true,           -- "происходит прямо сейчас"
  created_at timestamptz default now()
);

alter table public.spots enable row level security;

-- Видимость: свои метки, публичные метки, либо метки друзей (если visibility = friends)
create policy "Видимость спотов по правилам приватности"
  on public.spots for select
  using (
    owner_id = auth.uid()
    or visibility = 'public'
    or (
      visibility = 'friends'
      and exists (
        select 1 from public.friendships f
        where f.status = 'accepted'
          and (
            (f.requester_id = auth.uid() and f.addressee_id = owner_id)
            or (f.addressee_id = auth.uid() and f.requester_id = owner_id)
          )
      )
    )
  );

create policy "Пользователь создаёт только свои споты"
  on public.spots for insert
  with check (owner_id = auth.uid());

create policy "Пользователь редактирует только свои споты"
  on public.spots for update
  using (owner_id = auth.uid());

create policy "Пользователь удаляет только свои споты"
  on public.spots for delete
  using (owner_id = auth.uid());


-- ---------- STORAGE (фото спотов) ----------
insert into storage.buckets (id, name, public)
values ('spot-photos', 'spot-photos', true)
on conflict (id) do nothing;

create policy "Публичный просмотр фото спотов"
  on storage.objects for select
  using (bucket_id = 'spot-photos');

create policy "Загрузка фото только авторизованными"
  on storage.objects for insert
  with check (bucket_id = 'spot-photos' and auth.role() = 'authenticated');
