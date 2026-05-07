// ── Config ──────────────────────────────────────────────────────────────────
const SUPABASE_URL  = 'https://mezayharkjyvnnhvdlww.supabase.co';
const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lemF5aGFya2p5dm5uaHZkbHd3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwOTE2ODQsImV4cCI6MjA5MTY2NzY4NH0.GlyIlgobMa0lVjEhH59-Zu1mt3f_usAipFNsg0bJSqE';

// ── Supabase client (loaded via CDN in index.html) ──────────────────────────
const { createClient } = supabase;
const db = createClient(SUPABASE_URL, SUPABASE_ANON);

// ── State ────────────────────────────────────────────────────────────────────
let currentUser = localStorage.getItem('gurkerl_user') || null;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const listEl      = document.getElementById('item-list');
const inputEl     = document.getElementById('item-input');
const addBtn      = document.getElementById('add-btn');
const userBadge   = document.getElementById('user-badge');
const userModal   = document.getElementById('user-modal');
const userNameEl  = document.getElementById('user-name-input');
const userSaveBtn = document.getElementById('user-save-btn');
const emptyState  = document.getElementById('empty-state');

// ── Gurkerl cart config & DOM refs ───────────────────────────────────────────
const CART_USERS   = ['Astrid', 'Niko'];
const cartBtn      = document.getElementById('cart-btn');
const cartModal    = document.getElementById('cart-modal');
const cartStateEls = {
  loading: document.getElementById('cart-loading'),
  matches: document.getElementById('cart-matches'),
  adding:  document.getElementById('cart-adding'),
  done:    document.getElementById('cart-done'),
  error:   document.getElementById('cart-error'),
};

// ── User setup ───────────────────────────────────────────────────────────────
function showUserModal() {
  userModal.classList.remove('hidden');
  userNameEl.focus();
}

function saveUser() {
  const name = userNameEl.value.trim();
  if (!name) return;
  currentUser = name;
  localStorage.setItem('gurkerl_user', name);
  userModal.classList.add('hidden');
  userBadge.textContent = name;
  updateCartButton();
}

userSaveBtn.addEventListener('click', saveUser);
userNameEl.addEventListener('keydown', e => e.key === 'Enter' && saveUser());
userBadge.addEventListener('click', () => {
  userNameEl.value = currentUser || '';
  showUserModal();
});

// ── Time formatting ──────────────────────────────────────────────────────────
function timeAgo(isoString) {
  const diff = (Date.now() - new Date(isoString)) / 1000;
  if (diff < 60)  return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── Render ───────────────────────────────────────────────────────────────────
function renderItem(item) {
  const existing = document.getElementById(`item-${item.id}`);
  if (existing) { existing.remove(); }

  const li = document.createElement('li');
  li.id = `item-${item.id}`;
  li.className = 'item' + (item.completed ? ' completed' : '');
  li.innerHTML = `
    <button class="check-btn" aria-label="Mark complete" data-id="${item.id}" data-done="${item.completed}">
      ${item.completed
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
        : ''}
    </button>
    <div class="item-body">
      <span class="item-name">${escapeHtml(item.name)}</span>
      <span class="item-meta">${escapeHtml(item.added_by || '?')} · ${timeAgo(item.created_at)}</span>
    </div>
    <button class="delete-btn" aria-label="Delete" data-id="${item.id}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  `;
  listEl.appendChild(li);
  updateEmpty();
}

function removeItem(id) {
  document.getElementById(`item-${id}`)?.remove();
  updateEmpty();
}

function updateEmpty() {
  emptyState.classList.toggle('hidden', listEl.children.length > 0);
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Load items ────────────────────────────────────────────────────────────────
async function loadItems() {
  const { data, error } = await db
    .from('gurkerl_items')
    .select('*')
    .eq('completed', false)
    .order('created_at', { ascending: true });

  if (error) { console.error(error); return; }
  listEl.innerHTML = '';
  data.forEach(renderItem);
}

// ── Real-time subscription ────────────────────────────────────────────────────
db.channel('gurkerl_items')
  .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'gurkerl_items' }, ({ new: item }) => {
    if (!item.completed) renderItem(item);
  })
  .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'gurkerl_items' }, ({ new: item }) => {
    if (item.completed) {
      removeItem(item.id);
    } else {
      renderItem(item);
    }
  })
  .on('postgres_changes', { event: 'DELETE', schema: 'public', table: 'gurkerl_items' }, ({ old: item }) => {
    removeItem(item.id);
  })
  .subscribe();

// ── Add item ─────────────────────────────────────────────────────────────────
async function addItem() {
  if (!currentUser) { showUserModal(); return; }
  const name = inputEl.value.trim();
  if (!name) return;
  inputEl.value = '';
  inputEl.focus();

  const { error } = await db.from('gurkerl_items').insert({ name, added_by: currentUser });
  if (error) { console.error(error); inputEl.value = name; }
}

addBtn.addEventListener('click', addItem);
inputEl.addEventListener('keydown', e => e.key === 'Enter' && addItem());

// ── Voice input ───────────────────────────────────────────────────────────────
const micBtn = document.getElementById('mic-btn');
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (!SpeechRecognition) {
  micBtn.style.display = 'none';
} else {
  const recognition = new SpeechRecognition();
  recognition.lang = 'de-AT';
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  let listening = false;

  micBtn.addEventListener('click', () => {
    if (listening) { recognition.stop(); return; }
    recognition.start();
  });

  recognition.addEventListener('start', () => {
    listening = true;
    micBtn.classList.add('listening');
    inputEl.placeholder = 'Listening…';
  });

  recognition.addEventListener('result', e => {
    const transcript = Array.from(e.results)
      .map(r => r[0].transcript).join('');
    inputEl.value = transcript;
    if (e.results[e.results.length - 1].isFinal) {
      recognition.stop();
      addItem();
    }
  });

  recognition.addEventListener('end', () => {
    listening = false;
    micBtn.classList.remove('listening');
    inputEl.placeholder = 'Add item…';
  });

  recognition.addEventListener('error', e => {
    console.error('Speech error', e.error);
    listening = false;
    micBtn.classList.remove('listening');
    inputEl.placeholder = 'Add item…';
  });
}

// ── Complete / delete ─────────────────────────────────────────────────────────
listEl.addEventListener('click', async e => {
  const checkBtn = e.target.closest('.check-btn');
  const deleteBtn = e.target.closest('.delete-btn');

  if (checkBtn) {
    const id = checkBtn.dataset.id;
    await db.from('gurkerl_items').update({
      completed: true,
      completed_at: new Date().toISOString(),
      completed_by: currentUser || 'unknown'
    }).eq('id', id);
  }

  if (deleteBtn) {
    const id = deleteBtn.dataset.id;
    await db.from('gurkerl_items').delete().eq('id', id);
  }
});

// ── Init ─────────────────────────────────────────────────────────────────────
if (!currentUser) {
  showUserModal();
} else {
  userBadge.textContent = currentUser;
}
updateCartButton();
loadItems();

// ── Gurkerl cart ──────────────────────────────────────────────────────────────

let cartRequestId = null;
let cartChannel   = null;
let cartMatches   = [];
let cartTimeout   = null;

function updateCartButton() {
  cartBtn.classList.toggle('hidden', !CART_USERS.includes(currentUser));
}

function showCartState(name) {
  Object.entries(cartStateEls).forEach(([k, el]) =>
    el.classList.toggle('hidden', k !== name)
  );
  cartModal.classList.remove('hidden');
}

function hideCartModal() {
  cartModal.classList.add('hidden');
  if (cartChannel) { db.removeChannel(cartChannel); cartChannel = null; }
  if (cartTimeout) { clearTimeout(cartTimeout); cartTimeout = null; }
  cartRequestId = null;
  cartMatches   = [];
}

function renderMatches(matches) {
  cartMatches = matches.map(m => ({ ...m }));
  const list = document.getElementById('cart-match-list');
  list.innerHTML = '';

  cartMatches.forEach((match, i) => {
    const div = document.createElement('div');
    div.className = 'match-item';

    const lbl = document.createElement('div');
    lbl.className = 'match-item-label';
    lbl.textContent = match.item_name;
    div.appendChild(lbl);

    if (!match.candidates || match.candidates.length === 0) {
      const none = document.createElement('div');
      none.className = 'match-no-result';
      none.textContent = 'No match found — will be skipped';
      div.appendChild(none);
    } else {
      const sel = document.createElement('select');
      sel.className = 'match-select';
      sel.dataset.idx = i;

      match.candidates.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.product_id;
        const parts = [c.name, c.brand, c.amount, c.price].filter(Boolean);
        opt.textContent = (c.is_frequent ? '★ ' : '') + parts.join(' · ');
        if (c.product_id === match.selected_product_id) opt.selected = true;
        sel.appendChild(opt);
      });

      const skip = document.createElement('option');
      skip.value = '';
      skip.textContent = '— Skip this item —';
      sel.appendChild(skip);

      sel.addEventListener('change', e => {
        cartMatches[+e.target.dataset.idx].selected_product_id = e.target.value || null;
      });
      div.appendChild(sel);
    }

    list.appendChild(div);
  });
}

function subscribeToRequest(id) {
  cartChannel = db.channel(`cart-req-${id}`)
    .on('postgres_changes', {
      event: 'UPDATE',
      schema: 'public',
      table: 'gurkerl_cart_requests',
      filter: `id=eq.${id}`,
    }, ({ new: row }) => {
      if (cartTimeout) { clearTimeout(cartTimeout); cartTimeout = null; }
      if (row.status === 'awaiting_confirmation') {
        renderMatches(row.matches || []);
        showCartState('matches');
      } else if (row.status === 'adding') {
        showCartState('adding');
      } else if (row.status === 'done') {
        showCartState('done');
      } else if (row.status === 'failed') {
        document.getElementById('cart-error-msg').textContent = row.error || 'Something went wrong.';
        showCartState('error');
      }
    })
    .subscribe();
}

async function startCartRequest() {
  if (!currentUser) { showUserModal(); return; }
  showCartState('loading');

  try {
    const { data, error } = await db.from('gurkerl_cart_requests')
      .insert({ requested_by: currentUser, status: 'pending' })
      .select().single();
    if (error) throw error;

    cartRequestId = data.id;
    subscribeToRequest(cartRequestId);

    cartTimeout = setTimeout(() => {
      document.getElementById('cart-error-msg').textContent =
        'No response from the VPS server. Is it running?';
      showCartState('error');
    }, 90_000);

  } catch (err) {
    console.error('Cart request error:', err);
    document.getElementById('cart-error-msg').textContent = 'Could not create cart request.';
    showCartState('error');
  }
}

async function confirmCart() {
  if (!cartRequestId) return;
  try {
    const { error } = await db.from('gurkerl_cart_requests')
      .update({ status: 'confirmed', matches: cartMatches })
      .eq('id', cartRequestId);
    if (error) throw error;
    showCartState('adding');
  } catch (err) {
    console.error('Confirm error:', err);
    document.getElementById('cart-error-msg').textContent = 'Could not confirm selection.';
    showCartState('error');
  }
}

cartBtn.addEventListener('click', startCartRequest);
document.getElementById('cart-confirm-btn').addEventListener('click', confirmCart);
document.getElementById('cart-cancel-btn').addEventListener('click', hideCartModal);
document.getElementById('cart-close-btn').addEventListener('click', hideCartModal);
document.getElementById('cart-retry-btn').addEventListener('click', () => { hideCartModal(); startCartRequest(); });
document.getElementById('cart-error-close-btn').addEventListener('click', hideCartModal);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js');
}
