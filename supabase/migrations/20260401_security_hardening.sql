-- AIEXAM Supabase security hardening migration
-- Target:
-- - Enable RLS on core tables
-- - Restrict user access to own rows
-- - Restrict system report access to admins
-- - Remove plaintext reset token storage
-- - Support a staged migration to Supabase Auth

begin;

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Admin registry and helper
-- ---------------------------------------------------------------------------

create table if not exists public.admin_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

alter table public.admin_users enable row level security;
revoke all on public.admin_users from anon, authenticated;

drop policy if exists "admin_users_self_read" on public.admin_users;
create policy "admin_users_self_read"
on public.admin_users
for select
using (auth.uid() = user_id);

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public, auth
as $$
  select exists (
    select 1
    from public.admin_users au
    where au.user_id = auth.uid()
  )
  or exists (
    select 1
    from public.users_pro up
    where up.user_id = auth.uid()
      and lower(coalesce(up.role, '')) = 'admin'
  );
$$;

revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to authenticated;

-- ---------------------------------------------------------------------------
-- Shared helper
-- ---------------------------------------------------------------------------

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- users_pro
-- ---------------------------------------------------------------------------

alter table public.users_pro
  add column if not exists user_id uuid references auth.users(id) on delete set null;

alter table public.users_pro
  add column if not exists created_at timestamptz not null default now();

alter table public.users_pro
  add column if not exists updated_at timestamptz not null default now();

create index if not exists users_pro_user_id_idx
  on public.users_pro(user_id);

create unique index if not exists users_pro_user_id_uidx
  on public.users_pro(user_id);

alter table public.users_pro enable row level security;
revoke all on public.users_pro from anon, authenticated;

grant select, insert, update, delete on public.users_pro to authenticated;

drop policy if exists "users_pro_select_own_or_admin" on public.users_pro;
create policy "users_pro_select_own_or_admin"
on public.users_pro
for select
using (user_id = auth.uid() or public.is_admin());

drop policy if exists "users_pro_insert_own_or_admin" on public.users_pro;
create policy "users_pro_insert_own_or_admin"
on public.users_pro
for insert
with check (user_id = auth.uid() or public.is_admin());

create or replace function public.normalize_users_pro_insert()
returns trigger
language plpgsql
as $$
begin
  if not public.is_admin() then
    if lower(coalesce(new.role, 'free')) = 'admin' then
      new.role := 'free';
    end if;
    new.points := coalesce(new.points, 0);
    new.usage_count := coalesce(new.usage_count, 0);
    new.commission_balance := coalesce(new.commission_balance, 0);
  end if;
  return new;
end;
$$;

drop trigger if exists trg_normalize_users_pro_insert on public.users_pro;
create trigger trg_normalize_users_pro_insert
before insert on public.users_pro
for each row
execute function public.normalize_users_pro_insert();

drop policy if exists "users_pro_update_own_or_admin" on public.users_pro;
create policy "users_pro_update_own_or_admin"
on public.users_pro
for update
using (user_id = auth.uid() or public.is_admin())
with check (user_id = auth.uid() or public.is_admin());

drop policy if exists "users_pro_delete_admin_only" on public.users_pro;
create policy "users_pro_delete_admin_only"
on public.users_pro
for delete
using (public.is_admin());

create or replace function public.block_sensitive_users_pro_changes()
returns trigger
language plpgsql
as $$
begin
  if not public.is_admin() then
    if new.user_id is distinct from old.user_id
       or new.username is distinct from old.username
       or new.password is distinct from old.password
       or new.role is distinct from old.role
       or new.points is distinct from old.points
       or new.usage_count is distinct from old.usage_count
       or new.commission_balance is distinct from old.commission_balance
       or new.referred_by is distinct from old.referred_by then
      raise exception 'insufficient privilege to modify sensitive profile fields';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_block_sensitive_users_pro_changes on public.users_pro;
create trigger trg_block_sensitive_users_pro_changes
before update on public.users_pro
for each row
execute function public.block_sensitive_users_pro_changes();

drop trigger if exists trg_users_pro_updated_at on public.users_pro;
create trigger trg_users_pro_updated_at
before update on public.users_pro
for each row
execute function public.touch_updated_at();

-- Optional profile bootstrap from Supabase Auth.
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  insert into public.users_pro (
    user_id,
    username,
    fullname,
    role,
    points,
    usage_count,
    commission_balance,
    referred_by,
    last_activity_at,
    created_at,
    updated_at
  )
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'username', split_part(coalesce(new.email, ''), '@', 1)),
    coalesce(new.raw_user_meta_data ->> 'fullname', ''),
    'free',
    0,
    0,
    0,
    null,
    now(),
    now(),
    now()
  )
  on conflict (user_id) do update
  set updated_at = now();
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_auth_user();

-- ---------------------------------------------------------------------------
-- exam_history
-- ---------------------------------------------------------------------------

alter table public.exam_history
  add column if not exists user_id uuid references auth.users(id) on delete set null;

alter table public.exam_history
  add column if not exists created_at timestamptz not null default now();

alter table public.exam_history
  add column if not exists updated_at timestamptz not null default now();

create index if not exists exam_history_user_id_created_at_idx
  on public.exam_history(user_id, created_at desc);

alter table public.exam_history enable row level security;
revoke all on public.exam_history from anon, authenticated;

grant select, insert, update, delete on public.exam_history to authenticated;

drop policy if exists "exam_history_select_own_or_admin" on public.exam_history;
create policy "exam_history_select_own_or_admin"
on public.exam_history
for select
using (user_id = auth.uid() or public.is_admin());

drop policy if exists "exam_history_insert_own_or_admin" on public.exam_history;
create policy "exam_history_insert_own_or_admin"
on public.exam_history
for insert
with check (user_id = auth.uid() or public.is_admin());

drop policy if exists "exam_history_update_own_or_admin" on public.exam_history;
create policy "exam_history_update_own_or_admin"
on public.exam_history
for update
using (user_id = auth.uid() or public.is_admin())
with check (user_id = auth.uid() or public.is_admin());

drop policy if exists "exam_history_delete_own_or_admin" on public.exam_history;
create policy "exam_history_delete_own_or_admin"
on public.exam_history
for delete
using (user_id = auth.uid() or public.is_admin());

drop trigger if exists trg_exam_history_updated_at on public.exam_history;
create trigger trg_exam_history_updated_at
before update on public.exam_history
for each row
execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- usage_events
-- ---------------------------------------------------------------------------

alter table public.usage_events
  add column if not exists user_id uuid references auth.users(id) on delete set null;

alter table public.usage_events
  add column if not exists created_at timestamptz not null default now();

create index if not exists usage_events_user_id_created_at_idx
  on public.usage_events(user_id, created_at desc);

alter table public.usage_events enable row level security;
revoke all on public.usage_events from anon, authenticated;

grant select, insert on public.usage_events to authenticated;

drop policy if exists "usage_events_select_own_or_admin" on public.usage_events;
create policy "usage_events_select_own_or_admin"
on public.usage_events
for select
using (user_id = auth.uid() or public.is_admin());

drop policy if exists "usage_events_insert_own_or_admin" on public.usage_events;
create policy "usage_events_insert_own_or_admin"
on public.usage_events
for insert
with check (user_id = auth.uid() or public.is_admin());

drop policy if exists "usage_events_update_admin_only" on public.usage_events;
create policy "usage_events_update_admin_only"
on public.usage_events
for update
using (public.is_admin())
with check (public.is_admin());

drop policy if exists "usage_events_delete_admin_only" on public.usage_events;
create policy "usage_events_delete_admin_only"
on public.usage_events
for delete
using (public.is_admin());

-- ---------------------------------------------------------------------------
-- reset_tokens
-- ---------------------------------------------------------------------------

alter table public.reset_tokens
  add column if not exists user_id uuid references auth.users(id) on delete set null;

alter table public.reset_tokens
  add column if not exists token_hash text;

alter table public.reset_tokens
  add column if not exists expires_at timestamptz;

alter table public.reset_tokens
  add column if not exists used boolean not null default false;

alter table public.reset_tokens
  add column if not exists created_at timestamptz not null default now();

-- Keep the legacy expired_at column during migration if it exists.
-- New code should use expires_at only.
update public.reset_tokens
   set expires_at = coalesce(expires_at, expired_at, now() + interval '10 minutes')
 where expires_at is null;

create index if not exists reset_tokens_user_id_expires_idx
  on public.reset_tokens(user_id, expires_at desc);

create index if not exists reset_tokens_username_expires_idx
  on public.reset_tokens(username, expires_at desc);

alter table public.reset_tokens enable row level security;
revoke all on public.reset_tokens from anon, authenticated;

-- Direct table access stays admin-only.
grant select, insert, update, delete on public.reset_tokens to authenticated;

drop policy if exists "reset_tokens_admin_only" on public.reset_tokens;
create policy "reset_tokens_admin_only"
on public.reset_tokens
for all
using (public.is_admin())
with check (public.is_admin());

create or replace function public.hash_reset_token(p_token text)
returns text
language sql
immutable
as $$
  select encode(digest(coalesce(p_token, ''), 'sha256'), 'hex');
$$;

create or replace function public.create_reset_token(p_user_id uuid, p_username text)
returns text
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  v_token text := lpad((floor(random() * 1000000))::int::text, 6, '0');
begin
  insert into public.reset_tokens (
    user_id,
    username,
    token_hash,
    expires_at,
    used
  )
  values (
    p_user_id,
    p_username,
    public.hash_reset_token(v_token),
    now() + interval '10 minutes',
    false
  );
  return v_token;
end;
$$;

create or replace function public.verify_reset_token(p_user_id uuid, p_username text, p_token text)
returns boolean
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  return exists (
    select 1
    from public.reset_tokens rt
    where rt.user_id = p_user_id
      and rt.username = p_username
      and rt.used = false
      and coalesce(rt.expires_at, rt.expired_at) >= now()
      and rt.token_hash = public.hash_reset_token(p_token)
  );
end;
$$;

create or replace function public.consume_reset_token(p_user_id uuid, p_username text, p_token text)
returns void
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  update public.reset_tokens
     set used = true
   where user_id = p_user_id
     and username = p_username
     and used = false
     and coalesce(expires_at, expired_at) >= now()
     and token_hash = public.hash_reset_token(p_token);
end;
$$;

grant execute on function public.hash_reset_token(text) to authenticated;
grant execute on function public.create_reset_token(uuid, text) to authenticated;
grant execute on function public.verify_reset_token(uuid, text, text) to authenticated;
grant execute on function public.consume_reset_token(uuid, text, text) to authenticated;

-- ---------------------------------------------------------------------------
-- Optional cleanup notes
-- ---------------------------------------------------------------------------
-- After the app fully migrates to Supabase Auth, consider:
-- - backfilling users_pro.user_id from auth.users
-- - setting users_pro.user_id, exam_history.user_id, usage_events.user_id to NOT NULL
-- - dropping legacy plaintext password / expired_at / token columns if no longer used
-- - reducing direct table grants further if the app switches to RPC-only writes

commit;
