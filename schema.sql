-- Run this in your Supabase project's SQL editor

create table gurkerl_items (
  id uuid default gen_random_uuid() primary key,
  name text not null,
  added_by text,
  created_at timestamptz default now(),
  completed boolean default false,
  completed_at timestamptz,
  completed_by text
);

-- Allow anonymous read/write (no login required for MVP)
alter table gurkerl_items enable row level security;
create policy "Allow all for anon" on gurkerl_items for all using (true) with check (true);

-- Enable real-time updates
alter publication supabase_realtime add table gurkerl_items;
