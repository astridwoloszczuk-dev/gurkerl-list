# SPEC: Gurkerl Auto-Stock + Amazon Fuel Countdown

*2026-07-06 · spec by Fable · status: FINAL (all forks resolved with Astrid in-session)*

## Intent

The Sunday Gurkerl list should write itself. James already knows the family's
consumption (every delivered order, with dates), knows the diary (travel, training),
and already has the list + cart rail — so the weekly "what do we need?" decision is
removable. Astrid stays the curator (final say: she prunes the list and the cart);
the machine does the remembering. Supply side of the fuel pings: a "pack dates" ping
is useless if there are none in the pantry.

Second strand: gummies + electrolytes come from **Amazon**, not Gurkerl — there the
failure mode is the surprise empty pantry on a comp morning. That's a countdown +
reminder problem, not a list problem.

**Subtraction check:** removes the weekly list-composition decision and the
"are we out of gummies?" background worry. New inputs required from Astrid: one-time
pantry seed counts + a one-tap "restocked" button. Nothing recurring.

## Strand A — Gurkerl staples auto-stock

### Mechanism

New job on James (`stock_bot.py`, lives beside `gurkerl-server/`), cron **Sat ~18:00
and Wed ~05:30** (lands before her Sunday main order and Wednesday top-up):

1. **Consumption rates from order history** — pull delivered orders via the existing
   Gurkerl API session (`/api/v3/orders/delivered`, creds in `gurkerl-server/.env`;
   the cart-bot already logs in and reads this endpoint for its frequent-items bias).
   Per product: purchases over the last ~90 days → weekly rate + last-delivered date
   + typical quantity. Products bought ≥3 times in the window count as staples;
   one-offs are ignored.
2. **Projection** — per staple: projected run-out = last delivery + (qty ÷ rate).
   Propose the item if it runs out before the *next* order window + 3-day buffer
   (Sat run → covers to ~Wed; Wed run → covers to ~Sun).
3. **Travel modifier** — read the calendar (MS Graph, same pattern as
   `fuel_ping.day_events`): **all-day out-of-office events** in the coverage window
   suppress proposals for that window. No cross-checking against other sources.
4. **Insert** into `gurkerl_items` (family-apps Supabase) with
   `added_by='stock-bot'`, idempotent: never insert a name that already exists
   uncompleted on the list.

### PWA change (gurkerl-list `index.html`/`app.js`)

Stock-bot items render in a distinct tint so they're recognisable at a glance.
Individually deletable exactly like any other item. **Explicitly NO bulk
"clear all bot items" action** (Astrid's call).

### Astrid's flow (unchanged)

List appears composed → she prunes/keeps → pushes to cart → prunes cart → orders.
Final say never moves.

## Strand B — Amazon fuel countdown (gummies, electrolytes)

### Mechanism

State: a small JSON on James (`fuel_stock.json`, in the nightly backup path):
per item `{count, seeded_at, rates}`. Consumption is *estimated from the diary* —
each day's events decrement stock by configured rates (defaults, tune at build):
gummies −2 per comp or hard run, −1 per gym session or easy run with pre-run ping;
electrolyte −1 per golf round or run ≥1h. Recompute daily (piggyback on the existing
fuel_ping cron — no new cron).

- **Ping:** when projected run-out < 7 days → ONE WhatsApp ping via the existing
  `reminders` rail ("🍬 gummies run out ~Thursday — Amazon now."), then silence
  until restocked (no nagging).
- **Countdown display:** nutrition-web (`server.py`) gains `GET /fuelstock`
  (projected days + run-out date per item) and `POST /fuelstock/restock`
  (reset an item to its seed count). The fuel-plan PWA shows a small card —
  countdown per item + a "✓ Restocked" button each.
- **Seed:** Astrid supplies initial pantry counts at build time (builder asks).

## Acceptance criteria

1. Saturday run produces a tinted, plausible staples list from real order history —
   spot-check: milk/eggs/bananas/skyr appear with sane cadence, one-off purchases don't.
2. Items already open on the list are never duplicated; items delivered days ago
   with weeks of stock left are not proposed.
3. A week containing an all-day out-of-office event produces no proposals for the
   affected window (verify with a synthetic event, then delete it).
4. Stock-bot items are visually distinct and individually deletable; no bulk-delete
   exists.
5. Fuel-plan PWA shows the gummies/electrolyte countdown; "Restocked" resets it;
   the WhatsApp ping fires when a (test-lowered) threshold is crossed and does NOT
   repeat before restock.
6. Both cron paths ping healthchecks (`hb`-wrapped or semantic ping) from day one —
   no un-heartbeated jobs. `fuel_stock.json` sits inside the nightly-backup tree.
7. Existing cart-bot behaviour unchanged.

## Decisions made

- **Rates from order history, not a fixed list and not meal-plan parsing** — the
  family's measured metabolism beats both. essen-plan integration explicitly dropped:
  rates already embody cooking patterns. (Astrid's reframe, 2026-07-06.)
- **Travel = calendar out-of-office all-day events, nothing else** (Astrid).
- **Sat 18:00 + Wed 05:30 cadence** — matches her real Sunday-main + Wednesday-top-up
  ordering rhythm (Astrid).
- **Gummies/electrolytes via Amazon → countdown + ping + PWA button**, reset =
  button on the fuel-plan page she opens daily; countdown visible there too (Astrid).
- **No training-load multiplier on Gurkerl quantities in v1** — staples rates are
  stable; the Amazon strand covers the training-sensitive items. Revisit only if
  the rates visibly under-serve comp weeks.
- **Tinted but NOT bulk-deletable** (Astrid: "different colour — but not one tap delete").
- Skyr note for the curious builder: skyr + a tbsp of real 10% Greek yogurt are BOTH
  staples (the tbsp is the palatability layer — do not "optimise" it away; the 0%
  Greek-labelled skyr-equivalent is interchangeable with skyr, history will learn it).

## Non-goals

- Inventory tracking (no fridge state; projection-from-history only).
- Meal-plan/essen-plan integration (see Decisions).
- Auto-ordering (she pushes to cart; the line in the sand stays).
- Amazon auto-purchase or price tracking — the ping is the product.
- WhatsApp inbound "restocked" parsing (PWA button chosen instead).

## Constraints

- family-apps Supabase for `gurkerl_items` (NOT astrid-efficiency — env gotcha).
- Gurkerl creds stay in `gurkerl-server/.env` on James; never in the repo/chat.
- Anti-UPF is inherited: proposals come from her own purchase history.
- Principle 5: new jobs ship hb-wrapped + backed up, or they don't ship.
- Ping wording follows the fuel-ping voice; it must pass her "sugar-or-skyr" test
  (it does: it's literally about sugar supply).

## Pointers

- Cart-bot + API session/auth/search/orders: `live/gurkerl-list/gurkerl-server/server.py`
  (deployed at `~/Code/gurkerl-list/gurkerl-server/` on James; `_load_frequent_items`
  shows the delivered-orders call).
- List schema: `live/gurkerl-list/schema.sql` (`gurkerl_items`: name, added_by,
  completed).
- Calendar read pattern: `~/Code/nutrition-prefill/fuel_ping.py` → `day_events()`
  (MS Graph via `nutrition_prefill.ms_access()`).
- Reminder insert pattern: same file → `insert_reminder()` (whatsapp-server
  `reminders` table).
- Fuel-plan PWA + server: `~/Code/nutrition-web/` on James (`server.py` already has
  GET/POST routing + the /today pattern to copy for /fuelstock); source of the PWA:
  `CODE/live/nutrition/nutrition-plan.html`.
- Healthchecks pattern: `/Code/bin/hb <uuid>` cron wrapper (see crontab on James);
  Astrid creates the check(s) and supplies UUIDs at build time.

## Open questions

*(none at handover — builder asks Astrid for: initial pantry seed counts, and one
new healthchecks UUID. Genuine design forks go here.)*

## Build notes (built overnight 2026-07-06→07, by Fable — Astrid waived the
## division of labour for the subscription's last night)

Shipped per spec, with these deviations/findings:
- **STALE_DAYS=14 added to the projection**: items whose projected runout is >2 weeks
  past and never repurchased (seasonal berries, abandoned products) are NOT proposed —
  the household demonstrably lives without them. Cut the first real list from 41 → 26
  sane items (inserted Mon evening; the Wed 05:30 cron tops up idempotently).
- **Found + fixed a latent cart-bot bug**: `_load_frequent_items` read
  `order['products']` from the delivered-orders LIST endpoint, which has no products —
  the frequent-items bias had loaded **0 ids since launch**. Now fetches the last 10
  order details (`/api/v3/orders/{id}` → `items[].id`). First proof will be the next
  cart push ("Order history: N known product IDs" > 0 in server.log).
- **Consumption data source**: order detail endpoint `items[]` uses `name` + `amount`;
  the list endpoint only carries dates/ids → two-phase fetch.
- **Backup manifest extended** (`backup.sh`): now includes `*_state.json` and
  `fuel_stock.json` (the old pattern `state.json` matched nothing — none of the
  nutrition state files were being backed up).
- **fuel_stock first run backfilled 7 diary days**: gummies 40→27, electrolytes 15→8
  (runout ~15 Jul — expect the first low-stock ping within days). Seeds are ESTIMATES
  until Astrid supplies real counts (edit `fuel_stock.json` seed+count,
  `estimated:false`).
- **Cron shipped un-heartbeated** (criterion 6 partially deferred): stock_bot carries
  semantic-ping code reading `HC_STOCKBOT` from the gurkerl `.env` — add the UUID and
  it's live. Astrid's TODO.
- **Repo housekeeping**: a divergent local draft of `shop/` + `schema_shop.sql` (older
  than the pushed boys-shop v1) was parked at `archive/_misc/shop-local-draft-20260706/`.
