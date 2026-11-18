// Receipt rendering (80mm thermal or A4) and printing via the browser's print dialog.
import { h, mount, fmtMoney, fmtDate } from './dom.js';
import { t, pname } from './i18n.js';

export function receiptView(r) {
  const cur = r.currency;
  return h('div', { class: 'receipt' },
    h('div', { class: 'r-center' }, h('strong', { class: 'r-store' }, r.store.name),
      r.store.address ? h('div', {}, r.store.address) : null, r.store.phone ? h('div', { dir: 'ltr' }, r.store.phone) : null,
      r.store.tax_number ? h('div', {}, `${t('vat_no')}: ${r.store.tax_number}`) : null),
    h('hr'),
    h('div', { class: 'r-row' }, h('span', {}, `${t('receipt_no')}: ${r.number}`), h('span', {}, fmtDate(r.created_at))),
    r.cashier ? h('div', {}, `${t('cashier')}: ${r.cashier}`) : null,
    h('hr'),
    h('table', { class: 'r-items' }, h('tbody', {}, r.items.map(i => h('tr', {},
      h('td', {}, pname(i), h('div', { class: 'muted' }, `${i.quantity} × ${fmtMoney(i.unit_price, cur)}`)),
      h('td', { class: 'r-num' }, fmtMoney(i.line_total, cur)))))),
    h('hr'),
    h('div', { class: 'r-row' }, h('span', {}, t('subtotal')), h('span', {}, fmtMoney(r.subtotal, cur))),
    h('div', { class: 'r-row' }, h('span', {}, `${t('vat')} ${r.tax_rate}%`), h('span', {}, fmtMoney(r.tax, cur))),
    h('div', { class: 'r-row r-total' }, h('span', {}, t('total')), h('span', {}, fmtMoney(r.total, cur))),
    h('div', {}, `${t(r.payment_method)}`),
    h('hr'),
    h('div', { class: 'r-center' }, r.store.footer));
}

export function printReceipt(r) {
  const area = document.getElementById('print-area');
  mount(area, receiptView(r));
  window.print();
}
