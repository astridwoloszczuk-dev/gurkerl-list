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
loadItems();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js');
}
