-- family-days: voting + history tables (cloud family-apps Supabase)
-- Run in the Supabase SQL editor (same click as schema_shop.sql was).
-- SPEC: CODE/building/family-days/SPEC.md

create table if not exists fd_plans (
  id uuid default gen_random_uuid() primary key,
  flavour text not null check (flavour in ('day','night')),
  title text not null,
  event_date date,
  summary text,
  est_cost_pp numeric,
  status text default 'voting',        -- voting | chosen | done | dropped
  created_at timestamptz default now()
);

create table if not exists fd_votes (
  id uuid default gen_random_uuid() primary key,
  plan_id uuid references fd_plans(id) on delete cascade,
  member text not null,                -- display name; roster enforced in app
  kind text not null check (kind in ('up','veto','wish')),
  created_at timestamptz default now(),
  unique (plan_id, member, kind)
);

create table if not exists fd_quota (
  member text primary key,
  vetoes_left int default 1,
  wishes_left int default 1,
  month text                            -- 'YYYY-MM' the quota applies to
);

create table if not exists fd_history (
  id uuid default gen_random_uuid() primary key,
  flavour text not null,
  event_date date not null,
  title text not null,
  rating numeric,                       -- family average 1-5
  notes text,
  created_at timestamptz default now()
);

-- Anon access (house pattern: no logins, RLS wide-open like gurkerl/todo)
alter table fd_plans   enable row level security;
alter table fd_votes   enable row level security;
alter table fd_quota   enable row level security;
alter table fd_history enable row level security;
create policy "anon all" on fd_plans   for all using (true) with check (true);
create policy "anon all" on fd_votes   for all using (true) with check (true);
create policy "anon all" on fd_quota   for all using (true) with check (true);
create policy "anon all" on fd_history for all using (true) with check (true);

alter publication supabase_realtime add table fd_plans;
alter publication supabase_realtime add table fd_votes;

-- NOTE: date-night plans are NEVER inserted here (Niko-surprise rule is
-- enforced server-side in planner.py — only flavour='day' rows are pushed).
