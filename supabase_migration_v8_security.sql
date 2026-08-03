-- =========================================================
--  КАРТОМЕТР / НА СПОТЕ — миграция v8
--  Security hardening + RLS fixes + anti-abuse
--  Запускать после schema + v2 + v3 + v4 + v5 + v6 + v7
-- =========================================================

begin;

-- =========================================================
-- 1. HELPER FUNCTIONS
-- =========================================================

-- Проверка дружбы между двумя пользователями
create or replace function public.are_friends(u1 uuid, u2 uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.friendships f
    where f.status = 'accepted'
      and (
        (f.requester_id = u1 and f.addressee_id = u2)
        or
        (f.requester_id = u2 and f.addressee_id = u1)
      )
  );
$$;

revoke all on function public.are_friends(uuid, uuid) from public, anon, authenticated;
grant execute on function public.are_friends(uuid, uuid) to authenticated;


-- Проверка видимости метки для текущего пользователя
create or replace function public.can_view_spot(p_spot_id bigint)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.spots s
    where s.id = p_spot_id
      and (
        -- владелец видит свои метки всегда, даже истёкшие
        s.owner_id = auth.uid()
        or (
          -- чужие видим только если они не истекли
          (s.expires_at is null or s.expires_at > now())
          and (
            s.visibility = 'public'
            or (
              s.visibility = 'friends'
              and public.are_friends(auth.uid(), s.owner_id)
            )
          )
        )
      )
  );
$$;

revoke all on function public.can_view_spot(bigint) from public, anon, authenticated;
grant execute on function public.can_view_spot(bigint) to authenticated;


-- =========================================================
-- 2. VALIDATION TRIGGER FOR SPOTS.ORGANIZATION_ID
-- =========================================================

create or replace function public.validate_spot_organization()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.organization_id is not null then
    if not exists (
      select 1
      from public.profiles
      where id = new.organization_id
        and account_type = 'organization'
    ) then
      raise exception 'organization_id must reference an organization profile';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists trg_validate_spot_organization on public.spots;

create trigger trg_validate_spot_organization
before insert or update of organization_id
on public.spots
for each row
execute function public.validate_spot_organization();


-- =========================================================
-- 3. ANTI XP FARM
-- =========================================================

create table if not exists public.xp_awards (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(id) on delete cascade,
  award_date date not null default current_date,
  unique (user_id, award_date)
);

revoke all on table public.xp_awards from anon, authenticated;

create or replace function public.award_spot_xp()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_xp int;
  v_level int;
  v_awarded boolean := false;
begin
  -- Разрешаем начислять XP максимум 1 раз в день на пользователя.
  -- Это защищает от фарма: удалить метку -> создать метку -> получить XP.
  begin
    insert into public.xp_awards (user_id, award_date)
    values (new.owner_id, current_date);

    v_awarded := true;
  exception when unique_violation then
    v_awarded := false;
  end;

  if v_awarded then
    update public.profiles
    set xp = coalesce(xp, 0) + 10
    where id = new.owner_id
    returning xp into v_xp;

    v_level := coalesce(v_xp / 100, 0) + 1;

    update public.profiles
    set level = v_level
    where id = new.owner_id;

    if not exists (
      select 1
      from public.user_achievements
      where user_id = new.owner_id
        and badge_type = 'first_spot'
    ) then
      insert into public.user_achievements (user_id, badge_type, badge_name, badge_icon, xp)
      values (new.owner_id, 'first_spot', 'Первая метка', '🎯', 10);
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists spot_xp_trigger on public.spots;

create trigger spot_xp_trigger
after insert
on public.spots
for each row
execute function public.award_spot_xp();


-- =========================================================
-- 4. FRIENDSHIP CLEANUP + UNIQUE PAIR
-- =========================================================

-- Удаляем дружбу с самим собой, если вдруг есть
delete from public.friendships
where requester_id = addressee_id;

-- Удаляем зеркальные дубли: A->B и B->A, оставляем самую раннюю запись
delete from public.friendships f
using public.friendships g
where f.id > g.id
  and least(f.requester_id, f.addressee_id) = least(g.requester_id, g.addressee_id)
  and greatest(f.requester_id, f.addressee_id) = greatest(g.requester_id, g.addressee_id);

-- Запрет дружбы с самим собой
do $$
begin
  alter table public.friendships
  add constraint friendships_not_self
  check (requester_id <> addressee_id);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'friendships_not_self: %', sqlerrm;
end;
$$;

-- Одна пара пользователей = одна запись дружбы
create unique index if not exists friendships_unique_pair
on public.friendships (
  least(requester_id, addressee_id),
  greatest(requester_id, addressee_id)
);


-- =========================================================
-- 5. PROFILES: POLICIES + COLUMN PRIVILEGES
-- =========================================================

drop policy if exists "Профили видны всем авторизованным" on public.profiles;
drop policy if exists "Пользователь редактирует только свой профиль" on public.profiles;
drop policy if exists "Пользователь создаёт только свой профиль" on public.profiles;

drop policy if exists profiles_select on public.profiles;
drop policy if exists profiles_insert_own on public.profiles;
drop policy if exists profiles_update_own on public.profiles;

create policy profiles_select
on public.profiles
for select
using (auth.role() = 'authenticated');

create policy profiles_insert_own
on public.profiles
for insert
with check (auth.uid() = id);

create policy profiles_update_own
on public.profiles
for update
using (auth.uid() = id)
with check (auth.uid() = id);

-- Ограничиваем INSERT/UPDATE на уровне колонок.
-- Пользователь не сможет сам менять is_verified, xp, level, account_type, telegram_id.
revoke insert, update on public.profiles from authenticated;

grant select on public.profiles to authenticated;

grant insert (
  id,
  username,
  display_name,
  avatar_url,
  bio,
  age,
  account_type,
  category,
  address,
  cover_url,
  lat,
  lng,
  location,
  visible_categories
) on public.profiles to authenticated;

grant update (
  display_name,
  avatar_url,
  bio,
  age,
  location,
  category,
  address,
  cover_url,
  lat,
  lng,
  visible_categories
) on public.profiles to authenticated;


-- =========================================================
-- 6. FRIENDSHIPS: POLICIES + COLUMN PRIVILEGES
-- =========================================================

drop policy if exists "Участники видят свои дружбы" on public.friendships;
drop policy if exists "Можно отправить заявку в друзья" on public.friendships;
drop policy if exists "Можно обновлять свои заявки (принять/отклонить/удалить)" on public.friendships;
drop policy if exists "Можно удалить дружбу" on public.friendships;

drop policy if exists friendships_select on public.friendships;
drop policy if exists friendships_insert_request on public.friendships;
drop policy if exists friendships_update_accept on public.friendships;
drop policy if exists friendships_delete on public.friendships;

create policy friendships_select
on public.friendships
for select
using (
  auth.uid() = requester_id
  or auth.uid() = addressee_id
);

create policy friendships_insert_request
on public.friendships
for insert
with check (
  auth.uid() = requester_id
  and requester_id <> addressee_id
);

-- Обновлять заявку может только получатель, и только принимать её.
-- Отклонение у нас сделано через DELETE.
create policy friendships_update_accept
on public.friendships
for update
using (auth.uid() = addressee_id)
with check (
  auth.uid() = addressee_id
  and status = 'accepted'
);

create policy friendships_delete
on public.friendships
for delete
using (
  auth.uid() = requester_id
  or auth.uid() = addressee_id
);

-- Ограничиваем UPDATE только колонкой status
revoke update on public.friendships from authenticated;

grant select, insert, delete on public.friendships to authenticated;
grant update (status) on public.friendships to authenticated;


-- =========================================================
-- 7. SPOTS: POLICIES
-- =========================================================

drop policy if exists "Видимость спотов по правилам приватности" on public.spots;
drop policy if exists "Пользователь создаёт только свои споты" on public.spots;
drop policy if exists "Пользователь редактирует только свои споты" on public.spots;
drop policy if exists "Пользователь удаляет только свои споты" on public.spots;

drop policy if exists spots_select_visible on public.spots;
drop policy if exists spots_insert_own on public.spots;
drop policy if exists spots_update_own on public.spots;
drop policy if exists spots_delete_own on public.spots;

create policy spots_select_visible
on public.spots
for select
using (
  owner_id = auth.uid()
  or (
    (expires_at is null or expires_at > now())
    and (
      visibility = 'public'
      or (
        visibility = 'friends'
        and public.are_friends(auth.uid(), owner_id)
      )
    )
  )
);

create policy spots_insert_own
on public.spots
for insert
with check (
  owner_id = auth.uid()
  and (expires_at is null or expires_at > now())
);

create policy spots_update_own
on public.spots
for update
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

create policy spots_delete_own
on public.spots
for delete
using (owner_id = auth.uid());


-- =========================================================
-- 8. SPOT COMMENTS: POLICIES + GRANTS
-- =========================================================

drop policy if exists "Комментарии видны всем авторизованным" on public.spot_comments;
drop policy if exists "Пользователь создаёт комментарии" on public.spot_comments;
drop policy if exists "Пользователь удаляет свои комментарии" on public.spot_comments;

drop policy if exists spot_comments_select_visible on public.spot_comments;
drop policy if exists spot_comments_insert_own on public.spot_comments;
drop policy if exists spot_comments_delete_own on public.spot_comments;

create policy spot_comments_select_visible
on public.spot_comments
for select
using (
  auth.role() = 'authenticated'
  and public.can_view_spot(spot_id)
);

create policy spot_comments_insert_own
on public.spot_comments
for insert
with check (
  auth.uid() = user_id
  and public.can_view_spot(spot_id)
);

create policy spot_comments_delete_own
on public.spot_comments
for delete
using (auth.uid() = user_id);

revoke all on public.spot_comments from authenticated;
grant select, insert, delete on public.spot_comments to authenticated;


-- =========================================================
-- 9. MESSAGES: POLICIES + COLUMN PRIVILEGES
-- =========================================================

drop policy if exists "Пользователь видит свои сообщения" on public.messages;
drop policy if exists "Пользователь отправляет сообщения" on public.messages;
drop policy if exists "Пользователь помечает сообщения прочитанными" on public.messages;

drop policy if exists messages_select on public.messages;
drop policy if exists messages_insert_friend on public.messages;
drop policy if exists messages_update_read on public.messages;

create policy messages_select
on public.messages
for select
using (
  auth.uid() = sender_id
  or auth.uid() = receiver_id
);

-- Сообщения можно отправлять только друзьям.
-- Если хочешь разрешить писать всем пользователям, эту политику нужно изменить.
create policy messages_insert_friend
on public.messages
for insert
with check (
  auth.uid() = sender_id
  and public.are_friends(sender_id, receiver_id)
);

-- Получатель может только помечать сообщения прочитанными.
create policy messages_update_read
on public.messages
for update
using (auth.uid() = receiver_id)
with check (
  auth.uid() = receiver_id
  and is_read = true
);

-- Запрещаем прямой UPDATE текста сообщения.
-- Разрешаем обновлять только is_read.
revoke update on public.messages from authenticated;

grant select, insert on public.messages to authenticated;
grant update (is_read) on public.messages to authenticated;


-- =========================================================
-- 10. SPOT COLLABORATORS: POLICIES + GRANTS
-- =========================================================

drop policy if exists "Участники видят совместные метки" on public.spot_collaborators;
drop policy if exists "Можно присоединиться к метке" on public.spot_collaborators;
drop policy if exists "Можно покинуть метку" on public.spot_collaborators;

drop policy if exists spot_collaborators_select_visible on public.spot_collaborators;
drop policy if exists spot_collaborators_insert_own on public.spot_collaborators;
drop policy if exists spot_collaborators_delete_own on public.spot_collaborators;

create policy spot_collaborators_select_visible
on public.spot_collaborators
for select
using (
  auth.role() = 'authenticated'
  and public.can_view_spot(spot_id)
);

create policy spot_collaborators_insert_own
on public.spot_collaborators
for insert
with check (
  auth.uid() = user_id
  and public.can_view_spot(spot_id)
);

create policy spot_collaborators_delete_own
on public.spot_collaborators
for delete
using (auth.uid() = user_id);

revoke all on public.spot_collaborators from authenticated;
grant select, insert, delete on public.spot_collaborators to authenticated;


-- =========================================================
-- 11. USER ACHIEVEMENTS: CLOSE INSERT/UPDATE/DELETE
-- =========================================================

drop policy if exists "Достижения видны всем" on public.user_achievements;
drop policy if exists "Система создаёт достижения" on public.user_achievements;

drop policy if exists user_achievements_select_own on public.user_achievements;

create policy user_achievements_select_own
on public.user_achievements
for select
using (auth.uid() = user_id);

-- Пользователь не должен сам создавать/менять/удалять достижения.
-- Их создаёт trigger / server-side logic.
revoke all on public.user_achievements from authenticated;
grant select on public.user_achievements to authenticated;


-- =========================================================
-- 12. STORAGE: USER FOLDER RESTRICTIONS
-- =========================================================

-- spot-photos
drop policy if exists "Публичный просмотр фото спотов" on storage.objects;
drop policy if exists "Загрузка фото только авторизованными" on storage.objects;

drop policy if exists storage_spot_photos_select on storage.objects;
drop policy if exists storage_spot_photos_insert on storage.objects;

create policy storage_spot_photos_select
on storage.objects
for select
using (bucket_id = 'spot-photos');

create policy storage_spot_photos_insert
on storage.objects
for insert
with check (
  bucket_id = 'spot-photos'
  and auth.role() = 'authenticated'
  and name like auth.uid()::text || '/%'
);

-- avatars
drop policy if exists "Публичный просмотр аватаров" on storage.objects;
drop policy if exists "Загрузка аватаров авторизованными" on storage.objects;
drop policy if exists "Замена своего аватара" on storage.objects;

drop policy if exists storage_avatars_select on storage.objects;
drop policy if exists storage_avatars_insert on storage.objects;
drop policy if exists storage_avatars_update on storage.objects;

create policy storage_avatars_select
on storage.objects
for select
using (bucket_id = 'avatars');

create policy storage_avatars_insert
on storage.objects
for insert
with check (
  bucket_id = 'avatars'
  and auth.role() = 'authenticated'
  and name like auth.uid()::text || '/%'
);

create policy storage_avatars_update
on storage.objects
for update
using (
  bucket_id = 'avatars'
  and auth.role() = 'authenticated'
  and name like auth.uid()::text || '/%'
)
with check (
  bucket_id = 'avatars'
  and auth.role() = 'authenticated'
  and name like auth.uid()::text || '/%'
);

-- voice-notes
drop policy if exists "Публичный просмотр голосовых" on storage.objects;
drop policy if exists "Загрузка голосовых авторизованными" on storage.objects;

drop policy if exists storage_voice_notes_select on storage.objects;
drop policy if exists storage_voice_notes_insert on storage.objects;

create policy storage_voice_notes_select
on storage.objects
for select
using (bucket_id = 'voice-notes');

create policy storage_voice_notes_insert
on storage.objects
for insert
with check (
  bucket_id = 'voice-notes'
  and auth.role() = 'authenticated'
  and name like auth.uid()::text || '/%'
);


-- =========================================================
-- 13. SAFE CONSTRAINTS
-- =========================================================

-- spots coordinates
do $$
begin
  alter table public.spots
  add constraint spots_lat_range
  check (lat between -90 and 90);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spots_lat_range: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.spots
  add constraint spots_lng_range
  check (lng between -180 and 180);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spots_lng_range: %', sqlerrm;
end;
$$;

-- profiles coordinates
do $$
begin
  alter table public.profiles
  add constraint profiles_lat_range
  check (lat is null or lat between -90 and 90);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_lat_range: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.profiles
  add constraint profiles_lng_range
  check (lng is null or lng between -180 and 180);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_lng_range: %', sqlerrm;
end;
$$;

-- profiles age
do $$
begin
  alter table public.profiles
  add constraint profiles_age_range
  check (age is null or age between 13 and 120);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_age_range: %', sqlerrm;
end;
$$;

-- spots text limits
do $$
begin
  alter table public.spots
  add constraint spots_title_length
  check (char_length(title) <= 120);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spots_title_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.spots
  add constraint spots_description_length
  check (description is null or char_length(description) <= 1000);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spots_description_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.spots
  add constraint spots_mood_length
  check (mood is null or char_length(mood) <= 50);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spots_mood_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.spots
  add constraint spots_category_length
  check (category is null or char_length(category) <= 50);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spots_category_length: %', sqlerrm;
end;
$$;

-- comments/messages text limits
do $$
begin
  alter table public.spot_comments
  add constraint spot_comments_text_length
  check (char_length(text) <= 500);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'spot_comments_text_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.messages
  add constraint messages_text_length
  check (char_length(text) <= 2000);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'messages_text_length: %', sqlerrm;
end;
$$;

-- profiles text limits
do $$
begin
  alter table public.profiles
  add constraint profiles_username_length
  check (char_length(username) <= 30);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_username_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.profiles
  add constraint profiles_display_name_length
  check (char_length(display_name) <= 80);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_display_name_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.profiles
  add constraint profiles_bio_length
  check (bio is null or char_length(bio) <= 500);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_bio_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.profiles
  add constraint profiles_location_length
  check (location is null or char_length(location) <= 100);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_location_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.profiles
  add constraint profiles_category_length
  check (category is null or char_length(category) <= 50);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_category_length: %', sqlerrm;
end;
$$;

do $$
begin
  alter table public.profiles
  add constraint profiles_address_length
  check (address is null or char_length(address) <= 200);
exception
  when duplicate_object then
    null;
  when others then
    raise notice 'profiles_address_length: %', sqlerrm;
end;
$$;


-- =========================================================
-- 14. INDEXES
-- =========================================================

create index if not exists idx_friendships_requester_status
on public.friendships(requester_id, status);

create index if not exists idx_friendships_addressee_status
on public.friendships(addressee_id, status);

create index if not exists idx_spots_owner_created
on public.spots(owner_id, created_at desc);

create index if not exists idx_spots_organization_created
on public.spots(organization_id, created_at desc);

create index if not exists idx_messages_receiver_read
on public.messages(receiver_id, is_read);

create index if not exists idx_messages_sender_receiver_created
on public.messages(sender_id, receiver_id, created_at);

create index if not exists idx_spot_comments_spot_created
on public.spot_comments(spot_id, created_at);

create index if not exists idx_spot_collaborators_spot
on public.spot_collaborators(spot_id);

create index if not exists idx_xp_awards_user_date
on public.xp_awards(user_id, award_date);


-- =========================================================
-- 15. SEQUENCE USAGE
-- =========================================================

-- На всякий случай даём authenticated доступ к последовательностям,
-- чтобы INSERT в таблицы с identity не ломался.
grant usage on all sequences in schema public to authenticated;

commit;