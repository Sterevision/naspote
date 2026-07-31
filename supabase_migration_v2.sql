-- =========================================================
--  НА СПОТЕ — миграция v2
--  Добавляет: аккаунты организаций, ручную расстановку меток,
--  привязку метки к конкретному заведению (важно для зданий,
--  где несколько заведений на одном адресе).
--
--  Выполните в Supabase Dashboard → SQL Editor ПОСЛЕ того как
--  уже выполнили supabase_schema.sql (это добавочная миграция,
--  таблицы не пересоздаются, данные не теряются).
-- =========================================================

-- ---------- profiles: тип аккаунта + поля организации ----------
alter table public.profiles
  add column if not exists account_type text not null default 'person'
    check (account_type in ('person', 'organization')),
  add column if not exists category text,          -- "Бар", "Кофейня", "Клуб", "Коворкинг" и т.д.
  add column if not exists address text,            -- адрес заведения
  add column if not exists cover_url text,           -- обложка страницы заведения
  add column if not exists lat double precision,     -- координаты заведения (для поиска рядом)
  add column if not exists lng double precision,
  add column if not exists is_verified boolean not null default false;

-- ---------- spots: способ расстановки + привязка к заведению ----------
alter table public.spots
  add column if not exists placement_type text not null default 'geo'
    check (placement_type in ('geo', 'manual')),
  add column if not exists organization_id uuid references public.profiles(id) on delete set null;

-- индекс для быстрого поиска "кто отмечался у этого заведения"
create index if not exists idx_spots_organization_id on public.spots(organization_id);

-- индекс для поиска организаций по геолокации (грубый, без PostGIS)
create index if not exists idx_profiles_org_location on public.profiles(lat, lng)
  where account_type = 'organization';
