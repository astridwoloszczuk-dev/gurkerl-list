-- Run in Supabase SQL editor (family-apps project)

create table gurkerl_cart_requests (
  id           uuid default gen_random_uuid() primary key,
  status       text default 'pending',
  -- pending → matching → awaiting_confirmation → confirmed → adding → done | failed
  requested_by text not null,
  matches      jsonb,
  -- [{item_id, item_name, candidates: [{product_id, name, brand, amount, price, is_frequent}], selected_product_id}]
  error        text,
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

alter table gurkerl_cart_requests enable row level security;
create policy "Allow all for anon" on gurkerl_cart_requests for all using (true) with check (true);

alter publication supabase_realtime add table gurkerl_cart_requests;
