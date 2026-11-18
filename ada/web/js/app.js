// App shell: auth gate, role-based navigation, hash router, connectivity + sync status.
import { api, session } from './api.js';
import { h, mount, toast } from './dom.js';
import { applyLang, setLang, getLang, t } from './i18n.js';
import { loadCatalog, startSync } from './sync.js';

const ROUTES = {
  pos: { view: () => import('./views/pos.js'), roles: ['owner', 'manager', 'cashier'], icon: '🛒', label: 'nav_pos' },
  chat: { view: () => import('./views/chat.js'), roles: ['owner', 'manager', 'cashier'], icon: '💬', label: 'nav_chat' },
  dashboard: { view: () => import('./views/dashboard.js'), roles: ['owner', 'manager'], icon: '📊', label: 'nav_dashboard' },
  products: { view: () => import('./views/products.js'), roles: ['owner', 'manager'], icon: '📦', label: 'nav_products' },
  sales: { view: () => import('./views/sales.js'), roles: ['owner', 'manager', 'cashier'], icon: '🧾', label: 'nav_sales' },
  alerts: { view: () => import('./views/alerts.js'), roles: ['owner', 'manager'], icon: '🔔', label: 'nav_alerts' },
  staff: { view: () => import('./views/staff.js'), roles: ['owner'], icon: '👥', label: 'nav_staff' },
  settings: { view: () => import('./views/settings.js'), roles: ['owner', 'manager', 'cashier'], icon: '⚙️', label: 'nav_settings' },
};

export const state = { user: null, profile: null, unread: 0, pending: 0 };
let current = null;
let routeSeq = 0;      // guards against overlapping navigations leaving stale views alive

function shell() {
  const role = state.user.role;
  const nav = h('nav', { class: 'nav', 'aria-label': 'main' },
    Object.entries(ROUTES).filter(([, r]) => r.roles.includes(role)).map(([key, r]) =>
      h('a', { href: `#/${key}`, class: 'nav-item', dataset: { route: key } },
        h('span', { class: 'nav-icon', 'aria-hidden': 'true' }, r.icon), h('span', { class: 'nav-label' }, t(r.label)),
        key === 'alerts' ? h('span', { class: 'badge', id: 'alerts-badge', hidden: true }) : null)));
  const header = h('header', { class: 'topbar' },
    h('div', { class: 'brand' }, h('img', { src: '/icons/icon-192.png', alt: '', width: 32, height: 32 }),
      h('div', {}, h('strong', {}, state.profile?.store_name || t('app')), h('small', { class: 'muted' }, `${t('app')} • ${state.user.name}`))),
    h('div', { class: 'topbar-actions' },
      h('span', { id: 'net', class: 'pill' }),
      h('button', { class: 'ghost', onclick: () => { setLang(getLang() === 'ar' ? 'en' : 'ar'); render(); } }, getLang() === 'ar' ? 'EN' : 'ع'),
      h('button', { class: 'ghost', id: 'install', hidden: !deferredInstall, onclick: install }, t('install_app'))));
  mount(document.getElementById('app'), header, h('div', { class: 'layout' }, nav, h('main', { id: 'view', tabindex: '-1' })));
  updateNet(); updateBadge();
}

async function route() {
  if (!state.user) return;
  const key = (location.hash.replace(/^#\/?/, '').split('?')[0]) || defaultRoute();
  const r = ROUTES[key];
  if (!r || !r.roles.includes(state.user.role)) { location.hash = `#/${defaultRoute()}`; return; }
  document.querySelectorAll('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.route === key));
  const my = ++routeSeq;
  current?.destroy?.(); current = null;
  const view = document.getElementById('view');
  // Each navigation renders into its own slot; a slower, superseded view keeps writing into
  // a detached slot and can never overwrite the current screen.
  const slot = h('div', { class: 'view-slot' }, h('div', { class: 'loading' }, t('loading')));
  mount(view, slot);
  try {
    const mod = await r.view();
    if (my !== routeSeq) return;
    const v = await mod.render(slot, state);
    if (my !== routeSeq) { v?.destroy?.(); return; }
    current = v;
  } catch (e) {
    if (my === routeSeq) mount(slot, h('div', { class: 'card error' }, t('error_generic', { m: e.message })));
  }
  view.focus({ preventScroll: true });
}

const defaultRoute = () => (state.user.role === 'cashier' ? 'pos' : (state.profile?.setup_completed === false && state.user.role === 'owner' ? 'settings' : 'pos'));

function updateNet() {
  const el = document.getElementById('net');
  if (!el) return;
  const on = navigator.onLine;
  el.className = `pill ${on ? 'ok' : 'warn'}`;
  el.textContent = (on ? t('online') : t('offline').split('—')[0]) + (state.pending ? ` • ${t('pending_sync', { n: state.pending })}` : '');
  el.title = on ? '' : t('offline');
}

function updateBadge() {
  const b = document.getElementById('alerts-badge');
  if (b) { b.hidden = !state.unread; b.textContent = state.unread > 99 ? '99+' : String(state.unread); }
}

async function pollAlerts() {
  if (!state.user || state.user.role === 'cashier' || !navigator.onLine) return;
  try { state.unread = (await api('/notifications/unread-count')).count; updateBadge(); } catch { /* ignore */ }
}

export async function render() {
  applyLang();
  if (!session.token) {
    state.user = null;
    const mod = await import('./views/login.js');
    return mod.render(document.getElementById('app'), async () => { await boot(); });
  }
  shell();
  route();
}

async function boot() {
  if (!session.token) return render();
  state.user = session.user;
  if (navigator.onLine) {
    try {
      state.user = await api('/auth/me');
      state.profile = await api('/store/profile');
      localStorage.setItem('ada.profile', JSON.stringify(state.profile));
      if (!localStorage.getItem('ada.lang') && state.profile.language) setLang(state.profile.language);
    } catch (e) { if (e.status === 401) { session.clear(); return render(); } }
  }
  state.profile ??= JSON.parse(localStorage.getItem('ada.profile') || 'null');
  await render();
  if (state.user && state.profile && !state.profile.setup_completed && state.user.role === 'owner') {
    (await import('./views/setup.js')).open(state);
  }
  loadCatalog();
}

// ---------- PWA install & updates ----------
let deferredInstall = null;
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredInstall = e; const b = document.getElementById('install'); if (b) b.hidden = false; });
async function install() { if (!deferredInstall) return; deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; document.getElementById('install').hidden = true; }

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((reg) => {
    reg.addEventListener('updatefound', () => {
      const nw = reg.installing;
      nw?.addEventListener('statechange', () => {
        if (nw.state === 'installed' && navigator.serviceWorker.controller) {
          toast(t('update_ready'), 'info');
          const bar = h('div', { class: 'update-bar' }, t('update_ready'),
            h('button', { class: 'primary', onclick: () => { nw.postMessage('skipWaiting'); } }, t('reload')));
          document.body.append(bar);
        }
      });
    });
  }).catch(() => { /* non-https dev */ });
  let reloaded = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (!reloaded) { reloaded = true; location.reload(); } });
}

window.addEventListener('hashchange', route);
window.addEventListener('online', () => { updateNet(); pollAlerts(); });
window.addEventListener('offline', updateNet);
window.addEventListener('ada:outbox', (e) => { state.pending = e.detail; updateNet(); });
window.addEventListener('ada:logout', () => { state.user = null; render(); });
window.addEventListener('ada:alerts', (e) => { state.unread = e.detail; updateBadge(); });
setInterval(pollAlerts, 30_000);

applyLang();
boot().then(() => { startSync(); pollAlerts(); });
