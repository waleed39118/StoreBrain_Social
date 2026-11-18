// Owner: manage staff (role, PIN, deactivate) and see signed-in devices.
import { api } from '../api.js';
import { h, mount, modal, toast, fmtDate } from '../dom.js';
import { t } from '../i18n.js';
import { field } from './login.js';

export async function render(root) {
  const box = h('div', { class: 'stack' });
  const roleLabel = (r) => ({ owner: t('owner'), manager: t('manager'), cashier: t('cashier_role') }[r] || r);

  async function load() {
    try {
      const users = await api('/users');
      mount(box,
        h('div', { class: 'row between' }, h('h2', {}, t('nav_staff')), h('button', { class: 'primary', onclick: () => form() }, `＋ ${t('staff_add')}`)),
        h('div', { class: 'card table-wrap' }, h('table', { class: 'table' },
          h('thead', {}, h('tr', {}, [t('name'), t('phone'), t('role'), ''].map(x => h('th', {}, x)))),
          h('tbody', {}, users.map(u => h('tr', { class: u.is_active ? '' : 'muted' },
            h('td', {}, u.name), h('td', { dir: 'ltr' }, u.phone), h('td', {}, roleLabel(u.role)),
            h('td', { class: 'actions' }, u.role === 'owner' ? null : [
              h('button', { class: 'small', onclick: () => form(u) }, t('reset_pin')),
              h('button', { class: 'small ghost', onclick: () => toggle(u) }, u.is_active ? t('deactivate') : t('activate'))])))))));
    } catch (e) { toast(t('error_generic', { m: e.message }), 'error'); }
  }

  async function toggle(u) {
    await api(`/users/${u.id}`, { method: 'PATCH', body: { is_active: !u.is_active } }); load();
  }

  function form(u = null) {
    const f = h('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f).entries());
      try {
        if (u) await api(`/users/${u.id}`, { method: 'PATCH', body: { pin: d.pin, role: d.role, name: d.name } });
        else await api('/users', { method: 'POST', body: d });
        toast(t('saved'), 'ok'); close(); load();
      } catch (err) { toast(t('error_generic', { m: err.message }), 'error'); }
    } },
      field(t('name'), h('input', { name: 'name', required: true, value: u?.name || '' })),
      u ? null : field(t('phone'), h('input', { name: 'phone', type: 'tel', required: true, dir: 'ltr' })),
      field(t('role'), h('select', { name: 'role' }, ['cashier', 'manager'].map(r => h('option', { value: r, selected: u?.role === r }, roleLabel(r))))),
      field(t('pin'), h('input', { name: 'pin', type: 'password', inputmode: 'numeric', pattern: '\\d{4,8}', required: true, dir: 'ltr', autocomplete: 'new-password' })),
      h('button', { class: 'primary', type: 'submit' }, t('save')));
    const close = modal(u ? `${t('reset_pin')} — ${u.name}` : t('staff_add'), f);
  }

  mount(root, h('div', { class: 'stack' }, box, await sessionsCard()));
  load();
}

export async function sessionsCard() {
  const card = h('div', { class: 'card' });
  async function load() {
    try {
      const rows = await api('/auth/sessions');
      mount(card, h('h2', {}, t('my_sessions')), h('ul', { class: 'plain' }, rows.map(s => h('li', { class: 'row between' },
        h('span', {}, `${s.device_name} • ${fmtDate(s.last_seen_at)}`, s.current ? h('strong', {}, ` (${t('this_device')})`) : null),
        s.current ? null : h('button', { class: 'small ghost', onclick: async () => { await api(`/auth/sessions/${s.id}`, { method: 'DELETE' }); load(); } }, t('revoke'))))));
    } catch { /* offline */ }
  }
  load();
  return card;
}
