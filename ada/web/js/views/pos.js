// Point of sale: barcode-first (scanner or camera), touch-friendly product grid, offline-safe.
import { h, mount, toast, modal, fmtMoney } from '../dom.js';
import { t, pname } from '../i18n.js';
import { loadCatalog, searchCatalog, findBarcode, sell, getCatalog } from '../sync.js';
import { onWedgeScan, cameraScan } from '../scanner.js';
import { receiptView, printReceipt } from '../receipt.js';

export async function render(root, state) {
  const cur = state.profile?.currency || 'SAR';
  const cart = new Map();                         // sku -> {sku, name, price, qty, stock}
  let query = '', category = '', payment = 'cash', busy = false;
  await loadCatalog();

  const search = h('input', { type: 'search', class: 'search', placeholder: t('search_products'), 'aria-label': t('search_products'),
    oninput: (e) => { query = e.target.value; drawGrid(); },
    onkeydown: (e) => { if (e.key === 'Enter') { const r = searchCatalog(query); if (r.length === 1) { add(r[0]); search.value = ''; query = ''; drawGrid(); } } } });
  const grid = h('div', { class: 'grid', role: 'list' });
  const cats = h('div', { class: 'chips', role: 'toolbar' });
  const cartBox = h('aside', { class: 'cart card', 'aria-label': t('cart') });

  function add(p, qty = 1) {
    const line = cart.get(p.sku) || { sku: p.sku, product: p, qty: 0 };
    line.qty += qty;
    if (line.qty <= 0) cart.delete(p.sku); else cart.set(p.sku, line);
    drawCart();
  }

  function onCode(code) {
    search.value = ''; query = ''; drawGrid();      // a scan must not leave the grid filtered
    const p = findBarcode(code);
    if (p) { add(p); beep(); } else toast(t('not_found_barcode', { c: code }), 'error');
  }

  function drawCats() {
    const all = [...new Set(getCatalog().map(p => p.category))].sort();
    mount(cats, [''].concat(all).map(c => h('button', { class: c === category ? 'chip active' : 'chip', onclick: () => { category = c; drawCats(); drawGrid(); } }, c || t('all'))));
  }

  function drawGrid() {
    const items = searchCatalog(query).filter(p => !category || p.category === category).slice(0, 120);
    mount(grid, items.length ? items.map(p => h('button', { class: `tile ${p.stock_qty <= 0 ? 'empty' : ''}`, role: 'listitem', onclick: () => add(p) },
      h('span', { class: 'tile-name' }, pname(p)),
      h('span', { class: 'tile-price' }, fmtMoney(p.price, cur)),
      h('span', { class: 'tile-stock muted' }, p.stock_qty > 0 ? t('in_stock', { n: p.stock_qty }) : t('out_of_stock'))))
      : h('p', { class: 'muted' }, t('nothing_here')));
  }

  function total() { let s = 0; for (const l of cart.values()) s += Number(l.product.price) * l.qty; return s; }

  function drawCart() {
    const lines = [...cart.values()];
    mount(cartBox,
      h('div', { class: 'row between' }, h('h2', {}, t('cart')), lines.length ? h('button', { class: 'link', onclick: () => { cart.clear(); drawCart(); } }, t('clear_cart')) : null),
      lines.length ? h('ul', { class: 'cart-lines' }, lines.map(l => h('li', { class: 'cart-line' },
        h('div', { class: 'grow' }, h('div', {}, pname(l.product)), h('small', { class: 'muted' }, fmtMoney(l.product.price, cur))),
        h('div', { class: 'stepper' },
          h('button', { 'aria-label': '−', onclick: () => add(l.product, -1) }, '−'),
          h('span', { class: 'qty' }, String(l.qty)),
          h('button', { 'aria-label': '+', onclick: () => add(l.product, 1) }, '+')),
        h('strong', { class: 'line-total' }, fmtMoney(Number(l.product.price) * l.qty, cur)))))
        : h('p', { class: 'muted empty-cart' }, t('cart_empty')),
      h('div', { class: 'cart-foot' },
        h('div', { class: 'row between total-row' }, h('span', {}, t('total')), h('strong', { class: 'grand' }, fmtMoney(total(), cur))),
        h('div', { class: 'seg', role: 'radiogroup' }, ['cash', 'card', 'transfer'].map(m =>
          h('button', { role: 'radio', 'aria-checked': String(payment === m), class: payment === m ? 'active' : '', onclick: () => { payment = m; drawCart(); } }, t(m)))),
        h('button', { class: 'primary big', disabled: !lines.length || busy, onclick: checkout }, `${t('checkout')} • ${fmtMoney(total(), cur)}`)));
  }

  async function checkout() {
    if (busy || !cart.size) return;
    busy = true; drawCart();
    try {
      const items = [...cart.values()].map(l => ({ sku: l.sku, qty: l.qty }));
      const res = await sell(items, payment);
      cart.clear();
      if (res.offline) toast(t('sale_offline'), 'warn');
      else {
        toast(t('sale_done'), 'ok');
        const close = modal(t('receipt'), receiptView(res.receipt), [
          h('button', { onclick: () => printReceipt(res.receipt) }, t('print_receipt')),
          h('button', { class: 'primary', onclick: () => close() }, t('new_sale'))]);
      }
      drawGrid();
    } catch (e) {
      toast(t('error_generic', { m: e.message }), 'error');
    } finally { busy = false; drawCart(); search.focus(); }
  }

  mount(root, h('div', { class: 'pos' },
    h('section', { class: 'pos-main' },
      h('div', { class: 'row gap' }, search, h('button', { class: 'icon-btn big', title: t('scan_camera'), 'aria-label': t('scan_camera'),
        onclick: async () => { const c = await cameraScan(); if (c) onCode(c); } }, '📷')),
      cats, grid),
    cartBox));
  drawCats(); drawGrid(); drawCart();
  search.focus();
  const off = onWedgeScan(onCode);
  return { destroy: off };
}

let ctx;
function beep() {
  try {
    ctx ??= new AudioContext();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 1400; g.gain.value = 0.05; o.connect(g).connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.06);
  } catch { /* ignore */ }
}
