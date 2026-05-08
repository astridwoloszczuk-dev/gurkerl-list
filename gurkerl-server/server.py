#!/usr/bin/env python3
"""
Gurkerl cart server — polls Supabase for cart requests, matches items against
Gurkerl.at, and adds confirmed selections to the basket.

Env vars (in /root/gurkerl-list/.env):
  SUPABASE_URL, SUPABASE_SERVICE_KEY, GURKERL_EMAIL, GURKERL_PASSWORD
"""
import os, sys, time, json, logging
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SUPABASE_URL      = os.environ['SUPABASE_URL']
SUPABASE_KEY      = os.environ['SUPABASE_SERVICE_KEY']
GURKERL_EMAIL     = os.environ['GURKERL_EMAIL']
GURKERL_PASSWORD  = os.environ['GURKERL_PASSWORD']
GURKERL_BASE      = 'https://www.gurkerl.at'
POLL_INTERVAL     = 5   # seconds between polls
SEARCH_LIMIT      = 6   # candidates returned per item

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

db = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Gurkerl API client ────────────────────────────────────────────────────────

class GurkerClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
            ),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8',
            'Content-Type': 'application/json',
            'Origin': GURKERL_BASE,
            'Referer': GURKERL_BASE + '/',
        })
        self.frequent_ids: set = set()
        self._logged_in = False
        self._debug_logged = False  # log raw response once for debugging

    def login(self):
        for endpoint in [
            '/services/frontend-service/login',
            '/services/frontend-service/v2/login',
        ]:
            resp = self.session.post(f'{GURKERL_BASE}{endpoint}', json={
                'email': GURKERL_EMAIL,
                'password': GURKERL_PASSWORD,
            })
            log.info(f'Login {endpoint}: HTTP {resp.status_code} — {resp.text[:400]}')
            data = resp.json()
            user = (data.get('data') or {}).get('user')
            if user:
                log.info(f'Authenticated as: {user}')
                self._logged_in = True
                return
        raise RuntimeError(f'Login failed — user is null after all attempts. Check GURKERL_EMAIL/PASSWORD in .env')

    def _check_auth(self):
        for path in ['/services/frontend-service/user', '/services/frontend-service/profile', '/api/v3/user']:
            try:
                resp = self.session.get(f'{GURKERL_BASE}{path}')
                log.info(f'AUTH CHECK {path} → {resp.status_code}: {resp.text[:200]}')
                if resp.ok:
                    break
            except Exception as e:
                log.info(f'AUTH CHECK {path} → ERROR: {e}')

    def ensure_logged_in(self):
        if not self._logged_in:
            self.login()
            self._check_auth()
            self._load_frequent_items()
            self.discover_list_endpoints()

    def _load_frequent_items(self):
        try:
            resp = self.session.get(
                f'{GURKERL_BASE}/api/v3/orders/delivered',
                params={'offset': '0', 'limit': '30'},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                orders = data
            else:
                orders = (data.get('data') or {}).get('orders', [])
            counts: dict = {}
            for order in orders:
                for p in order.get('products', []):
                    pid = p.get('productId')
                    if pid:
                        counts[pid] = counts.get(pid, 0) + 1
            self.frequent_ids = set(counts.keys())
            log.info(f'Order history: {len(self.frequent_ids)} known product IDs')
        except Exception as e:
            log.warning(f'Could not load order history (fine for new accounts): {e}')
            self.frequent_ids = set()

    def search(self, query: str) -> dict:
        resp = self.session.get(
            f'{GURKERL_BASE}/services/frontend-service/search-metadata',
            params={
                'search': query,
                'offset': '0',
                'limit': str(SEARCH_LIMIT),
                'companyId': '1',
                'filterData': json.dumps({'filters': []}),
                'canCorrect': 'true',
            },
        )
        resp.raise_for_status()
        result = resp.json()
        if not self._debug_logged:
            log.info(f'RAW SEARCH RESPONSE: {json.dumps(result)[:1200]}')
            self._debug_logged = True
        return result

    def _extract_products(self, search_response) -> list:
        # Gurkerl.at may return a plain list or a wrapped dict
        if isinstance(search_response, list):
            raw = search_response
            if raw:
                log.info(f'RAW PRODUCT FIELDS (first item): {list(raw[0].keys())}')
        else:
            data = search_response.get('data') or {}
            if isinstance(data, list):
                raw = data
            else:
                pl = data.get('productList')
                raw = (
                    data.get('products')
                    or (pl if isinstance(pl, list) else (pl or {}).get('products'))
                    or (data.get('hits') or {}).get('hits')
                    or data.get('items')
                    or []
                ) or []
        if not raw:
            top = list(search_response.keys()) if isinstance(search_response, dict) else type(search_response)
            log.warning(f'No products found. Response type/keys: {top}')

        products = []
        for p in raw:
            pid = p.get('productId') or p.get('id')
            if not pid:
                continue
            price_obj = p.get('price', {})
            if isinstance(price_obj, dict):
                price_str = f"{price_obj.get('full', '')} {price_obj.get('currency', '€')}".strip()
            else:
                price_str = str(price_obj)

            is_frequent = int(pid) in self.frequent_ids if self.frequent_ids else False
            products.append({
                'product_id': str(pid),
                'name': p.get('productName') or p.get('name') or '',
                'brand': p.get('brand') or '',
                'amount': p.get('textualAmount') or p.get('amount') or '',
                'price': price_str,
                'is_frequent': is_frequent,
            })

        # Frequent (previously ordered) items float to the top
        products.sort(key=lambda x: (0 if x['is_frequent'] else 1))
        return products[:5]

    def discover_list_endpoints(self):
        """Probe candidate endpoints to find the right lists API."""
        candidates = [
            ('GET',  '/api/v3/shoppingList'),
            ('GET',  '/api/v3/shopping-lists'),
            ('GET',  '/api/v3/lists'),
            ('GET',  '/services/frontend-service/v2/lists'),
            ('GET',  '/services/frontend-service/shopping-lists'),
        ]
        for method, path in candidates:
            try:
                resp = self.session.request(method, f'{GURKERL_BASE}{path}')
                log.info(f'PROBE {method} {path} → {resp.status_code}: {resp.text[:200]}')
            except Exception as e:
                log.info(f'PROBE {method} {path} → ERROR: {e}')

    def add_to_cart(self, product_id: str, quantity: int = 1):
        resp = self.session.post(
            f'{GURKERL_BASE}/services/frontend-service/v2/cart',
            json={'productId': int(product_id), 'quantity': quantity},
        )
        log.info(f'add_to_cart {product_id}: HTTP {resp.status_code} — {resp.text[:300]}')
        resp.raise_for_status()

    def read_cart(self):
        resp = self.session.get(f'{GURKERL_BASE}/services/frontend-service/v2/cart')
        log.info(f'read_cart: HTTP {resp.status_code} — {resp.text[:600]}')
        return resp.json() if resp.ok else {}


gurkerl = GurkerClient()


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def set_status(request_id: str, status: str, **extra):
    db.table('gurkerl_cart_requests').update(
        {'status': status, 'updated_at': now_iso(), **extra}
    ).eq('id', request_id).execute()

def fail(request_id: str, msg: str):
    log.error(f'Request {request_id} failed: {msg}')
    set_status(request_id, 'failed', error=msg)


# ── Request processors ────────────────────────────────────────────────────────

def process_pending(req: dict):
    request_id = req['id']
    log.info(f'[{request_id[:8]}] Matching items for {req["requested_by"]}')
    set_status(request_id, 'matching')

    try:
        gurkerl.ensure_logged_in()

        items_resp = (
            db.table('gurkerl_items')
            .select('id, name')
            .eq('completed', False)
            .order('created_at')
            .execute()
        )
        items = items_resp.data or []
        if not items:
            fail(request_id, 'Nothing on the list!')
            return

        matches = []
        for item in items:
            try:
                search_resp = gurkerl.search(item['name'])
                candidates = gurkerl._extract_products(search_resp)
            except Exception as e:
                log.warning(f'Search failed for "{item["name"]}": {e}')
                candidates = []

            matches.append({
                'item_id': item['id'],
                'item_name': item['name'],
                'candidates': candidates,
                'selected_product_id': candidates[0]['product_id'] if candidates else None,
            })
            time.sleep(0.25)  # be polite to Gurkerl's servers

        set_status(request_id, 'awaiting_confirmation', matches=matches)
        log.info(f'[{request_id[:8]}] Matched {len(matches)} items — awaiting confirmation')

    except Exception as e:
        gurkerl._logged_in = False
        gurkerl._debug_logged = False
        fail(request_id, str(e))


def process_confirmed(req: dict):
    request_id = req['id']
    matches = req.get('matches') or []
    log.info(f'[{request_id[:8]}] Adding {len(matches)} items to cart')
    set_status(request_id, 'adding')

    try:
        gurkerl.ensure_logged_in()

        added = []
        for match in matches:
            product_id = match.get('selected_product_id')
            if not product_id:
                log.info(f'  Skipping "{match["item_name"]}" — no product selected')
                continue

            gurkerl.add_to_cart(product_id)
            time.sleep(0.3)

            item_id = match.get('item_id')
            if item_id:
                db.table('gurkerl_items').update({
                    'completed': True,
                    'completed_at': now_iso(),
                    'completed_by': 'Gurkerl',
                }).eq('id', item_id).execute()

            added.append(match['item_name'])
            log.info(f'  ✓ {match["item_name"]}')

        gurkerl.read_cart()
        set_status(request_id, 'done')
        log.info(f'[{request_id[:8]}] Done — {len(added)} item(s) added to basket')

    except Exception as e:
        gurkerl._logged_in = False
        gurkerl._debug_logged = False
        fail(request_id, str(e))


# ── Poll loop ─────────────────────────────────────────────────────────────────

def poll_loop():
    log.info(f'Gurkerl cart server started (polling every {POLL_INTERVAL}s)')
    while True:
        try:
            pending = (
                db.table('gurkerl_cart_requests')
                .select('*')
                .eq('status', 'pending')
                .execute()
            )
            for req in pending.data or []:
                process_pending(req)

            confirmed = (
                db.table('gurkerl_cart_requests')
                .select('*')
                .eq('status', 'confirmed')
                .execute()
            )
            for req in confirmed.data or []:
                process_confirmed(req)

        except Exception as e:
            log.error(f'Poll error: {e}')

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    poll_loop()
