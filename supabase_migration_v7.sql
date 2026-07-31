-- =========================================================
--  НА СПОТЕ — миграция v7
--  Добавляет: telegram_id в profiles для бесшовного входа
--  через Telegram Mini App.
-- =========================================================

alter table public.profiles
add column if not exists telegram_id bigint unique;

create index if not exists idx_profiles_telegram_id
on public.profiles(telegram_id);