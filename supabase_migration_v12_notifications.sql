-- =========================================================
--  КАРТОМЕТР — миграция v12
--  Добавляет:
--  1. Поле friends_seen_at в profiles (для обнуления счётчика заявок)
--  2. Функцию mark_all_messages_read() для обнуления счётчика сообщений
-- =========================================================

begin;

-- 1. Поле "последний раз смотрел заявки в друзья"
alter table public.profiles
add column if not exists friends_seen_at timestamptz;

-- Разрешаем пользователю обновлять это поле
grant update (friends_seen_at) on public.profiles to authenticated;

-- 2. Функция для отметки всех входящих сообщений как прочитанных
create or replace function public.mark_all_messages_read()
returns bigint
language sql
security definer
set search_path = public
as $$
    with updated as (
        update public.messages
        set is_read = true
        where receiver_id = auth.uid()
          and is_read = false
        returning id
    )
    select count(*)::bigint from updated;
$$;

revoke all on function public.mark_all_messages_read() from public, anon, authenticated;
grant execute on function public.mark_all_messages_read() to authenticated;

commit;