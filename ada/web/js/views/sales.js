// Sales history with reprintable receipts (cashiers see only their own sales).
import { api } from '../api.js';
import { h, mount, modal, toast, fmtMoney, fmtDate } from '../dom.js';
import { t } from '../i18n.js';
import { outbox } from '../db.js';
import { receiptView, printReceipt } from '../receipt.js';

export async function render(root, state) {
  const cur = state.profile?.currency || 'SAR';
  const list = h('tbody');
  let lastId = null;
  const more = h('button', { onclick: () => load() }, t('load_more'));
  const pending = await outbox.all();

  async function load() {
    try {
      const rows = await api(`/sales?limit=50${lastId ? `&before_id=${lastId}` : ''}`);
      rows.forEach(s => list.append(h('tr', { class: 'clickable', tabindex: 0, onclick: () => open(s.id), onkeydown: (e) => e.key === 'Enter' && open(s.id) },
        h('td', { dir: 'ltr' }, `#${s.number}`), h('td', {}, fmtDate(s.created_at)), h('td', {}, s.cashier || '—'),
        h('td', {}, t(s.payment_method)), h('td', { class: 'num' }, fmtMoney(s.total, cur)))));
      if (rows.length) lastId = rows[rows.length - 1].id;
      more.hidden = rows.length < 50;
    } catch (e) { toast(t('error_generic', { m: e.message }), 'error'); }
  }

  async function open(id) {
    const r = await api(`/sales/${id}`);
    modal(t('receipt'), receiptView(r), [h('button', { class: 'primary', onclick: () => printReceipt(r) }, t('print_receipt'))]);
  }

  mount(root, h('div', { class: 'stack' },
    pending.length ? h('div', { class: 'card warn' }, t('pending_sync', { n: pending.length }),
      h('ul', {}, pending.filter(p => p.error).map(p => h('li', {}, `${p.client_ref}: ${p.error}`)))) : null,
    h('div', { class: 'card table-wrap' }, h('h2', {}, t('history')), h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, [t('receipt_no'), '', t('cashier'), '', t('total')].map(x => h('th', {}, x)))), list), more)));
  load();
}
