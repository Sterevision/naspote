-- =========================================================
--  КАРТОМЕТР — миграция v10
--  Активирует друзья-only чаты, диалоги, storage для фото
--  Запускать после schema + v2 + v3 + v4 + v5 + v6 + v7 + v8 + v9
-- =========================================================

begin;

-- =========================================================
-- 1. HELPER: are_friends
-- =========================================================

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

-- =========================================================
-- 2. FRIENDSHIPS CLEANUP
-- =========================================================

delete from public.friendships
where requester_id = addressee_id;

delete from public.friendships f
using public.friendships g
where f.id > g.id
  and least(f.requester_id, f.addressee_id) = least(g.requester_id, g.addressee_id)
  and greatest(f.requester_id, f.addressee_id) = greatest(g.requester_id, g.addressee_id);

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

create unique index if not exists friendships_unique_pair
on public.friendships (
    least(requester_id, addressee_id),
    greatest(requester_id, addressee_id)
);

-- =========================================================
-- 3. MESSAGES: ONLY FRIENDS CAN WRITE
-- =========================================================

drop policy if exists "Пользователь отправляет сообщения" on public.messages;
drop policy if exists messages_insert_friend on public.messages;

create policy messages_insert_friend
on public.messages
for insert
with check (
    auth.uid() = sender_id
    and public.are_friends(sender_id, receiver_id)
);

drop policy if exists messages_update_read on public.messages;

create policy messages_update_read
on public.messages
for update
using (auth.uid() = receiver_id)
with check (
    auth.uid() = receiver_id
    and is_read = true
);

revoke update on public.messages from authenticated;
grant select, insert on public.messages to authenticated;
grant update (is_read) on public.messages to authenticated;

-- =========================================================
-- 4. CONVERSATIONS RPC
-- =========================================================

create or replace function public.get_conversations()
returns table (
    friend_id uuid,
    username text,
    display_name text,
    avatar_url text,
    last_message_text text,
    last_message_at timestamptz,
    last_message_mine boolean,
    unread_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
with friends as (
    select
        case
            when f.requester_id = auth.uid() then f.addressee_id
            else f.requester_id
        end as friend_id
    from public.friendships f
    where f.status = 'accepted'
      and (
            f.requester_id = auth.uid()
            or f.addressee_id = auth.uid()
          )
),
latest_messages as (
    select distinct on (
        case
            when m.sender_id = auth.uid() then m.receiver_id
            else m.sender_id
        end
    )
        case
            when m.sender_id = auth.uid() then m.receiver_id
            else m.sender_id
        end as friend_id,
        m.text,
        m.created_at,
        (m.sender_id = auth.uid()) as mine
    from public.messages m
    where (
              m.sender_id = auth.uid()
              or m.receiver_id = auth.uid()
          )
      and (
              m.sender_id in (select friend_id from friends)
              or m.receiver_id in (select friend_id from friends)
          )
    order by
        case
            when m.sender_id = auth.uid() then m.receiver_id
            else m.sender_id
        end,
        m.created_at desc
),
unread as (
    select
        m.sender_id as friend_id,
        count(*)::bigint as unread_count
    from public.messages m
    where m.receiver_id = auth.uid()
      and m.is_read = false
    group by m.sender_id
)
select
    p.id as friend_id,
    p.username,
    p.display_name,
    p.avatar_url,
    lm.text as last_message_text,
    lm.created_at as last_message_at,
    coalesce(lm.mine, false) as last_message_mine,
    coalesce(u.unread_count, 0) as unread_count
from friends f
join public.profiles p on p.id = f.friend_id
left join latest_messages lm on lm.friend_id = f.friend_id
left join unread u on u.friend_id = f.friend_id
order by
    lm.created_at desc nulls last,
    lower(p.display_name);
$$;

revoke all on function public.get_conversations() from public, anon, authenticated;
grant execute on function public.get_conversations() to authenticated;

-- =========================================================
-- 5. STORAGE BUCKETS
-- =========================================================

insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', true)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('spot-photos', 'spot-photos', true)
on conflict (id) do nothing;

-- =========================================================
-- 6. STORAGE POLICIES
-- =========================================================

drop policy if exists storage_avatars_select on storage.objects;
drop policy if exists storage_avatars_insert on storage.objects;
drop policy if exists "Публичный просмотр аватаров" on storage.objects;
drop policy if exists "Загрузка аватаров авторизованными" on storage.objects;

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

drop policy if exists storage_spot_photos_select on storage.objects;
drop policy if exists storage_spot_photos_insert on storage.objects;
drop policy if exists "Публичный просмотр фото спотов" on storage.objects;
drop policy if exists "Загрузка фото только авторизованными" on storage.objects;

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

-- =========================================================
-- 7. SEQUENCES
-- =========================================================

grant usage on all sequences in schema public to authenticated;

commit;