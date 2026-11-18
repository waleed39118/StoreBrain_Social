// Offline-first catalog + sales queue. Sales made offline get a client_ref and are uploaded
// automatically when the connection returns; the server applies each client_ref only once.
import { api } from './api.js';
import { kv, outbox } from './db.js';
import { uuid } from './dom.js';

let catalog = [];
let byBarcode = new Map(), bySku = new Map();

function index() {
  byBarcode = new Map(catalog.filter(p => p.barcode).map(p => [p.barcode, p]));
  bySku = new Map(catalog.map(p => [p.sku.toLowerCase(), p]));
}

export async function loadCatalog({ force = false } = {}) {
  if (!catalog.length) { catalog = (await kv.get('catalog')) || []; index(); }
  if (!navigator.onLine && !force) return catalog;
  try {
    const etag = force ? null : await kv.get('catalog_etag');
    const res = await api('/pos/catalog', { raw: true, headers: etag ? { 'If-None-Match': etag } : {} });
    if (res.status !== 304) {
      catalog = await res.json(); index();
      await kv.set('catalog', catalog);
      await kv.set('catalog_etag', res.headers.get('ETag'));
    }
  } catch { /* offline: keep cached copy */ }
  return catalog;
}

export const getCatalog = () => catalog;
export const findBarcode = (code) => byBarcode.get(code) || bySku.get(String(code).toLowerCase());

export function searchCatalog(q) {
  const s = q.trim().toLowerCase();
  if (!s) return catalog;
  return catalog.filter(p => p.sku.toLowerCase().includes(s) || p.name_en.toLowerCase().includes(s)
    || (p.name_ar || '').includes(q.trim()) || (p.barcode || '').startsWith(s));
}

/** Record a sale: online -> immediate receipt; offline -> queued with a local receipt. */
export async function sell(items, paymentMethod) {
  const client_ref = `pos-${uuid()}`;
  const payload = { items: items.map(i => ({ sku: i.sku, quantity: i.qty })), payment_method: paymentMethod, client_ref };
  if (navigator.onLine) {
    try {
      const receipt = await api('/pos/sales', { method: 'POST', body: payload });
      adjustLocalStock(items);
      return { receipt, offline: false };
    } catch (e) {
      if (e.status !== 0) throw e;            // real business error (e.g. no stock): surface it
    }
  }
  await outbox.add({ ...payload, sold_at: new Date().toISOString() });
  adjustLocalStock(items);
  notify();
  return { receipt: null, offline: true, client_ref };
}

function adjustLocalStock(items) {
  for (const i of items) { const p = bySku.get(i.sku.toLowerCase()); if (p) p.stock_qty = Math.max(0, p.stock_qty - i.qty); }
  kv.set('catalog', catalog);
}

let flushing = false;
export async function flush() {
  if (flushing || !navigator.onLine) return;
  flushing = true;
  try {
    const pending = await outbox.all();
    for (let i = 0; i < pending.length; i += 100) {
      const batch = pending.slice(i, i + 100);
      const { results } = await api('/pos/sync', { method: 'POST', body: { sales: batch } });
      for (const r of results) {
        if (r.status === 'ok') await outbox.remove(r.client_ref);
        else await outbox.add({ ...batch.find(b => b.client_ref === r.client_ref), error: r.error });
      }
    }
    if (pending.length) await loadCatalog({ force: true });
  } catch { /* retry later */ } finally { flushing = false; notify(); }
}

function notify() { outbox.count().then(n => window.dispatchEvent(new CustomEvent('ada:outbox', { detail: n }))); }

export function startSync() {
  window.addEventListener('online', flush);
  setInterval(flush, 30_000);
  flush(); notify();
}
