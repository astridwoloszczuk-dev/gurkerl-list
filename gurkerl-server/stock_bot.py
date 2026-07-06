#!/usr/bin/env python3
"""
stock_bot.py — Gurkerl auto-stock (SPEC: CODE/live/gurkerl-list/SPEC.md, 2026-07-06).

Learns the family's consumption RATES from Gurkerl delivered-order history and
proposes what runs out before the next order window, as tinted 'stock-bot' items
on the gurkerl-list. Astrid stays the curator; this only composes the draft.

Cron: Sat 18:00 (before the Sunday main order) + Wed 05:30 (before the Wed top-up).

Logic:
  • staples = products bought in ≥3 distinct orders in the last 90 days
  • rate    = qty bought / weeks in span (first→last purchase, min 2 weeks)
  • runout  = last delivery + (last qty ÷ rate)
  • propose when runout falls within HORIZON_DAYS of now
  • travel: all-day out-of-office calendar days in the horizon pause consumption
    (shift runout); ≥4 OOF days in the horizon → skip the whole run (away week)
  • idempotent: never proposes a name already open (uncompleted) on the list

  python3 stock_bot.py --dry    # print proposals + diagnostics, write nothing
  python3 stock_bot.py          # insert proposals
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server as srv  # reuse GurkerClient session/login + supabase client

sys.path.insert(0, os.path.expanduser('~/Code/nutrition-prefill'))
import nutrition_prefill as n  # ms_access() + graph() for the calendar

DRY = '--dry' in sys.argv
HISTORY_DAYS = 90
STAPLE_MIN_ORDERS = 3
HORIZON_DAYS = 7          # Sat run covers → Wed; Wed run covers → Sun; +3d buffer
STALE_DAYS = 14           # runout further back than this = they stopped buying it
OOF_SKIP_THRESHOLD = 4    # ≥4 out-of-office days in horizon = travel week, skip
HC_STOCKBOT = os.environ.get('HC_STOCKBOT', '')  # healthchecks UUID; empty = no-op


def hb(ok=True, msg=''):
    if not HC_STOCKBOT:
        return
    try:
        url = f'https://hc-ping.com/{HC_STOCKBOT}' + ('' if ok else '/fail')
        requests.post(url, data=(msg or '')[:500] or None, timeout=10)
    except Exception:
        pass


# ── order history ─────────────────────────────────────────────────────────────

DATE_KEYS = ('deliveredAt', 'deliveryDate', 'deliverySlotSince', 'orderTime', 'createdAt')
ISO_RX = re.compile(r'^\d{4}-\d{2}-\d{2}')


def order_date(order):
    """Best-effort delivery date from whatever field Gurkerl uses."""
    for k in DATE_KEYS:
        v = order.get(k)
        if isinstance(v, str) and ISO_RX.match(v):
            return date.fromisoformat(v[:10])
    slot = order.get('deliverySlot') or {}
    if isinstance(slot, dict):
        for v in slot.values():
            if isinstance(v, str) and ISO_RX.match(v):
                return date.fromisoformat(v[:10])
    for v in order.values():  # last resort: first ISO-dated string anywhere
        if isinstance(v, str) and ISO_RX.match(v):
            return date.fromisoformat(v[:10])
    return None


def product_qty(p):
    for k in ('amount', 'quantity', 'count'):
        v = p.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return 1.0


def fetch_orders(client, since):
    """All delivered orders since `since`, with items (list gives dates/ids,
    detail endpoint /api/v3/orders/{id} carries the items[])."""
    heads, offset = [], 0
    while True:
        resp = client.session.get(
            f'{srv.GURKERL_BASE}/api/v3/orders/delivered',
            params={'offset': str(offset), 'limit': '30'},
        )
        resp.raise_for_status()
        data = resp.json()
        orders = data if isinstance(data, list) else (data.get('data') or {}).get('orders', [])
        if not orders:
            break
        stop = False
        for o in orders:
            d = order_date(o)
            if d is None or not o.get('id'):
                continue
            if d < since:
                stop = True
                continue
            heads.append((d, o['id']))
        if stop or len(orders) < 30:
            break
        offset += 30
        time.sleep(0.3)

    out = []
    for d, oid in heads:
        try:
            resp = client.session.get(f'{srv.GURKERL_BASE}/api/v3/orders/{oid}')
            resp.raise_for_status()
            out.append((d, resp.json().get('items') or []))
        except Exception as ex:
            print(f'  order {oid} detail failed, skipping: {ex}')
        time.sleep(0.3)
    return out


def build_stats(dated_orders):
    """product name -> {orders:set(dates), qty_total, last_date, last_qty, typical_qty}."""
    stats = {}
    for d, items in dated_orders:
        for p in items:
            name = (p.get('name') or '').strip()
            if not name:
                continue
            q = product_qty(p)
            s = stats.setdefault(name, {'dates': set(), 'qty': 0.0, 'per_order': []})
            s['dates'].add(d)
            s['qty'] += q
            s['per_order'].append((d, q))
    for s in stats.values():
        s['per_order'].sort()
        s['last_date'], s['last_qty'] = s['per_order'][-1]
        qs = sorted(q for _, q in s['per_order'])
        s['typical_qty'] = qs[len(qs) // 2]
    return stats


# ── travel (calendar out-of-office) ──────────────────────────────────────────

def oof_days_in_horizon(today):
    try:
        access = n.ms_access()
        end = today + timedelta(days=HORIZON_DAYS)
        qs = ('startDateTime=' + f'{today}T00:00:00'
              + '&endDateTime=' + f'{end}T23:59:59'
              + '&$select=subject,start,end,isAllDay,showAs&$top=100')
        code, data = n.graph('GET', f'{n.GRAPH}/calendarView?{qs}', access)
        days = set()
        for e in (data.get('value', []) if code == 200 else []):
            if not e.get('isAllDay') or e.get('showAs') != 'oof':
                continue
            s = date.fromisoformat(e['start']['dateTime'][:10])
            t = date.fromisoformat(e['end']['dateTime'][:10])
            d = s
            while d < t:  # all-day events end at 00:00 the day after
                if today <= d <= end:
                    days.add(d)
                d += timedelta(days=1)
        return days
    except Exception as ex:
        print(f'calendar check failed (proceeding without travel adjustment): {ex}')
        return set()


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    today = date.today()
    client = srv.GurkerClient()
    client.ensure_logged_in()

    since = today - timedelta(days=HISTORY_DAYS)
    dated = fetch_orders(client, since)
    print(f'{len(dated)} delivered orders since {since}')
    if len(dated) < 3:
        print('Not enough order history to estimate rates — nothing proposed.')
        hb(True, 'insufficient history')
        return

    oof = oof_days_in_horizon(today)
    if len(oof) >= OOF_SKIP_THRESHOLD:
        print(f'Travel week ({len(oof)} out-of-office days in horizon) — run skipped.')
        hb(True, f'travel week, skipped ({len(oof)} OOF days)')
        return

    stats = build_stats(dated)
    existing = {
        (r.get('name') or '').strip().lower()
        for r in (srv.db.table('gurkerl_items').select('name')
                  .eq('completed', False).execute().data or [])
    }

    proposals = []
    for name, s in sorted(stats.items()):
        if len(s['dates']) < STAPLE_MIN_ORDERS:
            continue
        first = s['per_order'][0][0]
        span_weeks = max(((s['last_date'] - first).days) / 7.0, 2.0)
        qty_before_last = s['qty'] - s['last_qty']
        rate = qty_before_last / span_weeks if span_weeks and qty_before_last > 0 else s['qty'] / span_weeks
        if rate <= 0:
            continue
        runout = s['last_date'] + timedelta(days=(s['last_qty'] / rate) * 7)
        runout += timedelta(days=len(oof))  # consumption pauses while away
        if runout > today + timedelta(days=HORIZON_DAYS):
            continue
        if runout < today - timedelta(days=STALE_DAYS):
            continue  # long past runout and not repurchased → no longer a staple
        if name.strip().lower() in existing:
            continue
        proposals.append({
            'name': name,
            'quantity': max(1, round(s['typical_qty'])),
            'runout': runout.isoformat(),
            'rate_per_week': round(rate, 2),
            'orders': len(s['dates']),
            'last': s['last_date'].isoformat(),
        })

    if not proposals:
        print('Nothing runs out in the horizon — list untouched.')
        hb(True, 'no proposals needed')
        return

    print(f'\n{"item":<48}{"qty":>4}{"/wk":>6}{"last":>12}{"runout":>12}{"n":>3}')
    for p in proposals:
        print(f"{p['name'][:47]:<48}{p['quantity']:>4}{p['rate_per_week']:>6}{p['last']:>12}{p['runout']:>12}{p['orders']:>3}")

    if DRY:
        print(f'\n--dry: {len(proposals)} proposals, nothing inserted.')
        return

    for p in proposals:
        srv.db.table('gurkerl_items').insert({
            'name': p['name'],
            'quantity': p['quantity'],
            'added_by': 'stock-bot',
        }).execute()
    print(f'\nInserted {len(proposals)} stock-bot items onto the list.')
    hb(True, f'{len(proposals)} items proposed')


if __name__ == '__main__':
    try:
        main()
    except Exception as ex:
        hb(False, str(ex))
        raise
