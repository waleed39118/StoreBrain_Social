// Catalog management: search, manual add/edit, scan-to-fill barcode, restock, Excel/CSV import.
import { api } from '../api.js';
import { h, mount, toast, modal, modalOpen, fmtMoney, downloadBlob } from '../dom.js';
import { t, pname } from '../i18n.js';
import { cameraScan, onWedgeScan } from '../scanner.js';
import { loadCatalog } from '../sync.js';
import { field } from './login.js';

export async function render(root, state) {
  const cur = state.profile?.currency || 'SAR';
  let q = '';
  const tbody = h('tbody');
  const search = h('input', { type: 'search', class: 'search grow', placeholder: t('search_products'), 'aria-label': t('search_products'),
    oninput: debounce((e) => { q = e.target.value; load(); }, 250) });

  async function load() {
    try {
      const rows = await api(`/products${q ? `?q=${encodeURIComponent(q)}` : ''}`);
      mount(tbody, rows.length ? rows.map(p => h('tr', { class: p.stock_qty <= p.reorder_level ? 'low' : '' },
        h('td', {}, h('strong', {}, pname(p)), h('div', { class: 'muted small', dir: 'ltr' }, `${p.sku}${p.barcode ? ' • ' + p.barcode : ''}`)),
        h('td', {}, p.category), h('td', { class: 'num' }, fmtMoney(p.price, cur)),
        h('td', { class: 'num' }, String(p.stock_qty)),
        h('td', { class: 'actions' },
          h('button', { class: 'small', onclick: () => restock(p) }, t('restock')),
          h('button', { class: 'small ghost', onclick: () => edit(p) }, '✎'))))
        : h('tr', {}, h('td', { colspan: 5, class: 'muted' }, t('nothing_here'))));
    } catch (e) { toast(t('error_generic', { m: e.message }), 'error'); }
  }

  function edit(p = null) {
    const isNew = !p;
    p ||= { sku: '', barcode: '', name_en: '', name_ar: '', category: 'general', price: '', cost: '', stock_qty: 0, reorder_level: 5, lead_time_days: 3, expiry_date: '', condition: 'new', is_active: true };
    const inp = (name, attrs = {}) => h('input', { name, value: p[name] ?? '', ...attrs });
    const barcode = inp('barcode', { dir: 'ltr', inputmode: 'numeric' });
    const form = h('form', { class: 'form-grid', onsubmit: save },
      field(t('name_ar'), inp('name_ar', { required: true })), field(t('name_en'), inp('name_en')),
      field(t('sku'), inp('sku', { required: true, readonly: !isNew, dir: 'ltr' })),
      field(t('barcode'), h('div', { class: 'row gap' }, barcode, h('button', { type: 'button', class: 'icon-btn', 'aria-label': t('scan_camera'),
        onclick: async () => { const c = await cameraScan(); if (c) barcode.value = c; } }, '📷'))),
      field(t('category'), inp('category')), field(t('price'), inp('price', { type: 'number', step: '0.01', min: 0, required: true, dir: 'ltr' })),
      field(t('cost'), inp('cost', { type: 'number', step: '0.01', min: 0, dir: 'ltr' })),
      isNew ? field(t('stock'), inp('stock_qty', { type: 'number', min: 0, dir: 'ltr' })) : null,
      field(t('reorder_level'), inp('reorder_level', { type: 'number', min: 0, dir: 'ltr' })),
      field(t('lead_time'), inp('lead_time_days', { type: 'number', min: 0, dir: 'ltr' })),
      field(t('expiry'), inp('expiry_date', { type: 'date', dir: 'ltr' })),
      field(t('condition'), h('select', { name: 'condition' }, ['new', 'good', 'damaged', 'expired', 'discontinued'].map(c => h('option', { value: c, selected: p.condition === c }, c)))),
      !isNew ? h('label', { class: 'row gap' }, h('input', { type: 'checkbox', name: 'is_active', checked: p.is_active }), t('active')) : null,
      h('div', { class: 'form-actions' }, h('button', { class: 'primary', type: 'submit' }, t('save'))));
    const stopWedge = onWedgeScan((c) => { barcode.value = c; });
    const close = modal(isNew ? t('add_product') : t('edit_product'), form, [], { onClose: stopWedge });

    async function save(e) {
      e.preventDefault();
      const f = new FormData(form), body = {};
      for (const [k, v] of f.entries()) if (v !== '') body[k] = v;
      body.name_en ||= body.name_ar;
      if (!isNew) { body.is_active = f.has('is_active'); delete body.sku; }
      for (const k of ['stock_qty', 'reorder_level', 'lead_time_days']) if (k in body) body[k] = Number(body[k]);
      if (!body.barcode) body.barcode = null;
      if (!body.expiry_date) body.expiry_date = null;
      try {
        await api(isNew ? '/products' : `/products/${encodeURIComponent(p.sku)}`, { method: isNew ? 'POST' : 'PATCH', body });
        toast(t('saved'), 'ok'); close(); load(); loadCatalog({ force: true });
      } catch (err) { toast(t('error_generic', { m: err.message }), 'error'); }
    }
  }

  function restock(p) {
    const qty = h('input', { type: 'number', min: 1, required: true, dir: 'ltr', value: 1 });
    const close = modal(`${t('restock')} — ${pname(p)}`, h('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      try { await api(`/products/${encodeURIComponent(p.sku)}/restock`, { method: 'POST', body: { quantity: Number(qty.value), ref: 'app' } });
        toast(t('saved'), 'ok'); close(); load(); loadCatalog({ force: true });
      } catch (err) { toast(t('error_generic', { m: err.message }), 'error'); }
    } }, field(t('restock_qty'), qty), h('button', { class: 'primary', type: 'submit' }, t('save'))));
  }

  function importer() {
    const file = h('input', { type: 'file', accept: '.xlsx,.csv,.txt', required: true });
    const mode = h('select', {}, h('option', { value: 'set' }, t('mode_set')), h('option', { value: 'add' }, t('mode_add')));
    const skip = h('input', { type: 'checkbox' });
    const out = h('div', { class: 'stack' });
    const run = async (dry) => {
      if (!file.files[0]) return toast(t('choose_file'), 'error');
      const fd = new FormData();
      fd.append('file', file.files[0]); fd.append('dry_run', String(dry)); fd.append('stock_mode', mode.value); fd.append('skip_invalid', String(skip.checked));
      try {
        const r = await api('/products/import', { method: 'POST', form: fd });
        mount(out, h('div', { class: `card ${r.errors.length ? 'warn' : 'ok'}` }, t('import_summary', { c: r.created, u: r.updated, s: r.skipped }),
            r.applied ? h('strong', {}, ` — ${t('saved')}`) : null),
          r.unknown_columns.length ? h('p', { class: 'muted' }, t('unknown_cols', { c: r.unknown_columns.join('، ') })) : null,
          r.errors.length ? h('details', { open: true }, h('summary', {}, t('import_errors', { n: r.errors.length })),
            h('ul', {}, r.errors.slice(0, 200).map(er => h('li', {}, `${t('row')} ${er.row}: ${er.error}`)))) : null);
        if (r.applied) { load(); loadCatalog({ force: true }); }
      } catch (err) { toast(t('error_generic', { m: err.message }), 'error'); }
    };
    modal(t('import_excel'), h('div', { class: 'stack' },
      h('button', { class: 'link', onclick: async () => downloadBlob(await (await api('/products/import/template', { raw: true })).blob(), 'ada_products_template.xlsx') }, `⬇ ${t('download_template')}`),
      field(t('choose_file'), file), field(t('import_mode'), mode), h('label', { class: 'row gap' }, skip, t('skip_invalid')),
      h('div', { class: 'row gap' }, h('button', { onclick: () => run(true) }, t('preview')), h('button', { class: 'primary', onclick: () => run(false) }, t('apply_import'))),
      out));
  }

  mount(root, h('div', { class: 'stack' },
    h('div', { class: 'row gap wrap' }, search,
      h('button', { class: 'primary', onclick: () => edit() }, `＋ ${t('add_product')}`),
      h('button', { onclick: importer }, `⬆ ${t('import_excel')}`)),
    h('div', { class: 'card table-wrap' }, h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, [t('name'), t('category'), t('price'), t('stock'), ''].map(x => h('th', {}, x)))), tbody))));
  load();
  const off = onWedgeScan((c) => { if (modalOpen()) return; search.value = c; q = c; load(); });
  return { destroy: off };
}

function debounce(fn, ms) { let id; return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), ms); }; }
