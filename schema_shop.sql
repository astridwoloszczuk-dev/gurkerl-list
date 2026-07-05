-- Boys' shop (shop/ PWA) — run in Supabase SQL editor (family-apps project)

create table shop_items (
  id          uuid default gen_random_uuid() primary key,
  person      text not null,              -- Alex | Max
  title       text not null,
  url         text,                       -- product link (amazon / girav / …)
  price       numeric,                    -- EUR (the boy's entry; mum can correct)
  note        text,                       -- boy's "why this one"
  source      text default 'amazon',      -- amazon | girav | other | extern
  status      text default 'proposed',    -- proposed → approved → ordered → arrived | rejected
  feedback    text,                       -- mum's comment (esp. on reject)
  created_at  timestamptz default now(),
  decided_at  timestamptz,                -- when mum approved/rejected
  ordered_at  timestamptz                 -- when mum actually ordered (tally anchor)
);

create table shop_budgets (
  person       text primary key,
  monthly_eur  numeric                    -- null = no hard budget, tallies only
);

alter table shop_items   enable row level security;
alter table shop_budgets enable row level security;
create policy "Allow all for anon" on shop_items   for all using (true) with check (true);
create policy "Allow all for anon" on shop_budgets for all using (true) with check (true);
