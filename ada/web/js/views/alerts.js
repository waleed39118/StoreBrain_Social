// In-app notifications (low stock, out of stock, stock discrepancies).
import { api } from '../api.js';
import { h, mount, toast, fmtDate } from '../dom.js';
import { t } from '../i18n.js';

export async function render(root) {
  const box = h('div', { class: 'stack' });
  async function load() {
    try {
      const rows = await api('/notifications?limit=100');
      const unread = rows.filter(r => !r.read_at).length;
      window.dispatchEvent(new CustomEvent('ada:alerts', { detail: unread }));
      mount(box,
        h('div', { class: 'row between' }, h('h2', {}, t('nav_alerts')),
          unread ? h('button', { onclick: async () => { await api('/notifications/read-all', { method: 'POST' }); load(); } }, t('mark_all_read')) : null),
        rows.length ? rows.map(n => h('div', { class: `card alert ${n.read_at ? 'read' : ''} kind-${n.kind}` },
          h('div', { class: 'grow' }, h('div', {}, n.message), h('small', { class: 'muted' }, fmtDate(n.created_at))),
          !n.read_at ? h('button', { class: 'small', onclick: async () => { await api(`/notifications/${n.id}/read`, { method: 'POST' }); load(); } }, t('mark_read')) : null))
          : h('p', { class: 'muted' }, t('nothing_here')));
    } catch (e) { toast(t('error_generic', { m: e.message }), 'error'); }
  }
  mount(root, box);
  load();
}
