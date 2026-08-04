-- =========================================================
--  КАРТОМЕТР / НА СПОТЕ — миграция v9
--  Добавляет функцию get_conversations() для списка диалогов
--  Запускать после v8 security migration
-- =========================================================

begin;

drop function if exists public.get_conversations();

create function public.get_conversations()
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
    where
        f.status = 'accepted'
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
    where
        (
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
    where
        m.receiver_id = auth.uid()
        and m.is_read = false
    group by
        m.sender_id
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

commit;