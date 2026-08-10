-- =========================================================
--  КАРТОМЕТР — миграция v15
--  Добавляет: аудио-фрагменты к меткам (Audio/Vibe Snippets)
-- =========================================================
begin;

-- Колонка для ссылки на аудио
alter table public.spots
add column if not exists audio_url text;

-- Публичный бакет для аудио
insert into storage.buckets (id, name, public)
values ('spot-audio', 'spot-audio', true)
on conflict (id) do nothing;

commit;

-- Политики доступа к бакету (запускать отдельно, можно по одной)
drop policy if exists spot_audio_read on storage.objects;
drop policy if exists spot_audio_write on storage.objects;

-- Читать аудио могут все (публичный бакет)
create policy spot_audio_read
on storage.objects for select
using (bucket_id = 'spot-audio');

-- Записывать могут только авторизованные
create policy spot_audio_write
on storage.objects for insert to authenticated
with check (bucket_id = 'spot-audio');