-- =========================================================
--  НА СПОТЕ — миграция v5
--  Добавляет: волны (временные события), достижения/XP,
--  голосовые метки, совместные метки
-- =========================================================

-- ---------- spots: волны и голосовые ----------
alter table public.spots
add column if not exists wave_ends_at timestamptz,
add column if not exists wave_max_people int,
add column if not exists voice_url text,
add column if not exists mood text;

create index if not exists idx_spots_wave_ends_at on public.spots(wave_ends_at);

-- ---------- достижения и XP ----------
create table if not exists public.user_achievements (
  id bigint generated always as identity primary key,
  user_id uuid references public.profiles(id) on delete cascade not null,
  badge_type text not null,
  badge_name text not null,
  badge_icon text,
  xp int default 10,
  earned_at timestamptz default now()
);

alter table public.user_achievements enable row level security;

create policy "Достижения видны всем"
on public.user_achievements for select
using (auth.role() = 'authenticated');

create policy "Система создаёт достижения"
on public.user_achievements for insert
with check (auth.role() = 'authenticated');

-- ---------- XP в профилях ----------
alter table public.profiles
add column if not exists xp int default 0,
add column if not exists level int default 1;

-- ---------- совместные метки ----------
create table if not exists public.spot_collaborators (
  spot_id bigint references public.spots(id) on delete cascade not null,
  user_id uuid references public.profiles(id) on delete cascade not null,
  joined_at timestamptz default now(),
  primary key (spot_id, user_id)
);

alter table public.spot_collaborators enable row level security;

create policy "Участники видят совместные метки"
on public.spot_collaborators for select
using (auth.role() = 'authenticated');

create policy "Можно присоединиться к метке"
on public.spot_collaborators for insert
with check (auth.uid() = user_id);

create policy "Можно покинуть метку"
on public.spot_collaborators for delete
using (auth.uid() = user_id);

-- ---------- storage: голосовые ----------
insert into storage.buckets (id, name, public)
values ('voice-notes', 'voice-notes', true)
on conflict (id) do nothing;

create policy "Публичный просмотр голосовых"
on storage.objects for select
using (bucket_id = 'voice-notes');

create policy "Загрузка голосовых авторизованными"
on storage.objects for insert
with check (bucket_id = 'voice-notes' and auth.role() = 'authenticated');

-- ---------- функция для начисления XP ----------
create or replace function award_spot_xp()
returns trigger as $$
declare
  current_xp int;
  new_level int;
begin
  -- +10 XP за метку
  update public.profiles
  set xp = xp + 10
  where id = new.owner_id
  returning xp into current_xp;
  
  -- расчёт уровня (каждые 100 XP = +1 уровень)
  new_level := (current_xp / 100) + 1;
  
  update public.profiles
  set level = new_level
  where id = new.owner_id;
  
  -- бейдж за первую метку
  if not exists (
    select 1 from public.user_achievements
    where user_id = new.owner_id and badge_type = 'first_spot'
  ) then
    insert into public.user_achievements (user_id, badge_type, badge_name, badge_icon, xp)
    values (new.owner_id, 'first_spot', 'Первая метка', '🎯', 10);
  end if;
  
  return new;
end;
$$ language plpgsql;

create trigger spot_xp_trigger
after insert on public.spots
for each row execute function award_spot_xp();