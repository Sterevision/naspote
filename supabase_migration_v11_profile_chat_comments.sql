-- =========================================================
--  КАРТОМЕТР — миграция v11
--  Добавляет:
--  1. Домашнюю точку пользователя для открытия карты
--  2. Контакты: telegram, телефон, email
--  3. Картинки в личных сообщениях
--  4. Storage-бакет для картинок чата
-- =========================================================

begin;

-- =========================================================
-- 1. PROFILES: домашняя точка и контакты
-- =========================================================

alter table public.profiles
add column if not exists home_lat double precision,
add column if not exists home_lng double precision,
add column if not exists home_location_name text,
add column if not exists telegram_username text,
add column if not exists contact_phone text,
add column if not exists contact_email text;

-- Ограничения координат домашней точки
do $$
begin
    alter table public.profiles
        add constraint profiles_home_lat_range
        check (home_lat is null or home_lat between -90 and 90);
exception
    when duplicate_object then
        null;
    when others then
        raise notice 'profiles_home_lat_range: %', sqlerrm;
end;
$$;

do $$
begin
    alter table public.profiles
        add constraint profiles_home_lng_range
        check (home_lng is null or home_lng between -180 and 180);
exception
    when duplicate_object then
        null;
    when others then
        raise notice 'profiles_home_lng_range: %', sqlerrm;
end;
$$;

-- Ограничения длины контактов
do $$
begin
    alter table public.profiles
        add constraint profiles_home_location_name_length
        check (home_location_name is null or char_length(home_location_name) <= 120);
exception
    when duplicate_object then
        null;
    when others then
        raise notice 'profiles_home_location_name_length: %', sqlerrm;
end;
$$;

do $$
begin
    alter table public.profiles
        add constraint profiles_telegram_username_length
        check (telegram_username is null or char_length(telegram_username) <= 32);
exception
    when duplicate_object then
        null;
    when others then
        raise notice 'profiles_telegram_username_length: %', sqlerrm;
end;
$$;

do $$
begin
    alter table public.profiles
        add constraint profiles_contact_phone_length
        check (contact_phone is null or char_length(contact_phone) <= 30);
exception
    when duplicate_object then
        null;
    when others then
        raise notice 'profiles_contact_phone_length: %', sqlerrm;
end;
$$;

do $$
begin
    alter table public.profiles
        add constraint profiles_contact_email_length
        check (contact_email is null or char_length(contact_email) <= 255);
exception
    when duplicate_object then
        null;
    when others then
        raise notice 'profiles_contact_email_length: %', sqlerrm;
end;
$$;

-- Разрешаем пользователю обновлять новые поля профиля
grant insert (
    home_lat,
    home_lng,
    home_location_name,
    telegram_username,
    contact_phone,
    contact_email
) on public.profiles to authenticated;

grant update (
    home_lat,
    home_lng,
    home_location_name,
    telegram_username,
    contact_phone,
    contact_email
) on public.profiles to authenticated;

-- =========================================================
-- 2. MESSAGES: картинка в сообщении
-- =========================================================

alter table public.messages
add column if not exists image_url text;

-- Разрешаем отправлять сообщение только с картинкой, без текста
alter table public.messages
alter column text drop not null;

-- =========================================================
-- 3. STORAGE: бакет для картинок чата
-- =========================================================

insert into storage.buckets (id, name, public)
values ('chat-images', 'chat-images', true)
on conflict (id) do nothing;

drop policy if exists storage_chat_images_select on storage.objects;
drop policy if exists storage_chat_images_insert on storage.objects;

create policy storage_chat_images_select
on storage.objects
for select
using (bucket_id = 'chat-images');

create policy storage_chat_images_insert
on storage.objects
for insert
with check (
    bucket_id = 'chat-images'
    and auth.role() = 'authenticated'
    and name like auth.uid()::text || '/%'
);

commit;